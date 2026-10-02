#!/usr/bin/env python3
"""Offline-Prüfung für envquelle.py:  python3 tests/test_envquelle.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from envquelle import EnvQuelle  # noqa: E402

fehler = []


def pruefe(ok, text, detail=""):
    print(("  ok   " if ok else "  FEHL ") + text + ("" if ok else "  – %s" % detail))
    if not ok:
        fehler.append(text)


with tempfile.TemporaryDirectory() as d:
    env = Path(d) / ".env"
    env.write_text("ANTHROPIC_API_KEY=aus-datei\nLEER=\nNUR_DATEI=datei-wert\nGMAIL_USER=datei@example.org\n")
    for k in [k for k in os.environ if k.startswith("NL_") or k in ("ANTHROPIC_API_KEY", "NUR_UMGEBUNG")]:
        del os.environ[k]
    q = EnvQuelle(env)
    pruefe(q.get("NUR_DATEI") == "datei-wert", "Wert nur in der .env wird gelesen")
    pruefe(q.get("GIBTS_NICHT", "std") == "std", "Standardwert, wenn nirgends vorhanden")
    pruefe(q.get("GIBTS_NICHT") == "", "ohne Standardwert leerer String")
    pruefe(q.get("LEER", "std") == "std", "leerer Wert in der .env → Standardwert")
    os.environ["NL_ANTHROPIC_API_KEY"] = "aus-umgebung"
    pruefe(q.get("ANTHROPIC_API_KEY") == "aus-umgebung", "NL_-Wert aus der Umgebung hat Vorrang vor der .env")
    os.environ["NL_ANTHROPIC_API_KEY"] = ""
    pruefe(q.get("ANTHROPIC_API_KEY") == "aus-datei", "leerer NL_-Wert fällt auf die .env zurück")
    os.environ["NUR_UMGEBUNG"] = "fremd"
    pruefe(q.get("NUR_UMGEBUNG", "std") == "std", "Variable OHNE Präfix wird ignoriert (kein Überschreiben durch fremde Dienste)")
    os.environ["ANTHROPIC_API_KEY"] = "anderer-dienst"
    os.environ["NL_ANTHROPIC_API_KEY"] = ""
    pruefe(q.get("ANTHROPIC_API_KEY") == "aus-datei", "gleichnamiger Wert eines anderen Dienstes wird nicht übernommen")
    q2 = EnvQuelle(Path(d) / "gibt_es_nicht.env")
    pruefe(q2.get("X", "std") == "std", "fehlende .env wirft nicht")
    os.environ["NL_GMAIL_USER"] = "umgebung@example.org"
    pruefe(q2.get("GMAIL_USER", "std") == "umgebung@example.org", "ohne .env: nur Umgebung genügt (Zielzustand nach dem Umzug)")

print("\n%s" % ("ALLE PRÜFUNGEN BESTANDEN" if not fehler else "%d FEHLGESCHLAGEN" % len(fehler)))
sys.exit(1 if fehler else 0)
