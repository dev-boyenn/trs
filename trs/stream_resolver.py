from streamlink import Streamlink


def resolve_hls_url(channel: str, oauth_token: str) -> str:
    session = Streamlink()
    session.set_option("twitch-oauth-token", oauth_token)
    streams = session.streams(f"https://twitch.tv/{channel}")
    stream = streams.get("best")
    if stream is None:
        raise RuntimeError(f"streamlink could not resolve '{channel}'")
    return stream.to_url()


def resolve_channel_urls(channels: list[str], oauth_token: str) -> list[str]:
    urls: list[str] = []
    for channel in channels:
        try:
            urls.append(resolve_hls_url(channel, oauth_token))
        except Exception as exc:
            print(f"stream resolve failed for '{channel}': {exc}")
    return urls
