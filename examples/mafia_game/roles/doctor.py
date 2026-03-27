"""Doctor role — one-time save and one-time poison after seeing the mafia kill."""

from typing import Any

ROLE_DESCRIPTION = (
    "You are the **Doctor**. Each night, after the Detective, Mafia, and Guardian "
    "act simultaneously, you are told who is dead (if anyone). You do not know "
    "whether a Guardian blocked the kill or the Mafia chose not to kill. You have "
    "two one-time abilities: **Save** (revive the killed player) and **Poison** "
    "(immediately kill another player). Each ability can only be used once per "
    "game. You may use both in the same night."
)

DOCTOR_ACTION_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "doctor_action",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "save": {"type": "boolean"},
                "poison": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["save", "poison", "reasoning"],
            "additionalProperties": False,
        },
    },
}


def doctor_prompt(
    killed_player: str | None,
    alive_players: list[str],
    doctor_name: str,
    has_save: bool,
    has_poison: bool,
) -> str:
    """Prompt the doctor to decide whether to save and/or poison."""
    parts = [
        "It is night time. As the Doctor, you have been informed of the Mafia's action.\n"
    ]

    if killed_player:
        parts.append(f"The Mafia killed **{killed_player}** tonight.\n")
    else:
        parts.append("The Mafia failed to kill anyone tonight.\n")

    # Save ability
    if has_save and killed_player:
        parts.append(
            "You still have your **one-time Save** ability. "
            "If you choose to save, the killed player will be revived.\n"
        )
    elif not has_save:
        parts.append("You have already used your Save ability.\n")
    elif not killed_player:
        parts.append(
            "You still have your Save ability, but there is no one to save this night.\n"
        )

    # Poison ability
    if has_poison:
        poison_targets = [p for p in alive_players if p != doctor_name]
        if killed_player and killed_player in poison_targets:
            poison_targets.remove(killed_player)
        targets_str = ", ".join(poison_targets)
        parts.append(
            f"You still have your **one-time Poison** ability. "
            f"You may poison one player to kill them immediately.\n"
            f"Valid poison targets: {targets_str}\n"
        )
    else:
        parts.append("You have already used your Poison ability.\n")

    parts.append(
        "Read your previous NIGHT_DOCTOR_NOTES_*.txt files to recall past actions.\n"
    )

    parts.append(
        'Return ONLY valid JSON: {"save": true/false, "poison": "<player_name>" or "", "reasoning": "..."}\n'
        '- "save": true to use your save (revive the killed player), false to skip\n'
        '- "poison": name of a player to poison, or "" to skip'
    )

    return "\n".join(parts)
