import os

from .config import TOKEN_ENV_VAR


def get_oauth_token() -> str:
    token = os.environ.get(TOKEN_ENV_VAR, "").strip()
    if not token:
        print(f"missing required auth token: set {TOKEN_ENV_VAR}")
        raise SystemExit(2)
    return token
