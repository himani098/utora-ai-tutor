from __future__ import annotations

from collections.abc import Mapping

SECRET_NAMES = ("Gemini API key", "GEMINI_API_KEY")


def resolve_gemini_api_key(
    environment: Mapping[str, str],
    secrets: Mapping[str, object] | None,
) -> str:
    """Resolve the private Gemini key without logging or exposing its value."""
    environment_key = environment.get("GEMINI_API_KEY", "").strip()
    if environment_key:
        return environment_key
    if secrets is None:
        return ""
    for name in SECRET_NAMES:
        value = secrets.get(name, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
