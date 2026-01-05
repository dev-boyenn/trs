# TRS

Minimal Rust app that launches a native Twitch stream player without a webview.

## Prerequisites

- Rust (stable) installed via [rustup](https://rustup.rs/)
- [streamlink](https://streamlink.github.io/) available on your PATH
- [GStreamer](https://gstreamer.freedesktop.org/) runtime installed

## Run

```sh
cargo run -- <twitch_channel>
```

Example:

```sh
cargo run -- ninja
```
