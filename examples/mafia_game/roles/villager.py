"""Villager role — no special abilities."""

from i18n import get_lang

ROLE_DESCRIPTION = (
    "You are a **Villager**. Your goal is to identify and eliminate the Mafia "
    "members through daily votes. You have no special abilities."
)

ROLE_DESCRIPTION_CN = (
    "你是一名**村民**。你的目标是通过白天的投票找出并淘汰狼人。你没有特殊能力。"
)


def get_role_description() -> str:
    return ROLE_DESCRIPTION_CN if get_lang() == "cn" else ROLE_DESCRIPTION
