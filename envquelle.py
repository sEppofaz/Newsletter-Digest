"""Zugangsdaten und Einstellungen: zuerst die Umgebung, dann die alte `.env`.

Seit 2026-10-02 gehören Passwörter und Token ausschließlich nach
`/etc/pka/secrets.env` (Sicherheitsregel). Dort stehen die Werte dieses Projekts
mit Präfix `NL_` (z. B. `NL_ANTHROPIC_API_KEY`), damit sie keine gleichnamigen
Werte anderer Dienste überschreiben. Die Units laden die Datei per
`EnvironmentFile=/etc/pka/secrets.env`.

Reihenfolge je Name: `NL_<NAME>` aus der Umgebung → `<NAME>` aus der `.env`
(Übergang; die `.env` darf auch fehlen) → Standardwert.
Nach dem Umzug und dem Löschen der `.env` greift nur noch die Umgebung.
"""
import os
from pathlib import Path

from dotenv import dotenv_values

PRAEFIX = "NL_"


class EnvQuelle:
    def __init__(self, env_datei: Path):
        self._datei = dotenv_values(env_datei)  # fehlende Datei → {}

    def get(self, name: str, default: str = "") -> str:
        wert = os.environ.get(PRAEFIX + name)
        if wert:
            return wert
        wert = self._datei.get(name)
        return wert if wert else default
