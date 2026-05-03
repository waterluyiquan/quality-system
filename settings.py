from __future__ import annotations

import json
from pathlib import Path


SETTINGS_FILE = Path("app_settings.json")
DEFAULT_SETTINGS = {
    "source_dir": "docs",
    "export_dir": "exports",
    "db_dir": "db",
}


def load_settings() -> dict[str, str]:
    if not SETTINGS_FILE.exists():
        return DEFAULT_SETTINGS.copy()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_SETTINGS.copy()
    settings = DEFAULT_SETTINGS.copy()
    for key in settings:
        value = str(data.get(key, settings[key])).strip()
        settings[key] = value or settings[key]
    return settings


def save_settings(settings: dict[str, str]) -> None:
    SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ensure_folder(path: str | Path) -> Path:
    folder = Path(path).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    return folder
