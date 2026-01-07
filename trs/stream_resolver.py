import time

from streamlink import Streamlink

_CACHE_TTL_SECONDS = 120
_URL_CACHE: dict[tuple[str, str], tuple[str, float]] = {}
_SESSION = Streamlink()


def _cache_key(channel: str, oauth_token: str) -> tuple[str, str]:
    return channel.lower(), oauth_token


def _get_cached_url(channel: str, oauth_token: str) -> str | None:
    key = _cache_key(channel, oauth_token)
    cached = _URL_CACHE.get(key)
    if not cached:
        return None
    url, timestamp = cached
    if time.time() - timestamp > _CACHE_TTL_SECONDS:
        return None
    return url


def resolve_hls_url(channel: str, oauth_token: str) -> str:
    print(f"resolving twitch channel '{channel}', oauth token = '{oauth_token[:4]}...'")
    _SESSION.set_option("http-headers", {"Authorization": f"OAuth {oauth_token}"})
    streams = _SESSION.streams(f"https://twitch.tv/{channel}")
    stream = streams.get("best")
    if stream is None:
        raise RuntimeError(f"streamlink could not resolve '{channel}'")
    url = stream.to_url()
    _URL_CACHE[_cache_key(channel, oauth_token)] = (url, time.time())
    return url


def resolve_channel_urls(channels: list[str], oauth_token: str) -> list[str]:
    urls: list[str] = []
    for channel in channels:
        try:
            cached = _get_cached_url(channel, oauth_token)
            if cached:
                urls.append(cached)
                continue
            urls.append(resolve_hls_url(channel, oauth_token))
        except Exception as exc:
            print(f"stream resolve failed for '{channel}': {exc}")
    return urls
