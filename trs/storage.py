import json
from pathlib import Path

from .config import DEFAULT_SAVE_FILE


def load_saved_streams(save_file: Path | None = None) -> list[str]:
    target = save_file or DEFAULT_SAVE_FILE
    if not target.exists():
        target.write_text(json.dumps({"streams": []}, indent=2), encoding="utf-8")
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        return []
    return [str(stream).strip() for stream in streams if str(stream).strip()]


def save_streams(streams: list[str], save_file: Path | None = None) -> None:
    target = save_file or DEFAULT_SAVE_FILE
    target.write_text(json.dumps({"streams": streams}, indent=2), encoding="utf-8")
