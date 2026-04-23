"""Mafia role — night kill meetings."""

from i18n import get_lang

ROLE_DESCRIPTION = (
    "You are a **Mafia** member. Your goal is to eliminate villagers without "
    "being discovered. During the night, you meet with other Mafia members to "
    "choose a victim (or strategically keep everyone alive). During the day, "
    "blend in and deflect suspicion."
)

ROLE_DESCRIPTION_CN = (
    "你是一名**狼人**。你的目标是在不被发现的情况下淘汰村民。"
    "在夜间，你与其他狼人开会选择要击杀的目标（或者策略性地不杀人）。"
    "在白天，混入村民中并转移嫌疑。"
)


def get_role_description() -> str:
    return ROLE_DESCRIPTION_CN if get_lang() == "cn" else ROLE_DESCRIPTION
