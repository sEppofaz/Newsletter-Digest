import os, json, logging
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify, request, send_file, abort
from dotenv import dotenv_values
import requests as http_client

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE = Path(__file__).parent
DATA_DIR = BASE / "data" / "digests"
ICONS_DIR = BASE / "icons"
CONFIG_FILE = BASE / "config.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)

_env = dotenv_values(BASE / ".env")
BEARER_TOKEN       = _env.get("BEARER_TOKEN", "")
ANTHROPIC_API_KEY  = _env.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = _env.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = _env.get("TELEGRAM_CHAT_ID", "")

CLAUDE_MODEL_FALLBACK = "claude-haiku-4-5-20251001"
CLAUDE_MODEL = _env.get("CLAUDE_MODEL", CLAUDE_MODEL_FALLBACK)

CAT_NAMES = {
    "ki_tech":   "KI & Tech",
    "finanzen":  "Finanzen",
    "automobil": "Automobil",
    "lokal":     "Lokal",
}

CAT_CONTEXT = {
    "ki_tech":   "KI, Machine Learning, Software-Entwicklung und Technologie",
    "finanzen":  "Finanzmärkte, Wirtschaft, Aktien und Unternehmen",
    "automobil": "Automobil, E-Mobilität, Motorrad und Verkehr",
    "lokal":     "Lokale Nachrichten aus Bayerbach, Hölskofen, Oberköllnbach und Paindlkofen (Niederbayern, Landkreis Dingolfing-Landau)",
}

# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def telegram_alert(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram nicht konfiguriert: %s", msg)
        return
    try:
        http_client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": f"⚠️ [Newsletter-Digest]\n{msg}"},
            timeout=10,
        )
    except Exception as e:
        log.error("Telegram-Alert fehlgeschlagen: %s", e)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {"schedule": {"type": "weekly", "weekday": "sunday"}, "max_archive": 10, "bullet_points": 10, "senders": {}}


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


def require_bearer(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not BEARER_TOKEN or auth != f"Bearer {BEARER_TOKEN}":
            abort(401)
        return f(*args, **kwargs)
    return decorated


def should_run_today() -> bool:
    cfg = load_config()
    schedule = cfg.get("schedule", {"type": "weekly", "weekday": "sunday"})
    today = datetime.now()
    WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6}
    stype = schedule.get("type", "weekly")

    if stype == "daily":
        return True
    if stype == "weekly":
        return today.weekday() == WEEKDAYS.get(schedule.get("weekday", "sunday"), 6)
    if stype == "monthly":
        target_wd = WEEKDAYS.get(schedule.get("weekday", "friday"), 4)
        week_num = int(schedule.get("week", 1))
        first = today.replace(day=1)
        delta = (target_wd - first.weekday()) % 7
        target_date = first + timedelta(days=delta + (week_num - 1) * 7)
        return today.date() == target_date.date()
    return False


def cleanup_old_digests(max_keep: int):
    all_digests = sorted(DATA_DIR.glob("digest_*.json"), reverse=True)
    for old in all_digests[max_keep:]:
        old.unlink()
        log.info("Alten Digest gelöscht: %s", old.name)


# ─── Claude-Integration ──────────────────────────────────────────────────────

def call_claude(category: str, mails: list, bullet_points: int, model: str | None = None) -> str | None:
    if model is None:
        model = CLAUDE_MODEL

    bodies = "\n---\n".join(
        f"Betreff: {m.get('subject', '(kein Betreff)')}\n\n{m.get('body', '')[:3000]}"
        for m in mails
    )
    cat_context = CAT_CONTEXT.get(category, category)
    cat_name = CAT_NAMES.get(category, category)

    system = (
        f"Du bist ein redaktioneller Assistent für den Bereich: {cat_context}.\n"
        f"Du erhältst Newsletter-Inhalte und erstellst daraus eine hochwertige deutschsprachige Zusammenfassung.\n\n"
        f"Format (Markdown):\n"
        f"- Genau {bullet_points} Punkte\n"
        f"- Jeder Punkt: **Kurze prägnante Überschrift** – 2–3 Sätze Erläuterung, sachlich und informativ\n"
        f"- Wichtigstes zuerst, kein Marketing-Sprech\n"
        f"- Letzter Absatz (eigene Zeile, kein Bullet): _Relevanz heute: [1 Satz]_\n"
        f"Antworte ausschließlich auf Deutsch."
    )

    payload = {
        "model": model,
        "max_tokens": 2500,
        "system": system,
        "messages": [{"role": "user", "content": f"Kategorie: {cat_name}\n\nNewsletter-Inhalte:\n{bodies}"}],
    }

    try:
        resp = http_client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=90,
        )

        # Modell-ID ungültig → automatisch Fallback
        if resp.status_code in (400, 404) and (
            "model_not_found" in resp.text or "invalid model" in resp.text.lower()
        ):
            if model != CLAUDE_MODEL_FALLBACK:
                msg = f"Modell '{model}' ungültig → Fallback auf '{CLAUDE_MODEL_FALLBACK}'"
                log.error(msg)
                telegram_alert(msg)
                return call_claude(category, mails, bullet_points, model=CLAUDE_MODEL_FALLBACK)
            else:
                telegram_alert(f"Fallback-Modell '{CLAUDE_MODEL_FALLBACK}' ebenfalls ungültig!")
                return None

        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    except Exception as e:
        err = f"Claude-API-Fehler (Kategorie {category}): {e}"
        log.error(err)
        telegram_alert(err)
        return None


# ─── Icon-Generierung ────────────────────────────────────────────────────────

_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-6 -6 36 36">
  <rect x="-6" y="-6" width="36" height="36" fill="#1e3a5f"/>
  <g stroke="white" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2" y="3" width="13" height="18" rx="1.5"/>
    <path d="M17 7h4v12a2 2 0 0 1-2 2H2"/>
    <path d="M5 8h7M5 12h7M5 16h4"/>
    <path d="M17 7V3"/>
  </g>
</svg>"""


def _generate_icon(size: int, fname: str):
    import cairosvg
    path = ICONS_DIR / fname
    png = cairosvg.svg2png(bytestring=_ICON_SVG.encode(), output_width=size, output_height=size)
    path.write_bytes(png)


def _serve_icon(size: int, fname: str):
    path = ICONS_DIR / fname
    if not path.exists():
        _generate_icon(size, fname)
    return send_file(path, mimetype="image/png")


# ─── Routen ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file(BASE / "index.html")


@app.route("/manifest.json")
def manifest():
    return send_file(BASE / "manifest.json", mimetype="application/manifest+json",
                     max_age=0)


@app.route("/sw.js")
def sw():
    resp = send_file(BASE / "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/icon-192.png")
def icon192():
    return _serve_icon(192, "icon-192.png")


@app.route("/icon-512.png")
def icon512():
    return _serve_icon(512, "icon-512.png")


@app.route("/apple-touch-icon.png")
def apple_icon():
    return _serve_icon(180, "apple-touch-icon.png")


# ─── API ─────────────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    cfg = load_config()
    return jsonify({
        "status": "ok",
        "model": CLAUDE_MODEL,
        "model_fallback": CLAUDE_MODEL_FALLBACK,
        "should_run_today": should_run_today(),
        "digests": len(list(DATA_DIR.glob("digest_*.json"))),
        "schedule": cfg.get("schedule"),
    })


@app.route("/api/should_run")
def api_should_run():
    return jsonify({"run": should_run_today(), "date": datetime.now().strftime("%Y-%m-%d")})


@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
@require_bearer
def api_config_post():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        abort(400)
    cfg = load_config()
    cfg.update(data)
    save_config(cfg)
    log.info("Config aktualisiert")
    return jsonify({"ok": True})


@app.route("/api/process", methods=["POST"])
@require_bearer
def api_process():
    """n8n schickt Mails → Flask ruft Claude auf → Digest gespeichert."""
    data = request.get_json(force=True)
    mails = data.get("mails", [])
    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    if not mails:
        return jsonify({"error": "Keine Mails übergeben"}), 400

    # Nach Kategorie gruppieren
    by_cat: dict[str, list] = {}
    for mail in mails:
        cat = mail.get("category", "sonstige")
        by_cat.setdefault(cat, []).append(mail)

    cfg = load_config()
    bullet_points = int(cfg.get("bullet_points", 10))

    categories_result = {}
    for cat, cat_mails in by_cat.items():
        log.info("Verarbeite Kategorie '%s' (%d Mails)", cat, len(cat_mails))
        summary = call_claude(cat, cat_mails, bullet_points)
        if summary:
            categories_result[cat] = summary

    if not categories_result:
        telegram_alert(f"Digest {date_str}: Keine Zusammenfassungen generiert – alle Kategorien fehlgeschlagen.")
        return jsonify({"error": "Alle Kategorien fehlgeschlagen"}), 500

    digest = {
        "date": date_str,
        "generated_at": datetime.now().isoformat(),
        "categories": categories_result,
        "mail_count": len(mails),
        "cat_count": {cat: len(ms) for cat, ms in by_cat.items()},
    }

    fname = DATA_DIR / f"digest_{date_str}.json"
    fname.write_text(json.dumps(digest, ensure_ascii=False, indent=2))
    log.info("Digest gespeichert: %s", fname.name)
    cleanup_old_digests(int(cfg.get("max_archive", 10)))

    return jsonify({"ok": True, "date": date_str, "categories": list(categories_result.keys())})


@app.route("/api/digest/latest")
def api_digest_latest():
    digests = sorted(DATA_DIR.glob("digest_*.json"), reverse=True)
    if not digests:
        return jsonify({"error": "Noch kein Digest vorhanden"}), 404
    return jsonify(json.loads(digests[0].read_text()))


@app.route("/api/digest/list")
def api_digest_list():
    digests = sorted(DATA_DIR.glob("digest_*.json"), reverse=True)
    return jsonify([d.stem.replace("digest_", "") for d in digests])


@app.route("/api/digest/<date_str>")
def api_digest_by_date(date_str: str):
    if not date_str.replace("-", "").isdigit() or len(date_str) != 10:
        abort(400)
    fname = DATA_DIR / f"digest_{date_str}.json"
    if not fname.exists():
        return jsonify({"error": "Nicht gefunden"}), 404
    return jsonify(json.loads(fname.read_text()))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5006, debug=False)
