# TRS

Minimal Python app that launches a native Twitch stream player without a webview.

## Prerequisites

- Python 3.10+
- [GStreamer](https://gstreamer.freedesktop.org/) runtime installed
- Python packages: `streamlink`, `PyGObject`

## Install

```sh
python -m pip install -r requirements.txt
```

## Run

```sh
python main.py <twitch_channel_one> <twitch_channel_two>
```

Example:

```sh
python main.py ninja shroud
```

The player switches between the two streams every 10 seconds.
