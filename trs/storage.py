import json
from pathlib import Path

from .config import DEFAULT_SAVE_FILE

_DEFAULT_SETTINGS: dict[str, object] = {
    "paceman_mode": False,
    "include_hidden": False,
    "paceman_fallback": False,
    "paceman_event": "",
    "paceman_hide_offline": False,
    "manual_grid_columns": 0,
    "manual_grid_rows": 0,
    "overlay_enabled": True,
    "pace_sort_enabled": True,
    "pace_autofocus_enabled": True,
    "pace_autofocus_threshold": 0.6,
    "pace_paceman_enabled": False,
    "pace_paceman_threshold": 0.8,
    "max_stream_quality": 720,
    "pace_good_splits": {
        "NETHER": 90,
        "S1": 120,
        "S2": 240,
        "BLIND": 300,
        "STRONGHOLD": 360,
        "END ENTER": 400,
        "FINISH": 600,
    },
    "pace_progression_bonus": {
        "NETHER": -0.2,
        "S1": 0.2,
        "S2": 0.6,
        "BLIND": 0.8,
        "STRONGHOLD": 0.9,
        "END ENTER": 0.95,
        "FINISH": 1.0,
    },
}

_BOOL_KEYS = {
    "paceman_mode",
    "include_hidden",
    "paceman_fallback",
    "paceman_hide_offline",
    "overlay_enabled",
    "pace_sort_enabled",
    "pace_autofocus_enabled",
    "pace_paceman_enabled",
}

_FLOAT_KEYS = {"pace_autofocus_threshold", "pace_paceman_threshold"}

_INT_KEYS = {"max_stream_quality", "manual_grid_columns", "manual_grid_rows"}

_DICT_FLOAT_KEYS = {"pace_good_splits", "pace_progression_bonus"}

_STRING_KEYS = {"paceman_event"}


def _normalize_settings(settings: dict) -> dict[str, object]:
    normalized: dict[str, object] = dict(_DEFAULT_SETTINGS)
    for key in _BOOL_KEYS:
        value = settings.get(key, normalized[key])
        normalized[key] = bool(value)
    for key in _FLOAT_KEYS:
        value = settings.get(key, normalized[key])
        try:
            normalized[key] = float(value)
        except (TypeError, ValueError):
            normalized[key] = float(_DEFAULT_SETTINGS[key])
    for key in _INT_KEYS:
        value = settings.get(key, normalized[key])
        try:
            normalized[key] = max(0, int(value))
        except (TypeError, ValueError):
            normalized[key] = max(0, int(_DEFAULT_SETTINGS[key]))
    for key in _STRING_KEYS:
        value = settings.get(key, normalized[key])
        if value is None:
            normalized[key] = ""
        else:
            normalized[key] = str(value).strip()
    for key in _DICT_FLOAT_KEYS:
        default_map = _DEFAULT_SETTINGS[key]
        value = settings.get(key, default_map)
        if not isinstance(value, dict):
            normalized[key] = dict(default_map)
            continue
        merged: dict[str, float] = {}
        for split_key, default_val in default_map.items():
            candidate = value.get(split_key, default_val)
            try:
                merged[str(split_key)] = float(candidate)
            except (TypeError, ValueError):
                merged[str(split_key)] = float(default_val)
        normalized[key] = merged
    return normalized


def load_saved_state(
    save_file: Path | None = None,
) -> tuple[list[str], dict[str, object]]:
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
    normalized_settings = _normalize_settings(settings)
    normalized_streams = [
        str(stream).strip() for stream in streams if str(stream).strip()
    ]
    if normalized_settings != settings:
        payload = {"streams": normalized_streams, "settings": normalized_settings}
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return normalized_streams, normalized_settings


def save_state(
    streams: list[str],
    settings: dict[str, object],
    save_file: Path | None = None,
) -> None:
    target = save_file or DEFAULT_SAVE_FILE
    normalized_settings = _normalize_settings(settings)
    payload = {"streams": streams, "settings": normalized_settings}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
