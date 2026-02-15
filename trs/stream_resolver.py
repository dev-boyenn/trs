import time
from dataclasses import dataclass

from streamlink import Streamlink

from .perf_log import log_perf, perf_timer

_CACHE_TTL_SECONDS = 120
_OFFLINE_CACHE_TTL_SECONDS = 600
_URL_CACHE: dict[tuple[str, str, int], tuple[str, float]] = {}
_NEGATIVE_CACHE: dict[tuple[str, str], float] = {}
_SESSION = Streamlink()


@dataclass(frozen=True)
class StreamEntry:
    channel: str
    url: str


def _cache_key(
    channel: str,
    oauth_token: str,
    max_quality: int | None,
) -> tuple[str, str, int]:
    return channel.lower(), oauth_token, max_quality or -1


def _neg_cache_key(channel: str, oauth_token: str) -> tuple[str, str]:
    return channel.lower(), oauth_token


def _get_cached_url(
    channel: str,
    oauth_token: str,
    max_quality: int | None,
) -> str | None:
    key = _cache_key(channel, oauth_token, max_quality)
    cached = _URL_CACHE.get(key)
    if not cached:
        return None
    url, timestamp = cached
    if time.time() - timestamp > _CACHE_TTL_SECONDS:
        _URL_CACHE.pop(key, None)
        return None
    return url


def _get_negative_cache(channel: str, oauth_token: str) -> bool:
    key = _neg_cache_key(channel, oauth_token)
    timestamp = _NEGATIVE_CACHE.get(key)
    if timestamp is None:
        return False
    if time.time() - timestamp > _OFFLINE_CACHE_TTL_SECONDS:
        _NEGATIVE_CACHE.pop(key, None)
        return False
    return True


def _prune_url_cache(now: float | None = None) -> None:
    now = time.time() if now is None else now
    expired: list[tuple[str, str, int]] = []
    for key, (_, timestamp) in _URL_CACHE.items():
        if now - timestamp > _CACHE_TTL_SECONDS:
            expired.append(key)
    for key in expired:
        _URL_CACHE.pop(key, None)


def _prune_negative_cache(now: float | None = None) -> None:
    now = time.time() if now is None else now
    expired: list[tuple[str, str]] = []
    for key, timestamp in _NEGATIVE_CACHE.items():
        if now - timestamp > _OFFLINE_CACHE_TTL_SECONDS:
            expired.append(key)
    for key in expired:
        _NEGATIVE_CACHE.pop(key, None)


def _mark_negative(channel: str, oauth_token: str) -> None:
    _NEGATIVE_CACHE[_neg_cache_key(channel, oauth_token)] = time.time()


def _clear_negative(channel: str, oauth_token: str) -> None:
    _NEGATIVE_CACHE.pop(_neg_cache_key(channel, oauth_token), None)


def resolve_hls_url(
    channel: str,
    oauth_token: str,
    max_quality: int | None = None,
) -> str:
    print(f"resolving twitch channel '{channel}', oauth token = '{oauth_token[:4]}...'")
    _SESSION.set_option("http-headers", {"Authorization": f"OAuth {oauth_token}"})
    with perf_timer("stream_resolver.streams", channel=channel):
        streams = _SESSION.streams(f"https://twitch.tv/{channel}")
    stream = _select_stream(streams, max_quality)
    if stream is None:
        log_perf("stream_resolver.best_missing", channel=channel)
        raise RuntimeError(f"streamlink could not resolve '{channel}'")
    with perf_timer("stream_resolver.to_url", channel=channel):
        url = stream.to_url()
    _URL_CACHE[_cache_key(channel, oauth_token, max_quality)] = (
        url,
        time.time(),
    )
    return url


def _select_stream(
    streams: dict[str, object],
    max_quality: int | None,
) -> object | None:
    if not streams:
        return None
    if max_quality is None:
        return streams.get("best") or streams.get("worst")
    candidates: list[tuple[int, int, str]] = []
    for name in streams.keys():
        height = _parse_quality_height(name)
        if height is None or height > max_quality:
            continue
        is_60 = 1 if "60" in name else 0
        candidates.append((height, is_60, name))
    if candidates:
        _, _, selected_name = max(candidates)
        return streams.get(selected_name)
    return streams.get("best") or streams.get("worst")


def _parse_quality_height(name: str) -> int | None:
    digits = []
    for ch in name:
        if ch.isdigit():
            digits.append(ch)
        elif digits:
            break
    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


def resolve_channel_urls(
    channels: list[str],
    oauth_token: str,
    max_quality: int | None = None,
) -> list[StreamEntry]:
    urls: list[StreamEntry] = []
    _prune_url_cache()
    _prune_negative_cache()
    for channel in channels:
        try:
            cached = _get_cached_url(channel, oauth_token, max_quality)
            if cached:
                log_perf("stream_resolver.cache_hit", channel=channel)
                urls.append(StreamEntry(channel=channel, url=cached))
                continue
            if _get_negative_cache(channel, oauth_token):
                log_perf("stream_resolver.offline_cache_hit", channel=channel)
                continue
            log_perf("stream_resolver.cache_miss", channel=channel)
            with perf_timer("stream_resolver.resolve_hls_url", channel=channel):
                url = resolve_hls_url(channel, oauth_token, max_quality)
            _clear_negative(channel, oauth_token)
            urls.append(StreamEntry(channel=channel, url=url))
        except Exception as exc:
            _mark_negative(channel, oauth_token)
            log_perf(
                "stream_resolver.resolve_failed",
                channel=channel,
                error=type(exc).__name__,
            )
            print(f"stream resolve failed for '{channel}': {exc}")
    return urls
