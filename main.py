import sys
from dataclasses import dataclass

import gi
from streamlink import Streamlink

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib  # noqa: E402

SWITCH_SECONDS = 10


@dataclass
class SwitchState:
    urls: list[str]
    index: int
    player: Gst.Element


def resolve_hls_url(channel: str) -> str:
    session = Streamlink()
    streams = session.streams(f"https://twitch.tv/{channel}")
    stream = streams.get("best")
    if stream is None:
        raise RuntimeError(f"streamlink could not resolve '{channel}'")
    return stream.to_url()


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python main.py <twitch_channel_one> <twitch_channel_two>")
        return 1

    Gst.init(None)

    hls_urls = [resolve_hls_url(sys.argv[1]), resolve_hls_url(sys.argv[2])]
    playbin = Gst.ElementFactory.make("playbin", None)
    if playbin is None:
        raise RuntimeError("failed to create gstreamer playbin")

    playbin.set_property("uri", hls_urls[0])
    playbin.set_state(Gst.State.PLAYING)

    bus = playbin.get_bus()
    if bus is None:
        raise RuntimeError("missing gstreamer bus")

    main_loop = GLib.MainLoop()

    def on_message(_, message):
        msg_type = message.type
        if msg_type == Gst.MessageType.ERROR:
            err, _ = message.parse_error()
            print(f"gstreamer error: {err}")
            main_loop.quit()
        elif msg_type == Gst.MessageType.EOS:
            main_loop.quit()

    bus.add_signal_watch()
    bus.connect("message", on_message)

    state = SwitchState(urls=hls_urls, index=0, player=playbin)

    def switch_stream():
        state.index = (state.index + 1) % len(state.urls)
        next_url = state.urls[state.index]
        state.player.set_state(Gst.State.READY)
        state.player.set_property("uri", next_url)
        state.player.set_state(Gst.State.PLAYING)
        return True

    GLib.timeout_add_seconds(SWITCH_SECONDS, switch_stream)
    main_loop.run()
    playbin.set_state(Gst.State.NULL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
