import json
import urllib.request
from dataclasses import dataclass

PACEMAN_LIVE_URL = "https://paceman.gg/api/ars/liveruns"


@dataclass(frozen=True)
class PacemanRun:
    channel: str | None
    nickname: str
    is_hidden: bool
    is_cheated: bool
    last_event_label: str | None
    last_event_time_ms: int | None


_EVENT_LABELS = {
    "rsg.enter_end": "END ENTER",
    "rsg.enter_stronghold": "STRONGHOLD",
    "rsg.first_portal": "BLIND",
    "rsg.enter_nether": "NETHER",
}


def _event_time_ms(event: dict) -> int | None:
    time_value = event.get("igt")
    if time_value is None:
        time_value = event.get("rta")
    if isinstance(time_value, (int, float)):
        return int(time_value)
    return None


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
        last_event_label = None
        last_event_time_ms = None
        event_list = entry.get("eventList") or []
        if isinstance(event_list, list) and event_list:
            event_entries = [event for event in event_list if isinstance(event, dict)]
            if event_entries:
                last_event = event_entries[-1]
                event_id = last_event.get("eventId")
                if isinstance(event_id, str):
                    last_event_time_ms = _event_time_ms(last_event)
                    last_event_label = _label_for_event(
                        event_id,
                        event_entries,
                        last_event_time_ms,
                    )
        runs.append(
            PacemanRun(
                channel=str(channel).strip() if channel else None,
                nickname=nickname,
                is_hidden=bool(entry.get("isHidden")),
                is_cheated=bool(entry.get("isCheated")),
                last_event_label=last_event_label,
                last_event_time_ms=last_event_time_ms,
            )
        )
    return runs
