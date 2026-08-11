import json, re
from io import BytesIO
from pathlib import Path

import requests
from dotenv import dotenv_values

import costs

BASE = Path(__file__).parent
_env = dotenv_values(BASE / ".env")

ANTHROPIC_API_KEY = _env.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = _env.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
OPENAI_API_KEY = _env.get("OPENAI_API_KEY", "")
DROPBOX_APP_KEY = _env.get("DROPBOX_APP_KEY", "")
DROPBOX_APP_SECRET = _env.get("DROPBOX_APP_SECRET", "")
DROPBOX_REFRESH_TOKEN = _env.get("DROPBOX_REFRESH_TOKEN", "")

VOICE_MALE = "onyx"
VOICE_FEMALE = "nova"


def _build_digest_text(digest: dict, cat_map: dict) -> str:
    parts = []
    for cat_id, text in digest.get("categories", {}).items():
        name = cat_map.get(cat_id, {}).get("name", cat_id)
        parts.append(f"## {name}\n{text}")
    return "\n\n".join(parts)


def generate_script(digest: dict, cat_map: dict) -> list[dict]:
    """Claude-Call: erzeugt Zwei-Sprecher-Dialogskript aus dem Digest-Text."""
    digest_text = _build_digest_text(digest, cat_map)

    system = (
        "Du erstellst das Skript für einen deutschsprachigen Zwei-Personen-Podcast, "
        "der einen Newsletter-Digest vorstellt.\n"
        "WICHTIG: Der Podcast muss VOLLSTÄNDIG sein – jeder einzelne Punkt aus jeder Kategorie "
        "des Digests muss vorkommen, keine Auswahl/Kürzung. Ausnahme: Enthält eine Kategorie "
        "keinen echten Nachrichteninhalt (z.B. nur eine Fehlermeldung/Entschuldigung statt "
        "Stichpunkten), lasse diese Kategorie komplett weg.\n"
        "Sprecher A (männlich) moderiert, kündigt jeden Punkt kurz launig an und leitet beim "
        "Wechsel auf eine neue Kategorie kurz über.\n"
        "Sprecher B (weiblich) erläutert den Inhalt in 2-3 natürlich gesprochenen Sätzen "
        "(frei formuliert wie in einem echten Gespräch, kein Vorlesen von Stichpunkten).\n"
        "Beginne mit einer kurzen Begrüßung durch Sprecher A, ende mit einer kurzen Verabschiedung.\n"
        "Antworte AUSSCHLIESSLICH mit einem JSON-Array, keine Erklärungen, kein Markdown-Codeblock:\n"
        '[{"speaker": "A", "text": "..."}, {"speaker": "B", "text": "..."}, ...]'
    )

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": 8000,
            "system": system,
            "messages": [{"role": "user", "content": digest_text}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    resp_json = resp.json()
    usage = resp_json.get("usage", {})

    raw = resp_json["content"][0]["text"].strip()
    raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.MULTILINE).strip()
    script = json.loads(raw)

    costs.record_call(
        CLAUDE_MODEL, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
        context="podcast:script",
    )
    return script


def synthesize_audio(script: list[dict]) -> bytes:
    """OpenAI TTS pro Zeile, Zusammenführung per pydub."""
    from pydub import AudioSegment

    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=300)
    total_chars = 0

    for line in script:
        voice = VOICE_MALE if line.get("speaker") == "A" else VOICE_FEMALE
        text = line.get("text", "")
        total_chars += len(text)

        resp = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": "tts-1", "voice": voice, "input": text, "response_format": "mp3"},
            timeout=60,
        )
        resp.raise_for_status()
        segment = AudioSegment.from_file(BytesIO(resp.content), format="mp3")
        combined += segment + silence

    costs.record_tts_call(total_chars, context="podcast:tts")

    buf = BytesIO()
    combined.export(buf, format="mp3")
    return buf.getvalue()


def _dropbox_client():
    import dropbox
    return dropbox.Dropbox(
        oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
        app_key=DROPBOX_APP_KEY,
        app_secret=DROPBOX_APP_SECRET,
    )


def upload_to_dropbox(date_str: str, audio_bytes: bytes, script: list[dict]) -> dict:
    import dropbox
    dbx = _dropbox_client()
    audio_path = f"/podcast_{date_str}.mp3"
    script_path = f"/podcast_{date_str}_skript.json"
    dbx.files_upload(audio_bytes, audio_path, mode=dropbox.files.WriteMode.overwrite)
    dbx.files_upload(
        json.dumps(script, ensure_ascii=False, indent=2).encode(),
        script_path, mode=dropbox.files.WriteMode.overwrite,
    )
    return {"audio_path": audio_path, "script_path": script_path}


def download_audio(dropbox_path: str) -> bytes:
    dbx = _dropbox_client()
    _, resp = dbx.files_download(dropbox_path)
    return resp.content


def generate_podcast(date_str: str, digest: dict, cat_map: dict) -> dict:
    script = generate_script(digest, cat_map)
    audio_bytes = synthesize_audio(script)
    paths = upload_to_dropbox(date_str, audio_bytes, script)
    return {**paths, "script": script}
