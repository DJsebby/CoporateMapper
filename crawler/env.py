"""
Load the repository's .env file into the process environment, once, for
every crawler CLI. Keeps the existing convention (each collector reads its
own API key from os.environ) but removes the need to export it manually
every session.
"""

from __future__ import annotations

from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    from dotenv import load_dotenv

    load_dotenv(_ENV_PATH)
