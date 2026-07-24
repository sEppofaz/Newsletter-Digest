#!/usr/bin/env python3
import argparse, imaplib, email, sys, json, logging
from email.header import decode_header
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import dotenv_values
import requests

import costs

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
TELEGRAM_BOT_TOKEN    = _env.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID      = _env.get("TELEGRAM_CHAT_ID", "")
IMAP_HOST             = "imap.gmail.com"
IMAP_PORT             = 993
LOOKBACK_HOURS        = 25


def _split_telegram_message(text: str, limit: int = 4096) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts


def notify_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    full_text = f"⚠️ [Newsletter-Fetch]\n{msg}"
    try:
        for part in _split_telegram_message(full_text):
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": part},
                timeout=10,
            )
    except Exception:
        pass


def should_run() -> bool:
    try:
        r = requests.get(f"{API_BASE}/api/should_run", timeout=10)
        data = r.json()
        if not data.get("run"):
            log.info("Heute kein Ausgabe-Zeitpunkt (%s) – Abbruch.", data.get("date"))
            return False
        log.info("Ausgabe-Zeitpunkt: %s", data.get("date"))
        return True
    except Exception as e:
        log.error("should_run-Check fehlgeschlagen: %s", e)
        return False


def get_config() -> dict:
    try:
        r = requests.get(f"{API_BASE}/api/config", timeout=10)
        return r.json()
    except Exception as e:
        log.warning("Config nicht geladen: %s", e)
        return {}


def get_valid_categories(cfg: dict) -> set[str]:
    cats = cfg.get("categories", [])
    return {c["id"] for c in cats if c.get("enabled", True)}


def build_category_prompt(cfg: dict) -> str:
    cats = cfg.get("categories", [])
    lines = []
    for c in cats:
        if c.get("enabled", True):
            lines.append(f"{c['id']} – {c.get('context', c['name'])}")
    lines.append("keine – passt in keine dieser Kategorien")
    return "\n".join(lines)


def auto_categorize(from_addr: str, subject: str, body: str,
                    valid_categories: set[str], cat_prompt: str,
                    model: str | None = None) -> tuple[str | None, bool]:
    if model is None:
        model = CLAUDE_MODEL

    prompt = (
        f"Absender: {from_addr}\n"
        f"Betreff: {subject}\n"
        f"Inhalt (Auszug): {body[:600]}\n\n"
        f"Kategorisiere diesen Newsletter. Antworte NUR mit einem dieser Begriffe:\n"
        f"{cat_prompt}\n\n"
        f"Antwort (nur das eine Wort):"
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
                return auto_categorize(from_addr, subject, body, valid_categories, cat_prompt,
                                       model=CLAUDE_MODEL_FALLBACK)
            return None, False

        resp.raise_for_status()
        resp_json = resp.json()
        usage = resp_json.get("usage", {})
        result = costs.record_call(
            model, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
            context="auto_categorize",
        )
        if result["warn_1usd"]:
            notify_telegram(
                f"1$ Tagesverbrauch erreicht (heute: ${result['day_total_usd']:.2f}).\n"
                f"Verarbeitung läuft normal weiter, keine Aktion nötig."
            )

        cat = resp_json["content"][0]["text"].strip().lower().split()[0]
        if cat in valid_categories:
            log.info("Auto-Kategorie für %s: %s", from_addr, cat)
            return cat, result["hard_kill"]
        log.info("Keine passende Kategorie für %s (%s) – übersprungen", from_addr, cat)
        return None, result["hard_kill"]

    except Exception as e:
        log.warning("Auto-Kategorisierung fehlgeschlagen für %s: %s", from_addr, e)
        return None, False


def decode_str(value) -> str:
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
    return body[:8000] if body else ""


def fetch_mails(sender_mapping: dict, valid_categories: set[str], cat_prompt: str) -> list:
    mails = []
    processed_ids = []
    hard_kill_triggered = False
    try:
        log.info("Verbinde mit Gmail IMAP…")
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(GMAIL_USER, GMAIL_PASSWORD)
        imap.select("INBOX")

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
            if "<" in from_raw and ">" in from_raw:
                from_addr = from_raw.split("<")[1].split(">")[0].strip().lower()
            else:
                from_addr = from_raw.strip().lower()

            subject = decode_str(msg.get("Subject", "(kein Betreff)"))
            body = extract_body(msg)

            category = sender_mapping.get(from_addr)
            if not category:
                if hard_kill_triggered:
                    log.info("Kosten-Hard-Kill aktiv – Auto-Kategorisierung übersprungen für %s", from_addr)
                    continue
                log.info("Absender unbekannt, Auto-Kategorisierung: %s", from_addr)
                category, hard_kill = auto_categorize(from_addr, subject, body, valid_categories, cat_prompt)
                if hard_kill and not hard_kill_triggered:
                    hard_kill_triggered = True
                    notify_telegram(
                        "5$ Tagesverbrauch erreicht – automatische Kategorisierung für weitere "
                        "unbekannte Absender in diesem Lauf übersprungen.\n"
                        "Bereits verarbeitete Mails bleiben erhalten, übrige unbekannte Absender "
                        "werden im nächsten stündlichen Lauf erneut versucht."
                    )
                if not category:
                    continue

            mails.append({
                "from":     from_addr,
                "subject":  subject,
                "body":     body,
                "category": category,
            })
            processed_ids.append(mid)
            log.info("Mail übernommen: [%s] %s", category, subject[:60])

        if processed_ids:
            log.info("%d Mails werden als gelesen markiert und archiviert…", len(processed_ids))
            for mid in processed_ids:
                try:
                    imap.store(mid, "+FLAGS", "\\Seen")
                    imap.copy(mid, "[Gmail]/All Mail")
                    imap.store(mid, "+FLAGS", "\\Deleted")
                except Exception as e:
                    log.warning("Fehler beim Archivieren von Mail %s: %s", mid, e)
            imap.expunge()
            log.info("Archivierung abgeschlossen (%d Mails).", len(processed_ids))

        imap.logout()
    except imaplib.IMAP4.error as e:
        log.error("IMAP-Fehler: %s", e)
        notify_telegram(f"IMAP-Fehler beim Mail-Abruf: {e}")
    except Exception as e:
        log.error("Unerwarteter Fehler beim Mail-Abruf: %s", e)
        notify_telegram(f"Unerwarteter Fehler beim Mail-Abruf: {e}")

    return mails


def fetch_from_all_mail(days: int, sender_mapping: dict, valid_categories: set[str], cat_prompt: str) -> list:
    """Einmaliger Nachhol-Lauf: durchsucht [Gmail]/All Mail (nicht INBOX) rein lesend,
    da ältere Mails ggf. schon archiviert wurden. Ändert keine IMAP-Flags."""
    mails = []
    hard_kill_triggered = False
    try:
        log.info("Verbinde mit Gmail IMAP (Nachhol-Modus, [Gmail]/All Mail)…")
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(GMAIL_USER, GMAIL_PASSWORD)
        imap.select('"[Gmail]/All Mail"', readonly=True)

        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        _, msg_ids = imap.search(None, f'(SINCE "{since}")')

        ids = msg_ids[0].split() if msg_ids[0] else []
        log.info("%d Mails seit %s in [Gmail]/All Mail gefunden", len(ids), since)

        for mid in ids:
            _, data = imap.fetch(mid, "(RFC822)")
            if not data or not data[0]:
                continue
            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            from_raw = decode_str(msg.get("From", ""))
            if "<" in from_raw and ">" in from_raw:
                from_addr = from_raw.split("<")[1].split(">")[0].strip().lower()
            else:
                from_addr = from_raw.strip().lower()

            subject = decode_str(msg.get("Subject", "(kein Betreff)"))
            body = extract_body(msg)

            category = sender_mapping.get(from_addr)
            if not category:
                if hard_kill_triggered:
                    log.info("Kosten-Hard-Kill aktiv – Auto-Kategorisierung übersprungen für %s", from_addr)
                    continue
                category, hard_kill = auto_categorize(from_addr, subject, body, valid_categories, cat_prompt)
                if hard_kill and not hard_kill_triggered:
                    hard_kill_triggered = True
                    notify_telegram(
                        "5$ Tagesverbrauch erreicht – Nachhol-Lauf: automatische Kategorisierung "
                        "für weitere unbekannte Absender übersprungen. Bereits kategorisierte Mails "
                        "bleiben im Nachhol-Digest erhalten."
                    )
                if not category:
                    continue

            mails.append({
                "from":     from_addr,
                "subject":  subject,
                "body":     body,
                "category": category,
            })
            log.info("Mail übernommen (Nachhol): [%s] %s", category, subject[:60])

        imap.logout()
    except imaplib.IMAP4.error as e:
        log.error("IMAP-Fehler (Nachhol-Modus): %s", e)
        notify_telegram(f"IMAP-Fehler beim Nachhol-Lauf: {e}")
    except Exception as e:
        log.error("Unerwarteter Fehler (Nachhol-Modus): %s", e)
        notify_telegram(f"Unerwarteter Fehler beim Nachhol-Lauf: {e}")

    return mails


def process_mails(mails: list, date_str: str) -> bool:
    try:
        r = requests.post(
            f"{API_BASE}/api/process",
            headers={
                "Authorization": f"Bearer {BEARER_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"date": date_str, "mails": mails},
            timeout=300,
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catchup-days", type=int, default=None,
        help="Einmaliger Nachhol-Lauf: durchsucht [Gmail]/All Mail (rein lesend) statt INBOX, "
             "N Tage zurück, umgeht should_run()",
    )
    args = parser.parse_args()

    log.info("=== Newsletter Fetch gestartet ===")

    if args.catchup_days is None and not should_run():
        sys.exit(0)
    elif args.catchup_days is not None:
        log.info("Nachhol-Modus aktiv: %d Tage zurück, [Gmail]/All Mail", args.catchup_days)

    if not GMAIL_PASSWORD:
        log.error("GMAIL_APP_PASSWORD nicht gesetzt")
        notify_telegram("GMAIL_APP_PASSWORD fehlt in .env")
        sys.exit(1)

    cfg = get_config()
    sender_mapping = cfg.get("senders", {})
    valid_categories = get_valid_categories(cfg)
    cat_prompt = build_category_prompt(cfg)

    if not valid_categories:
        log.error("Keine aktiven Kategorien in Config – Abbruch.")
        notify_telegram("Keine aktiven Kategorien konfiguriert.")
        sys.exit(1)

    date_str = datetime.now().strftime("%Y-%m-%d")
    if args.catchup_days is None:
        mails = fetch_mails(sender_mapping, valid_categories, cat_prompt)
    else:
        mails = fetch_from_all_mail(args.catchup_days, sender_mapping, valid_categories, cat_prompt)

    if not mails:
        log.info("Keine passenden Mails gefunden – kein Digest erstellt.")
        sys.exit(0)

    log.info("%d Mails werden verarbeitet…", len(mails))
    success = process_mails(mails, date_str)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
