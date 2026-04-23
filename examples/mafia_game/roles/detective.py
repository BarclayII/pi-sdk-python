"""Detective role — nightly investigation."""

from typing import Any

from i18n import get_lang

ROLE_DESCRIPTION = (
    "You are the **Detective**. Your goal is to identify Mafia members. Each "
    "night, you can investigate one player to learn if they are Mafia or not. "
    "Use this information carefully during day discussions."
)

ROLE_DESCRIPTION_CN = (
    "你是**预言家**。你的目标是找出狼人。每个夜晚，你可以查验一名玩家，"
    "得知其是否是狼人。请在白天讨论中谨慎使用这些信息。"
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


def get_role_description() -> str:
    return ROLE_DESCRIPTION_CN if get_lang() == "cn" else ROLE_DESCRIPTION


def detective_prompt(alive_players: list[str], detective_name: str) -> str:
    """Prompt the detective to choose who to investigate."""
    others = [p for p in alive_players if p != detective_name]
    others_str = ", ".join(others)
    if get_lang() == "cn":
        return f"""现在是夜晚。作为预言家，你可以查验一名玩家，得知其是否是狼人。

存活玩家（不含你自己）: {others_str}

请阅读你之前的 NIGHT_DETECTIVE_NOTES_*.txt 文件回忆过去的查验结果。

仅返回有效JSON: {{"investigate": "<玩家名>", "reasoning": "..."}}"""
    return f"""It is night time. As the Detective, you may investigate one player to learn if they are Mafia.

Alive players (excluding yourself): {others_str}

Read your previous NIGHT_DETECTIVE_NOTES_*.txt files to recall past investigations.

Return ONLY valid JSON: {{"investigate": "<player_name>", "reasoning": "..."}}"""
