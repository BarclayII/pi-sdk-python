"""Detective role — nightly investigation."""

from typing import Any

ROLE_DESCRIPTION = (
    "You are the **Detective**. Your goal is to identify Mafia members. Each "
    "night, you can investigate one player to learn if they are Mafia or not. "
    "Use this information carefully during day discussions."
)

INVESTIGATE_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "investigate",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "investigate": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["investigate", "reasoning"],
            "additionalProperties": False,
        },
    },
}


def detective_prompt(alive_players: list[str], detective_name: str) -> str:
    """Prompt the detective to choose who to investigate."""
    others = [p for p in alive_players if p != detective_name]
    others_str = ", ".join(others)
    return f"""It is night time. As the Detective, you may investigate one player to learn if they are Mafia.

Alive players (excluding yourself): {others_str}

Read your previous NIGHT_DETECTIVE_NOTES_*.txt files to recall past investigations.

Return ONLY valid JSON: {{"investigate": "<player_name>", "reasoning": "..."}}"""
