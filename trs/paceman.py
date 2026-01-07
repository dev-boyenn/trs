import json
import time
import urllib.request
from dataclasses import dataclass

PACEMAN_LIVE_URL = "https://paceman.gg/api/ars/liveruns"
PACEMAN_PB_URL = "https://twitchgoat-a5vk.vercel.app/paceman/pb?username="
_PB_CACHE_TTL_SEC = 1800
_pb_cache: dict[str, tuple[float, float | None]] = {}


@dataclass(frozen=True)
class PacemanRun:
    channel: str | None
    nickname: str
    is_hidden: bool
    is_cheated: bool
    last_event_id: str | None
    last_event_label: str | None
    last_event_time_ms: int | None
    last_updated_ms: int | None
    pace_score: float | None
    pace_split: str | None
    pace_time_sec: float | None
    pace_estimated_time_sec: float | None
    pb_time_sec: float | None


_EVENT_LABELS = {
    "rsg.enter_end": "END ENTER",
    "rsg.enter_stronghold": "STRONGHOLD",
    "rsg.first_portal": "BLIND",
    "rsg.enter_nether": "NETHER",
}

_DEFAULT_GOOD_SPLITS_SEC = {
    "NETHER": 90,
    "S1": 120,
    "S2": 240,
    "BLIND": 300,
    "STRONGHOLD": 360,
    "END ENTER": 400,
    "FINISH": 600,
}

_SPLIT_ORDER = [
    "NETHER",
    "S1",
    "S2",
    "BLIND",
    "STRONGHOLD",
    "END ENTER",
    "FINISH",
]

_DEFAULT_PROGRESSION_BONUS = {
    "NETHER": -0.2,
    "S1": 0.2,
    "S2": 0.6,
    "BLIND": 0.8,
    "STRONGHOLD": 0.9,
    "END ENTER": 0.95,
    "FINISH": 1.0,
}

_good_splits_sec = dict(_DEFAULT_GOOD_SPLITS_SEC)
_progression_bonus = dict(_DEFAULT_PROGRESSION_BONUS)


def _event_time_ms(event: dict) -> int | None:
    time_value = event.get("igt")
    if time_value is None:
        time_value = event.get("rta")
    if isinstance(time_value, (int, float)):
        return int(time_value)
    return None


def _fetch_pb_seconds(username: str, timeout: float = 4.0) -> float | None:
    if not username:
        return None
    cached = _pb_cache.get(username)
    now = time.time()
    if cached and (now - cached[0]) < _PB_CACHE_TTL_SEC:
        return cached[1]
    request = urllib.request.Request(
        f"{PACEMAN_PB_URL}{username}",
        headers={"User-Agent": "trs"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        _pb_cache[username] = (now, None)
        return None
    pb_value = payload.get("pb") if isinstance(payload, dict) else None
    try:
        pb_seconds = float(pb_value)
    except (TypeError, ValueError):
        pb_seconds = None
    _pb_cache[username] = (now, pb_seconds)
    return pb_seconds


def _find_event_time(event_list: list[dict], event_id: str) -> int | None:
    for event in event_list:
        if event.get("eventId") == event_id:
            return _event_time_ms(event)
    return None


def _label_for_event(
    event_id: str,
    event_list: list[dict],
    event_time_ms: int | None,
) -> str | None:
    if event_id in ("rsg.enter_fortress", "rsg.enter_bastion"):
        fortress_time = _find_event_time(event_list, "rsg.enter_fortress")
        bastion_time = _find_event_time(event_list, "rsg.enter_bastion")
        if fortress_time is None or bastion_time is None:
            return "S1"
        current_time = event_time_ms
        if current_time is None:
            current_time = (
                fortress_time
                if event_id == "rsg.enter_fortress"
                else bastion_time
            )
        other_time = bastion_time if event_id == "rsg.enter_fortress" else fortress_time
        return "S2" if current_time >= other_time else "S1"
    return _EVENT_LABELS.get(event_id)


def _calculate_current_time_ms(last_updated_ms: int | None) -> int:
    if not last_updated_ms:
        return 0
    return max(0, int((time.time() * 1000) - last_updated_ms))


def _get_next_split(current_split: str | None) -> str | None:
    if not current_split:
        return None
    try:
        current_index = _SPLIT_ORDER.index(current_split)
    except ValueError:
        return None
    if current_index == len(_SPLIT_ORDER) - 1:
        return None
    return _SPLIT_ORDER[current_index + 1]


def _adjusted_pace_score(
    split: str | None,
    time_sec: float | None,
    last_updated_ms: int | None,
) -> tuple[float | None, str | None, float | None]:
    if not split or time_sec is None:
        return None, None, None
    good_split = _good_splits_sec.get(split)
    bonus = _progression_bonus.get(split)
    if not good_split or bonus is None:
        return None, None, None
    current_score = (time_sec / good_split) - bonus
    next_split = _get_next_split(split)
    if not next_split or not last_updated_ms:
        return current_score, split, None
    next_good = _good_splits_sec.get(next_split)
    next_bonus = _progression_bonus.get(next_split)
    if not next_good or next_bonus is None:
        return current_score, split, None
    elapsed_ms = _calculate_current_time_ms(last_updated_ms)
    estimated_time_sec = (elapsed_ms / 1000.0) + time_sec
    next_score = (estimated_time_sec / next_good) - next_bonus
    if next_score > current_score:
        return next_score, next_split, estimated_time_sec
    return current_score, split, estimated_time_sec


def set_pace_config(
    good_splits_sec: dict[str, float] | None = None,
    progression_bonus: dict[str, float] | None = None,
) -> None:
    if good_splits_sec:
        normalized: dict[str, float] = {}
        for key, value in good_splits_sec.items():
            try:
                normalized[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        if normalized:
            _good_splits_sec.clear()
            _good_splits_sec.update(normalized)
    if progression_bonus:
        normalized = {}
        for key, value in progression_bonus.items():
            try:
                normalized[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        if normalized:
            _progression_bonus.clear()
            _progression_bonus.update(normalized)


def fetch_live_runs(timeout: float = 8.0) -> list[PacemanRun]:
    request = urllib.request.Request(
        PACEMAN_LIVE_URL,
        headers={"User-Agent": "trs"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        return []
    runs: list[PacemanRun] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        user = entry.get("user") or {}
        channel = user.get("liveAccount")
        nickname = str(entry.get("nickname") or "").strip()
        last_event_id = None
        last_event_label = None
        last_event_time_ms = None
        last_updated_ms = None
        pb_time_sec = _fetch_pb_seconds(nickname) if nickname else None
        event_list = entry.get("eventList") or []
        if isinstance(event_list, list) and event_list:
            event_entries = [event for event in event_list if isinstance(event, dict)]
            if event_entries:
                last_event = event_entries[-1]
                event_id = last_event.get("eventId")
                if isinstance(event_id, str):
                    last_event_id = event_id
                    last_event_time_ms = _event_time_ms(last_event)
                    last_event_label = _label_for_event(
                        event_id,
                        event_entries,
                        last_event_time_ms,
                    )
        last_updated = entry.get("lastUpdated")
        if isinstance(last_updated, (int, float)):
            last_updated_ms = int(last_updated)
        pace_time_sec = (
            (last_event_time_ms / 1000.0)
            if isinstance(last_event_time_ms, int)
            else None
        )
        pace_score, pace_split, pace_estimated_time_sec = _adjusted_pace_score(
            last_event_label,
            pace_time_sec,
            last_updated_ms,
        )
        runs.append(
            PacemanRun(
                channel=str(channel).strip() if channel else None,
                nickname=nickname,
                is_hidden=bool(entry.get("isHidden")),
                is_cheated=bool(entry.get("isCheated")),
                last_event_id=last_event_id,
                last_event_label=last_event_label,
                last_event_time_ms=last_event_time_ms,
                last_updated_ms=last_updated_ms,
                pace_score=pace_score,
                pace_split=pace_split,
                pace_time_sec=pace_time_sec,
                pace_estimated_time_sec=pace_estimated_time_sec,
                pb_time_sec=pb_time_sec,
            )
        )
    return runs
