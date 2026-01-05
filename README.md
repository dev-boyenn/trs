# TRS

Minimal Python app that launches a native Twitch stream player without a webview.

## Prerequisites

- Python 3.10+
- Qt Multimedia backend available on your platform
- Python packages: `streamlink`, `PySide6`

## Install

```sh
python -m pip install -r requirements.txt
```

## Run

```sh
$env:TWITCH_OAUTH_TOKEN="3uetne2yjknpr5o64g0os18h2tjtf9"
python main.py <twitch_channel> [twitch_channel ...]
```

Example:

```sh
$env:TWITCH_OAUTH_TOKEN="3uetne2yjknpr5o64g0os18h2tjtf9"
python main.py fulham beefsalad couriway edcrspeedruns
```

The player shows all streams side by side (audio is enabled for the first one).
