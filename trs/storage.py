import json
from pathlib import Path

from .config import DEFAULT_SAVE_FILE

_DEFAULT_SETTINGS: dict[str, bool] = {
    "paceman_mode": False,
    "include_hidden": False,
    "paceman_fallback": False,
}


def load_saved_state(
    save_file: Path | None = None,
) -> tuple[list[str], dict[str, bool]]:
    target = save_file or DEFAULT_SAVE_FILE
    if not target.exists():
        payload = {"streams": [], "settings": dict(_DEFAULT_SETTINGS)}
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return [], dict(_DEFAULT_SETTINGS)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], dict(_DEFAULT_SETTINGS)
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        streams = []
    settings = payload.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}
    normalized_settings = dict(_DEFAULT_SETTINGS)
    for key in normalized_settings:
        value = settings.get(key, normalized_settings[key])
        normalized_settings[key] = bool(value)
    normalized_streams = [
        str(stream).strip() for stream in streams if str(stream).strip()
    ]
    return normalized_streams, normalized_settings


def save_state(
    streams: list[str],
    settings: dict[str, bool],
    save_file: Path | None = None,
) -> None:
    target = save_file or DEFAULT_SAVE_FILE
    normalized_settings = dict(_DEFAULT_SETTINGS)
    for key in normalized_settings:
        if key in settings:
            normalized_settings[key] = bool(settings[key])
    payload = {"streams": streams, "settings": normalized_settings}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
