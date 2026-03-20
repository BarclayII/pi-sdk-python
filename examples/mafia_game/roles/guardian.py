"""Guardian role — nightly protection (renamed from the original doctor)."""

from typing import Any

ROLE_DESCRIPTION = (
    "You are the **Guardian**. Each night, you choose one player to protect — "
    "that player is immune to all attacks for the night. You may NOT protect "
    "the same person on consecutive nights, and you may NOT protect yourself."
)

PROTECT_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "protect",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "protect": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["protect", "reasoning"],
            "additionalProperties": False,
        },
    },
}


def guardian_prompt(
    alive_players: list[str],
    guardian_name: str,
    last_protected: str | None,
) -> str:
    """Prompt the guardian to choose who to protect tonight."""
    others = [p for p in alive_players if p != guardian_name]
    excluded = []
    if last_protected and last_protected in others:
        others = [p for p in others if p != last_protected]
        excluded.append(last_protected)

    others_str = ", ".join(others)

    parts = [
        "It is night time. As the Guardian, you must choose one player to protect tonight. "
        "That player will be immune to all attacks this night."
    ]

    if excluded:
        parts.append(
            f"\nYou protected {last_protected} last night, so you CANNOT protect them again tonight."
        )

    parts.append(f"\nPlayers you may protect: {others_str}")
    parts.append(
        "\nRead your previous NIGHT_GUARDIAN_NOTES_*.txt files to recall past actions."
    )
    parts.append(
        '\nReturn ONLY valid JSON: {"protect": "<player_name>", "reasoning": "..."}'
    )

    return "\n".join(parts)
