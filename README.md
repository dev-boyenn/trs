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

## Twitch Authentication

To get your personal OAuth token from Twitch:

1. Open Twitch.tv in your browser and log in.
2. Open developer tools (F12 or Ctrl+Shift+I), then go to the Console tab.
3. Run this JavaScript snippet to read the `auth-token` cookie:

```js
document.cookie.split("; ").find(item=>item.startsWith("auth-token="))?.split("=")[1]
```

Copy the resulting 30-character alphanumeric string (no quotes) and use it as
`TWITCH_OAUTH_TOKEN`.
