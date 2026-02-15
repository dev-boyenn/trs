from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from pathlib import Path

_LOGGER_NAME = "trs.perf"
_handler: logging.Handler | None = None


def setup_perf_logger(path: Path) -> None:
    global _handler
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if _handler is not None:
        return
    handler = logging.FileHandler(Path(path), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    _handler = handler
    logger.info("event=perf_logger_started path=%s", Path(path).as_posix())


def log_perf(
    event: str,
    duration_ms: float | None = None,
    **fields: object,
) -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        return
    parts = [f"event={_sanitize_value(event)}"]
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms:.2f}")
    for key, value in fields.items():
        parts.append(f"{_sanitize_value(key)}={_sanitize_value(value)}")
    logger.info(" ".join(parts))


@contextmanager
def perf_timer(event: str, **fields: object):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_perf(event, duration_ms=duration_ms, **fields)


def _sanitize_value(value: object) -> str:
    if isinstance(value, (list, tuple, set)):
        return ",".join(_sanitize_value(item) for item in value)
    return str(value).replace(" ", "_")
