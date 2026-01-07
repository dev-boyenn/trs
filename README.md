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
$env:TWITCH_OAUTH_TOKEN="your_oauth_token"
python main.py
```

Linux/macOS:

```sh
export TWITCH_OAUTH_TOKEN="your_oauth_token"
python main.py
```

The app starts with the player window plus a control panel. Use the control
panel to add/remove streams and toggle Paceman settings. Streams and settings
are saved in `save.json`, so the next launch restores them.

The player shows all streams side by side (audio is enabled for the first one).
