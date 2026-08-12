"""Private pairing data for the Vivo AURA Avatar.

This token is deliberately unrelated to the MBBank bridge token. It is stored
locally, never logged, and handed to the phone only through an explicit ADB
configuration intent.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

from core.config import settings

_PATH = settings.ledger_dir / "aura_avatar_pairing.json"
_LOCK = threading.RLock()


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def pairing(path: Path | None = None) -> dict[str, str]:
    """Return and, when needed, create the Avatar-only pairing data."""
    target = path or _PATH
    with _LOCK:
        data = _read(target)
        token = str(data.get("token") or "")
        if not token:
            token = secrets.token_urlsafe(32)
            data = {"version": 1, "token": token}
            _save(data, target)
        return {
            "endpoint": (
                f"http://127.0.0.1:{settings.aura_avatar_lan_port}"
                "/v1/avatar/chat"
            ),
            "token": token,
        }


def token_matches(candidate: str, path: Path | None = None) -> bool:
    expected = pairing(path)["token"]
    return bool(candidate) and hmac.compare_digest(str(candidate), expected)


__all__ = ["pairing", "token_matches"]
