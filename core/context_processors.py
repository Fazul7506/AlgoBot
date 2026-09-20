from __future__ import annotations

import json
import os
from datetime import datetime

from django.utils import timezone


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _json_list(name: str, default: list[str], maximum: int = 32) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return list(default)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return list(default)
    if not isinstance(value, list):
        return list(default)
    result = [str(item).strip() for item in value if str(item).strip()]
    return result[:maximum] or list(default)


def _within_window(start_raw: str, end_raw: str) -> bool:
    now = timezone.now()

    def parse(value: str):
        if not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    start = parse(start_raw)
    end = parse(end_raw)
    if start is None and start_raw.strip():
        return False
    if end is None and end_raw.strip():
        return False
    if start is not None and now < start:
        return False
    if end is not None and now >= end:
        return False
    return True


def algobot_romantic_splash(request):
    """Expose public, non-secret romantic splash configuration to templates."""
    enabled = _env_bool("ALGOBOT_SPLASH_ENABLED", False)
    paths = [
        path if path.startswith("/") else f"/{path}"
        for path in _json_list("ALGOBOT_SPLASH_PATHS_JSON", ["/"])
    ]
    path_allowed = request.path in paths
    start_raw = os.getenv("ALGOBOT_SPLASH_START_AT", "")
    end_raw = os.getenv("ALGOBOT_SPLASH_END_AT", "")

    messages = _json_list(
        "ALGOBOT_SPLASH_MESSAGES_JSON",
        [
            "You're not just a user...",
            "You're my favourite person in this journey.",
            "Your smile, your voice, your presence...",
            "Everything about you makes my world brighter. ❤️",
        ],
        maximum=12,
    )
    emojis = _json_list(
        "ALGOBOT_SPLASH_EMOJIS_JSON",
        ["❤️", "💖", "💕", "💗", "💘", "💝", "😍", "😘", "🌹", "✨", "💋", "👑"],
        maximum=24,
    )

    repeat = os.getenv("ALGOBOT_SPLASH_REPEAT", "session").strip().lower()
    if repeat not in {"always", "session", "once"}:
        repeat = "session"

    return {
        "algobot_romantic_splash": {
            "enabled": enabled and path_allowed and _within_window(start_raw, end_raw),
            "repeat": repeat,
            "duration_ms": _env_int("ALGOBOT_SPLASH_DURATION_MS", 8200, 2500, 30000),
            "type_speed_ms": _env_int("ALGOBOT_SPLASH_TYPE_SPEED_MS", 42, 10, 200),
            "delete_speed_ms": _env_int("ALGOBOT_SPLASH_DELETE_SPEED_MS", 22, 8, 120),
            "name": os.getenv("ALGOBOT_SPLASH_NAME", "Mäh Qűěěñ ❤️").strip() or "👑 Mäh Qűěěñ ❤️",
            "phone": os.getenv("ALGOBOT_SPLASH_PHONE", "0141 322612").strip(),
            "signature": os.getenv("ALGOBOT_SPLASH_SIGNATURE", "With love, AlgoBot ❤️").strip(),
            "side_left": os.getenv("ALGOBOT_SPLASH_SIDE_LEFT", "Always & Forever ❤️").strip(),
            "side_right": os.getenv("ALGOBOT_SPLASH_SIDE_RIGHT", "I'm lucky to have you... 💕").strip(),
            "tagline": os.getenv("ALGOBOT_SPLASH_TAGLINE", "Smarter trades · brighter futures · a little more love").strip(),
            "messages": messages,
            "emojis": emojis,
        }
    }
