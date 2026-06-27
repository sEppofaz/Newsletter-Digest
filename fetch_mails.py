#!/usr/bin/env python3
"""
Newsletter Digest – Mail-Fetch Script
Läuft täglich per systemd-Timer, prüft ob heute Ausgabe-Tag ist,
holt Mails per IMAP und übergibt sie an Flask /api/process.
"""
import imaplib, email, os, sys, json, logging
from email.header import decode_header
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import dotenv_values
import requests

_env = dotenv_values(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

API_BASE              = "http://127.0.0.1:5006"
BEARER_TOKEN          = _env.get("BEARER_TOKEN", "")
GMAIL_USER            = _env.get("GMAIL_USER", "josef.jf.fischer@gmail.com")
GMAIL_PASSWORD        = _env.get("GMAIL_APP_PASSWORD", "")
ANTHROPIC_API_KEY     = _env.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL_FALLBACK = "claude-haiku-4-5-20251001"
CLAUDE_MODEL          = _env.get("CLAUDE_MODEL", CLAUDE_MODEL_FALLBACK)
IMAP_HOST             = "imap.gmail.com"
IMAP_PORT             = 993
LOOKBACK_HOURS        = 25

VALID_CATEGORIES = {"ki_tech", "finanzen", "automobil", "lokal"}


def should_run() -> bool:
    try:
        r = requests.get(f"{API_BASE}/api/should_run", timeout=10)
        data = r.json()
        if not data.get("run"):
            log.info("Heute kein Ausgabe-Tag (%s) – Abbruch.", data.get("date"))
            return False
        log.info("Ausgabe-Tag: %s", data.get("date"))
        return True
    except Exception as e:
        log.error("should_run-Check fehlgeschlagen: %s", e)
        return False


def get_sender_mapping() -> dict:
    try:
        r = requests.get(f"{API_BASE}/api/config", timeout=10)
        return r.json().get("senders", {})
    except Exception as e:
        log.warning("Config nicht geladen, leeres Mapping: %s", e)
        return {}


def auto_categorize(from_addr: str, subject: str, body: str, model: str | None = None) -> str | None:
    """Lässt Claude Haiku die Kategorie bestimmen. Gibt None zurück wenn keine Kategorie passt."""
    if model is None:
        model = CLAUDE_MODEL

    prompt = (
        f"Absender: {from_addr}\n"
        f"Betreff: {subject}\n"
        f"Inhalt (Auszug): {body[:600]}\n\n"
        "Kategorisiere diesen Newsletter. Antworte NUR mit einem dieser Begriffe:\n"
        "ki_tech – KI, Technologie, Software, Wissenschaft\n"
        "finanzen – Finanzen, Wirtschaft, Aktien, Unternehmen\n"
        "automobil – Automobil, E-Mobilität, Fahrzeuge, Verkehr\n"
        "lokal – Lokales aus Bayerbach, Hölskofen, Oberköllnbach oder Paindlkofen (Niederbayern)\n"
        "keine – passt in keine dieser Kategorien\n\n"
        "Antwort (nur das eine Wort):"
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 20,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )

        if resp.status_code in (400, 404) and "model_not_found" in resp.text.lower():
            if model != CLAUDE_MODEL_FALLBACK:
                log.warning("Modell '%s' ungültig, Fallback auf '%s'", model, CLAUDE_MODEL_FALLBACK)
                return auto_categorize(from_addr, subject, body, model=CLAUDE_MODEL_FALLBACK)
            return None

        resp.raise_for_status()
        cat = resp.json()["content"][0]["text"].strip().lower().split()[0]
        if cat in VALID_CATEGORIES:
            log.info("Auto-Kategorie für %s: %s", from_addr, cat)
            return cat
        log.info("Keine passende Kategorie für %s (%s) – übersprungen", from_addr, cat)
        return None

    except Exception as e:
        log.warning("Auto-Kategorisierung fehlgeschlagen für %s: %s", from_addr, e)
        return None


def decode_str(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    parts = decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def extract_body(msg) -> str:
    """Plaintext-Body extrahieren, HTML als Fallback."""
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not plain:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                plain = payload.decode(charset, errors="replace") if payload else ""
            elif ct == "text/html" and not html:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace") if payload else ""
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace") if payload else ""
        if msg.get_content_type() == "text/html":
            html = text
        else:
            plain = text

    body = plain or html
    # Grob kürzen damit Claude nicht überflutet wird
    return body[:8000] if body else ""


def fetch_mails(sender_mapping: dict) -> list:
    mails = []
    try:
        log.info("Verbinde mit Gmail IMAP…")
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(GMAIL_USER, GMAIL_PASSWORD)
        imap.select("INBOX")

        # Mails der letzten LOOKBACK_HOURS holen
        since = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%d-%b-%Y")
        _, msg_ids = imap.search(None, f'(SINCE "{since}")')

        ids = msg_ids[0].split() if msg_ids[0] else []
        log.info("%d Mails seit %s gefunden", len(ids), since)

        for mid in ids:
            _, data = imap.fetch(mid, "(RFC822)")
            if not data or not data[0]:
                continue
            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            from_raw = decode_str(msg.get("From", ""))
            # E-Mail-Adresse aus "Name <email@domain.com>" extrahieren
            from_addr = from_raw
            if "<" in from_raw and ">" in from_raw:
                from_addr = from_raw.split("<")[1].split(">")[0].strip().lower()
            else:
                from_addr = from_raw.strip().lower()

            category = sender_mapping.get(from_addr)
            if not category:
                log.info("Absender unbekannt, Auto-Kategorisierung: %s", from_addr)
                body_preview = extract_body(msg)
                category = auto_categorize(from_addr, subject, body_preview)
                if not category:
                    continue

            subject = decode_str(msg.get("Subject", "(kein Betreff)"))
            body = extract_body(msg)

            mails.append({
                "from":     from_addr,
                "subject":  subject,
                "body":     body,
                "category": category,
            })
            log.info("Mail übernommen: [%s] %s", category, subject[:60])

        imap.logout()
    except imaplib.IMAP4.error as e:
        log.error("IMAP-Fehler: %s", e)
        notify_telegram(f"IMAP-Fehler beim Mail-Abruf: {e}")
    except Exception as e:
        log.error("Unerwarteter Fehler beim Mail-Abruf: %s", e)
        notify_telegram(f"Unerwarteter Fehler beim Mail-Abruf: {e}")

    return mails


def notify_telegram(msg: str):
    """Direkt-Alert ohne Flask (Fallback wenn Flask nicht erreichbar)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": f"⚠️ [Newsletter-Fetch]\n{msg}"},
            timeout=10,
        )
    except Exception:
        pass


def process_mails(mails: list, date_str: str) -> bool:
    try:
        r = requests.post(
            f"{API_BASE}/api/process",
            headers={
                "Authorization": f"Bearer {BEARER_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"date": date_str, "mails": mails},
            timeout=300,   # Claude-Calls können dauern
        )
        if r.ok:
            data = r.json()
            log.info("Digest erstellt: %s – Kategorien: %s", date_str, data.get("categories"))
            return True
        else:
            err = f"POST /api/process fehlgeschlagen: HTTP {r.status_code} – {r.text[:200]}"
            log.error(err)
            notify_telegram(err)
            return False
    except Exception as e:
        err = f"POST /api/process Exception: {e}"
        log.error(err)
        notify_telegram(err)
        return False


def main():
    log.info("=== Newsletter Fetch gestartet ===")

    if not should_run():
        sys.exit(0)

    date_str = datetime.now().strftime("%Y-%m-%d")
    sender_mapping = get_sender_mapping()

    if not sender_mapping:
        log.warning("Kein Absender-Mapping konfiguriert – keine Mails werden verarbeitet.")
        notify_telegram("Kein Absender-Mapping konfiguriert. Bitte in der PWA unter Einstellungen eintragen.")
        sys.exit(1)

    if not GMAIL_PASSWORD:
        log.error("GMAIL_APP_PASSWORD nicht gesetzt")
        notify_telegram("GMAIL_APP_PASSWORD fehlt in .env")
        sys.exit(1)

    mails = fetch_mails(sender_mapping)

    if not mails:
        log.info("Keine passenden Mails gefunden – kein Digest erstellt.")
        sys.exit(0)

    log.info("%d Mails werden verarbeitet…", len(mails))
    success = process_mails(mails, date_str)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
