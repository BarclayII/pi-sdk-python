"""Doctor role — one-time save and one-time poison after seeing the mafia kill."""

from typing import Any

from i18n import get_lang

ROLE_DESCRIPTION = (
    "You are the **Doctor**. Each night, after the Detective, Mafia, and Guardian "
    "act simultaneously, you are told who is dead (if anyone). You do not know "
    "whether a Guardian blocked the kill or the Mafia chose not to kill. You have "
    "two one-time abilities: **Save** (revive the killed player) and **Poison** "
    "(immediately kill another player). Each ability can only be used once per "
    "game. You may use both in the same night."
)

ROLE_DESCRIPTION_CN = (
    "你是**女巫**。每个夜晚，在预言家、狼人和守卫同时行动之后，"
    "你会被告知谁死了（如果有人死的话）。你不知道是守卫挡刀了还是狼人选择不杀人。"
    "你有两个一次性技能：**解药**（救活被杀的玩家）和**毒药**（立即毒杀另一名玩家）。"
    "每个技能每局游戏只能使用一次。你可以在同一个夜晚同时使用两个技能。"
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


def get_role_description() -> str:
    return ROLE_DESCRIPTION_CN if get_lang() == "cn" else ROLE_DESCRIPTION


def doctor_prompt(
    killed_player: str | None,
    alive_players: list[str],
    doctor_name: str,
    has_save: bool,
    has_poison: bool,
) -> str:
    """Prompt the doctor to decide whether to save and/or poison."""
    if get_lang() == "cn":
        return _doctor_prompt_cn(
            killed_player, alive_players, doctor_name, has_save, has_poison
        )
    return _doctor_prompt_en(
        killed_player, alive_players, doctor_name, has_save, has_poison
    )


def _doctor_prompt_en(
    killed_player: str | None,
    alive_players: list[str],
    doctor_name: str,
    has_save: bool,
    has_poison: bool,
) -> str:
    parts = [
        "It is night time. As the Doctor, you have been informed of the Mafia's action.\n"
    ]

    if killed_player:
        parts.append(f"The Mafia killed **{killed_player}** tonight.\n")
    else:
        parts.append("The Mafia failed to kill anyone tonight.\n")

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


def _doctor_prompt_cn(
    killed_player: str | None,
    alive_players: list[str],
    doctor_name: str,
    has_save: bool,
    has_poison: bool,
) -> str:
    parts = ["现在是夜晚。作为女巫，你已被告知狼人的行动结果。\n"]

    if killed_player:
        parts.append(f"狼人今晚击杀了 **{killed_player}**。\n")
    else:
        parts.append("狼人今晚没有成功击杀任何人。\n")

    if has_save and killed_player:
        parts.append("你还有**一次性解药**。如果你选择使用解药，被杀的玩家将被救活。\n")
    elif not has_save:
        parts.append("你已经使用过解药了。\n")
    elif not killed_player:
        parts.append("你还有解药，但今晚没有人需要被救。\n")

    if has_poison:
        poison_targets = [p for p in alive_players if p != doctor_name]
        if killed_player and killed_player in poison_targets:
            poison_targets.remove(killed_player)
        targets_str = ", ".join(poison_targets)
        parts.append(
            f"你还有**一次性毒药**。你可以毒杀一名玩家使其立即死亡。\n"
            f"可选毒药目标: {targets_str}\n"
        )
    else:
        parts.append("你已经使用过毒药了。\n")

    parts.append("请阅读你之前的 NIGHT_DOCTOR_NOTES_*.txt 文件回忆过去的行动。\n")

    parts.append(
        '仅返回有效JSON: {"save": true/false, "poison": "<玩家名>" or "", "reasoning": "..."}\n'
        '- "save": true 表示使用解药（救活被杀的玩家），false 表示不使用\n'
        '- "poison": 要毒杀的玩家名，或 "" 表示不使用'
    )

    return "\n".join(parts)
