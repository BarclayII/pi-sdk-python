"""Guardian role — nightly protection (renamed from the original doctor)."""

from typing import Any

from i18n import get_lang

ROLE_DESCRIPTION = (
    "You are the **Guardian**. Each night, you choose one player to protect — "
    "that player is immune to all attacks for the night. You may NOT protect "
    "the same person on consecutive nights, and you may NOT protect yourself."
)

ROLE_DESCRIPTION_CN = (
    "你是**守卫**。每个夜晚，你选择一名玩家进行守护——"
    "该玩家在当晚免疫所有攻击。你不能连续两晚守护同一个人，"
    "也不能守护你自己。"
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


def get_role_description() -> str:
    return ROLE_DESCRIPTION_CN if get_lang() == "cn" else ROLE_DESCRIPTION


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

    if get_lang() == "cn":
        parts = [
            "现在是夜晚。作为守卫，你必须选择一名玩家进行守护。"
            "该玩家在今晚将免疫所有攻击。"
        ]
        if excluded:
            parts.append(f"\n你昨晚守护了 {last_protected}，因此今晚不能再守护他。")
        parts.append(f"\n你可以守护的玩家: {others_str}")
        parts.append("\n请阅读你之前的 NIGHT_GUARDIAN_NOTES_*.txt 文件回忆过去的行动。")
        parts.append('\n仅返回有效JSON: {"protect": "<玩家名>", "reasoning": "..."}')
        return "\n".join(parts)

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
