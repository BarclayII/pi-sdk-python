"""Internationalization support for the Mafia game.

Usage:
    from i18n import set_lang, t, role_name

    set_lang("cn")                        # switch to Chinese
    t("killed_by_mafia", "alice", "mafia")  # interpolated string
    role_name("mafia")                     # "狼人"
"""

_lang: str = "en"


def set_lang(lang: str) -> None:
    global _lang
    if lang not in ("en", "cn"):
        raise ValueError(f"Unsupported language: {lang}. Use 'en' or 'cn'.")
    _lang = lang


def get_lang() -> str:
    return _lang


# ---------------------------------------------------------------------------
# Role display names
# ---------------------------------------------------------------------------
_ROLE_NAMES = {
    "en": {
        "villager": "Villager",
        "mafia": "Mafia",
        "detective": "Detective",
        "doctor": "Doctor",
        "guardian": "Guardian",
        "mayor": "Mayor",
    },
    "cn": {
        "villager": "村民",
        "mafia": "狼人",
        "detective": "预言家",
        "doctor": "女巫",
        "guardian": "守卫",
        "mayor": "警长",
    },
}


def role_name(role_key: str) -> str:
    """Get the display name for a role in the current language."""
    return _ROLE_NAMES[_lang].get(role_key, role_key.capitalize())


# ---------------------------------------------------------------------------
# Winner labels
# ---------------------------------------------------------------------------
_WINNER_LABELS = {
    "en": {"village": "Village", "mafia": "Mafia"},
    "cn": {"village": "好人阵营", "mafia": "狼人阵营"},
}


def winner_label(winner: str) -> str:
    return _WINNER_LABELS[_lang].get(winner, winner)


# ---------------------------------------------------------------------------
# Translation strings
# ---------------------------------------------------------------------------
_STRINGS = {
    # --- orchestrator.py ---
    "mayor_vote": {
        "en": "--- MAYOR VOTE ---",
        "cn": "--- 警长投票 ---",
    },
    "mayor_dying_successor": {
        "en": "Mayor {} is dying — appointing successor",
        "cn": "警长 {} 即将死亡 — 正在指定继任者",
    },
    "killed_by_mafia": {
        "en": "{} was killed by the Mafia during the night. Their role was: {}.",
        "cn": "{} 在夜间被狼人击杀。其角色为: {}。",
    },
    "killed_by_poison": {
        "en": "{} was found dead from poisoning during the night. Their role was: {}.",
        "cn": "{} 在夜间被女巫毒杀身亡。其角色为: {}。",
    },
    "no_deaths": {
        "en": "No one died during the night.",
        "cn": "夜间无人死亡。",
    },
    "voting": {
        "en": "--- VOTING ---",
        "cn": "--- 投票 ---",
    },
    "guardian_saved": {
        "en": "Guardian saved {} from the Mafia!",
        "cn": "守卫救下了 {}，使其免于狼人毒手！",
    },
    "doctor_saved": {
        "en": "Doctor revived {}!",
        "cn": "女巫救活了 {}！",
    },
    "no_day_meeting": {
        "en": "(no day meeting this round)",
        "cn": "(本轮无白天会议)",
    },
    "eliminated_result": {
        "en": "Eliminated: {}. Their role was: {}.",
        "cn": "淘汰: {}。其角色为: {}。",
    },
    "no_elimination": {
        "en": "No one was eliminated.",
        "cn": "无人被淘汰。",
    },
    # --- meeting.py ---
    "meeting_transcript": {
        "en": "=== Meeting Transcript ===",
        "cn": "=== 会议记录 ===",
    },
    "mayor_vote_header": {
        "en": "=== Mayor Vote ===",
        "cn": "=== 警长投票 ===",
    },
    "elected_mayor_result": {
        "en": "Elected Mayor: {}",
        "cn": "当选警长: {}",
    },
    "elected_mayor_tie": {
        "en": "Elected Mayor: no one (tie)",
        "cn": "当选警长: 无 (平票)",
    },
    "mafia_vote_header": {
        "en": "=== Mafia Vote ===",
        "cn": "=== 狼人投票 ===",
    },
    "mafia_night_decision": {
        "en": "=== Night {} - Mafia Decision ===",
        "cn": "=== 第{}夜 - 狼人决策 ===",
    },
    "day_vote_header": {
        "en": "=== Day Vote ===",
        "cn": "=== 白天投票 ===",
    },
    "target_result": {
        "en": "Target: {}",
        "cn": "目标: {}",
    },
    "target_no_kill": {
        "en": "Target: no kill",
        "cn": "目标: 不击杀",
    },
    # --- investigation results ---
    "investigation_result_mafia": {
        "en": "Result: {} is a MAFIA member.",
        "cn": "查验结果: {} 是狼人。",
    },
    "investigation_result_not_mafia": {
        "en": "Result: {} is NOT Mafia.",
        "cn": "查验结果: {} 不是狼人。",
    },
    "investigation_failed": {
        "en": "Night {}: Investigation failed (invalid target).",
        "cn": "第{}夜: 查验失败 (无效目标)。",
    },
    "night_investigation_header": {
        "en": "Night {} Investigation:",
        "cn": "第{}夜 查验:",
    },
    "you_investigated": {
        "en": "You investigated {}.",
        "cn": "你查验了 {}。",
    },
    # --- guardian results ---
    "you_protected": {
        "en": "You protected {} tonight.",
        "cn": "你今晚守护了 {}。",
    },
    "invalid_protect_target": {
        "en": "Invalid target '{}'. No one was protected.",
        "cn": "无效目标 '{}'。无人被守护。",
    },
    "guardian_decision_failed": {
        "en": "Decision failed (invalid response).",
        "cn": "决策失败 (无效回应)。",
    },
    # --- doctor results ---
    "used_save": {
        "en": "You used your Save ability to revive {}.",
        "cn": "你使用了解药，救活了 {}。",
    },
    "save_already_used": {
        "en": "You tried to save but already used your Save ability.",
        "cn": "你尝试使用解药，但解药已经用过了。",
    },
    "save_no_target": {
        "en": "You tried to save but no one was killed.",
        "cn": "你尝试使用解药，但无人被杀。",
    },
    "used_poison": {
        "en": "You used your Poison ability on {}.",
        "cn": "你对 {} 使用了毒药。",
    },
    "invalid_poison_target": {
        "en": "Invalid poison target '{}'. Poison not used.",
        "cn": "无效的毒药目标 '{}'。毒药未使用。",
    },
    "poison_already_used": {
        "en": "You tried to poison but already used your Poison ability.",
        "cn": "你尝试使用毒药，但毒药已经用过了。",
    },
    "doctor_decision_failed": {
        "en": "Decision failed (invalid response).",
        "cn": "决策失败 (无效回应)。",
    },
    # --- mafia single decision ---
    "decided_kill": {
        "en": "{} decided to kill {}.",
        "cn": "{} 决定击杀 {}。",
    },
    "decided_skip": {
        "en": "{} decided to skip killing.",
        "cn": "{} 决定不击杀任何人。",
    },
}


def t(key: str, *args: object) -> str:
    """Get a translated string, optionally formatting with positional args."""
    entry = _STRINGS.get(key)
    if not entry:
        return key
    template = entry.get(_lang, entry.get("en", key))
    if args:
        return template.format(*args)
    return template
