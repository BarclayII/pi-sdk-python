"""System prompt templates for the Mafia game."""

from i18n import get_lang, role_name, t, winner_label


def agent_system_prompt(
    personality: str,
    role_description: str,
    agent_name: str,
    mafia_allies: list[str] | None = None,
) -> str:
    """Build the static system prompt for an agent (set once at game start)."""
    if get_lang() == "cn":
        return _agent_system_prompt_cn(
            personality, role_description, agent_name, mafia_allies
        )
    return _agent_system_prompt_en(
        personality, role_description, agent_name, mafia_allies
    )


def _agent_system_prompt_en(
    personality: str,
    role_description: str,
    agent_name: str,
    mafia_allies: list[str] | None = None,
) -> str:
    mafia_section = ""
    if mafia_allies:
        allies_str = ", ".join(mafia_allies)
        mafia_section = f"\n\nYour fellow Mafia members are: {allies_str}. Coordinate with them during night meetings and protect each other during the day."

    return f"""
You are {agent_name}, playing a Mafia game.  You have access to four tools: (1) read - read a file's contents, (2) edit - edit a file, (3) write - write contents to a new file, (4) bash - execute any Linux shell command such as grep, ls, cat, etc.

The rules are in RULES.md.  Make sure you read the rules before engaging with others.

{role_description}{mafia_section}

{personality}

You may have diary files (DIARY_<round>.txt) and a lessons learned file (LESSONS_LEARNED.md) in your working directory. You may also have knowledge files (KNOWLEDGE_<name>.txt) from previous games. Read them to recall what happened in previous rounds and games.

Your working directory also contains transcripts (DAY_<round>.txt, NIGHT_*.txt) you're allowed to see.

IMPORTANT: Keep your responses concise (no more than 3 sentences per speaking turn). Stay in character. Do NOT reveal your role unless it's strategically beneficial.

IMPORTANT: When speaking, voting, or answering questions, respond with plain text in your message. NEVER use bash commands (like echo) or write to files to deliver your answers.

When speaking in meetings, wrap your public speech in <speak>...</speak> tags. Only the content inside these tags will be visible to other players. You may read files and think privately outside the tags. If you choose not to include a <speak> tag, you will remain silent this round."""


def _agent_system_prompt_cn(
    personality: str,
    role_description: str,
    agent_name: str,
    mafia_allies: list[str] | None = None,
) -> str:
    mafia_section = ""
    if mafia_allies:
        allies_str = ", ".join(mafia_allies)
        mafia_section = f"\n\n你的狼人同伴是: {allies_str}。在夜间会议中与他们协作，在白天互相掩护。"

    return f"""
你是 {agent_name}，正在参与一场狼人杀游戏。你可以使用四个工具：(1) read - 读取文件内容，(2) edit - 编辑文件，(3) write - 写入新文件，(4) bash - 执行Linux命令如grep、ls、cat等。

游戏规则在 RULES.md 中。请确保在与其他人互动之前先阅读规则。

{role_description}{mafia_section}

{personality}

你的工作目录中可能有日记文件 (DIARY_<轮次>.txt) 和经验总结文件 (LESSONS_LEARNED.md)。你也可能有之前游戏的知识文件 (KNOWLEDGE_<名字>.txt)。阅读它们来回忆之前的轮次和游戏。

你的工作目录还包含你可以查看的会议记录 (DAY_<轮次>.txt, NIGHT_*.txt)。

重要：请用中文发言。保持简洁（每次发言不超过3句话）。保持角色扮演。除非有策略性好处，否则不要暴露你的身份。

重要：发言、投票或回答问题时，请直接在消息中使用纯文本回复。不要使用bash命令（如echo）或写入文件来回答。

在会议中发言时，将你的公开发言包裹在 <speak>...</speak> 标签中。只有标签内的内容会被其他玩家看到。你可以在标签外阅读文件和私下思考。如果你选择不使用 <speak> 标签，你将在本轮保持沉默。"""


def phase_context_prompt(
    round_id: int,
    alive_players: list[str],
    dead_players: list[str],
    mafia_alive_count: int,
    phase: str,
    mafia_allies_alive: list[str] | None = None,
    mayor: str | None = None,
) -> str:
    """Build a user-message preamble with current game state for the start of a phase action."""
    alive_str = ", ".join(sorted(alive_players))
    dead_str = (
        ", ".join(sorted(dead_players))
        if dead_players
        else ("无" if get_lang() == "cn" else "none")
    )

    if get_lang() == "cn":
        parts = [
            f"=== 第{round_id}轮 — {phase} ===",
            f"存活玩家: {alive_str}",
            f"死亡玩家: {dead_str}",
            f"剩余狼人数: {mafia_alive_count}",
        ]
        if mayor:
            parts.append(f"当前警长: {mayor} (优先发言，平票决胜)")
        if mafia_allies_alive is not None:
            allies_str = (
                ", ".join(mafia_allies_alive)
                if mafia_allies_alive
                else "无 (你是最后一个)"
            )
            parts.append(f"你存活的狼人同伴: {allies_str}")
    else:
        parts = [
            f"=== Round {round_id} — {phase} ===",
            f"Alive players: {alive_str}",
            f"Dead players: {dead_str}",
            f"Mafia members remaining: {mafia_alive_count}",
        ]
        if mayor:
            parts.append(f"Current Mayor: {mayor} (speaks first, breaks tiebreaks)")
        if mafia_allies_alive is not None:
            allies_str = (
                ", ".join(mafia_allies_alive)
                if mafia_allies_alive
                else "none (you are the last)"
            )
            parts.append(f"Your living Mafia allies: {allies_str}")
    return "\n".join(parts)


def eagerness_prompt(new_messages: str) -> str:
    """Build the prompt for a player to rate their eagerness to speak."""
    if get_lang() == "cn":
        return f"""讨论中的新内容:
{new_messages}

请评估你发言的迫切程度，0（保持沉默）到10（必须立刻发言）。考虑：
- 你有重要的事情要说吗？
- 你刚才被提到或被指控了吗？
- 有需要分享的信息或需要表达的观点吗？

仅返回有效JSON: {{"eagerness": <0到10的数字>, "reason": "简要原因"}}"""

    return f"""New in the discussion:
{new_messages}

Rate your eagerness to speak next on a scale from 0 (stay silent) to 10 (must speak now). Consider:
- Do you have something important to say?
- Were you just mentioned or accused?
- Is there information you need to share or a point you need to make?

Return ONLY valid JSON: {{"eagerness": <number from 0 to 10>, "reason": "brief reason"}}"""


def consensus_prompt(participants: list[str], transcript_recent: str) -> str:
    """Build the prompt for the facilitator to check if consensus has been reached."""
    participants_str = ", ".join(participants)
    if get_lang() == "cn":
        return f"""你是狼人杀游戏讨论的主持人。你的工作是检测是否已达成一致共识。

当前参与者: {participants_str}

最近的记录:
{transcript_recent}

共识检测规则:
- 只有当每个参与者都明确且清楚地同意了同一个目标（全票通过）或"不投票"时，才将 consensus_reached 设为 true
- 沉默、模糊的表态或"随大流"不算数——每个参与者必须明确表达立场
- 如果有任何一个参与者不同意或未明确表态，consensus_reached 必须为 false
- 当 consensus_reached 为 true 时，将 consensus_target 设为达成共识的玩家名或 "no target"
- 当 consensus_reached 为 false 时，将 consensus_target 设为空字符串

仅返回有效JSON: {{"consensus_reached": <true or false>, "consensus_target": "<玩家名或空字符串或no target>", "reasoning": "..."}}"""

    return f"""You are a meeting facilitator for a Mafia game discussion. Your job is to detect when unanimous consensus has been reached.

Current participants: {participants_str}

Recent transcript:
{transcript_recent}

Consensus detection rules:
- Set consensus_reached to true ONLY if every participant has explicitly and clearly agreed on the same target (unanimous agreement) or "no target"
- Silence, vague statements, or "going along" do NOT count — each participant must have stated their position
- If even one participant disagrees or hasn't stated a clear position, consensus_reached must be false
- When consensus_reached is true, set consensus_target to the agreed-upon player name or "no target" (if everybody decided not to vote)
- When consensus_reached is false, set consensus_target to an empty string

Return ONLY valid JSON: {{"consensus_reached": <true or false>, "consensus_target": "<player name or empty string or no target>", "reasoning": "..."}}"""


def vote_prompt(
    alive_players: list[str], agent_name: str, mayor: str | None = None
) -> str:
    """Build the vote prompt appended after a meeting."""
    candidates = [p for p in alive_players if p != agent_name]
    candidates_str = ", ".join(candidates)

    if get_lang() == "cn":
        mayor_note = ""
        if mayor and mayor in alive_players:
            mayor_note = f"\n注意: {mayor} 是警长——如果两个选项得票完全相同（各获得总票数的一半），警长决定最终结果。\n"
        return f"""讨论结束。你现在必须投票淘汰一名玩家，或选择弃权。
候选人: {candidates_str}

当至少半数存活玩家投票给某人时，该玩家被淘汰（弃权计入总票数）。{mayor_note}

仅返回有效JSON: {{"vote": "<玩家名>" 或 "abstain", "reasoning": "..."}}

你的投票必须是候选人之一，或 "abstain"（弃权）。"""

    mayor_note = ""
    if mayor and mayor in alive_players:
        mayor_note = f"\nNote: {mayor} is the Mayor — if there is an exact tie between two options (each receiving half of all votes), the Mayor decides the outcome.\n"
    return f"""The discussion is over. You must now vote to eliminate one player, or choose to abstain.
Candidates: {candidates_str}

A player is eliminated if at least half of all alive players vote for them (abstentions count toward the total).{mayor_note}

Return ONLY valid JSON: {{"vote": "<player_name>" or "abstain", "reasoning": "..."}}

Your vote MUST be one of the listed candidates, or "abstain" if you choose not to vote."""


def diary_prompt(
    agent_name: str,
    round_id: int,
    alive_players: list[str],
    day_transcript: str,
    night_transcript: str | None = None,
) -> str:
    """Prompt an agent to write their diary entry for the round."""
    if get_lang() == "cn":
        parts = [f"第{round_id}轮已结束。\n"]
        if night_transcript:
            parts.append(f"=== 夜间记录 ===\n{night_transcript}\n")
        parts.append(f"=== 白天会议记录 ===\n{day_transcript}\n")
        parts.append(
            "你可以阅读你的数据文件夹中的历史日记。\n\n"
            f"写入 DIARY_{round_id}.txt，总结本轮发生的事情、你的想法/策略、"
            "以及对其他玩家的观察（怀疑、联盟、行为模式）。\n\n"
            "保持简洁但有洞察力。"
        )
        return "\n".join(parts)

    parts = [f"Round {round_id} has ended.\n"]
    if night_transcript:
        parts.append(f"=== Night Transcript ===\n{night_transcript}\n")
    parts.append(f"=== Day Meeting Transcript ===\n{day_transcript}\n")
    parts.append(
        "You may read your data folder for historical diary entries as you wish.\n\n"
        f"Write DIARY_{round_id}.txt with a summary of what happened this round, your thoughts/strategy, "
        "and any observations about other players (suspicions, alliances, behavior patterns).\n\n"
        "Keep it concise but insightful."
    )
    return "\n".join(parts)


def mayor_election_diary_prompt(
    agent_name: str,
    alive_players: list[str],
    election_transcript: str,
) -> str:
    """Prompt an agent to write their Day 0 diary after the mayor election."""
    if get_lang() == "cn":
        return (
            "第0天——警长竞选——刚刚结束。\n\n"
            f"=== 警长竞选记录 ===\n{election_transcript}\n\n"
            "写入 DIARY_0.txt，总结发生了什么、你对其他玩家的初步印象、"
            "你注意到的早期嫌疑或联盟关系、以及你接下来的策略。\n\n"
            "保持简洁但有洞察力。"
        )

    return (
        "Day 0 — the mayor election — has just concluded.\n\n"
        f"=== Mayor Election Transcript ===\n{election_transcript}\n\n"
        "Write DIARY_0.txt with a summary of what happened, your initial impressions "
        "of the other players, any early suspicions or alliances you noticed, "
        "and your strategy going forward.\n\n"
        "Keep it concise but insightful."
    )


def mafia_kill_vote_prompt(targets: list[str]) -> str:
    """Prompt mafia members to vote on who to kill."""
    targets_str = ", ".join(targets)
    if get_lang() == "cn":
        return f"""狼人讨论结束。投票决定今晚击杀谁，或投 "abstain" 放弃击杀。
你可以选择任何人——包括你的狼人同伴甚至你自己（冒险，但守卫可能会保护你）。
可选目标: {targets_str}

仅返回有效JSON: {{"vote": "<玩家名>" 或 "abstain", "reasoning": "..."}}"""

    return f"""The Mafia discussion is over. Vote on who to kill tonight, or vote "abstain" to skip or spare everyone.
You may target anyone — including fellow Mafia members or even yourself (risky, but the guardian might protect you).
Possible targets: {targets_str}

Return ONLY valid JSON: {{"vote": "<player_name>" or "abstain", "reasoning": "..."}}"""


def format_vote_outcome(
    eliminated: str | None,
    role: str | None = None,
) -> str:
    """Format the public vote outcome line (no individual reasoning)."""
    if eliminated and role:
        return t("eliminated_result", eliminated, role_name(role))
    return t("no_elimination")


def postgame_prompt(
    agent_name: str,
    agent_role: str,
    winner: str,
    all_roles: dict[str, str],
    eliminated: list[tuple[int, str, str]],
    total_rounds: int,
    other_players: list[str],
) -> str:
    """Prompt an agent to reflect on the completed game and update lessons learned."""
    wl = winner_label(winner)
    won = (winner == "village" and agent_role != "mafia") or (
        winner == "mafia" and agent_role == "mafia"
    )

    roles_str = "\n".join(
        f"  - {name}: {role_name(role)}" for name, role in sorted(all_roles.items())
    )
    elim_str = "\n".join(
        f"  - Round {r}: {name} ({cause})" for r, name, cause in eliminated
    )

    others_str = ", ".join(other_players)

    if get_lang() == "cn":
        won_str = "获胜" if won else "失败"
        return f"""=== 游戏结束 ===
获胜方: {wl}
你（{won_str}）的角色是 {role_name(agent_role)}。
游戏持续了 {total_rounds} 轮。

所有角色（现已揭晓）:
{roles_str}

淘汰时间线:
{elim_str if elim_str else "  （无人被淘汰）"}

阅读你的日记文件 (DIARY_*.txt) 和知识文件 (KNOWLEDGE_*.txt) 回忆你在游戏中的想法。

现在请完成以下任务:

1. 写入 GAME_SUMMARY.txt — 从你的角度对整场游戏的完整回顾:
   - 关键时刻和转折点
   - 你对其他玩家的判断哪些正确哪些错误
   - 游戏的实际进展与你预期的对比

2. 对每个玩家 ({others_str})，更新他们的 KNOWLEDGE_<名字>.txt:
   - 现在你知道了他们的真实身份，重新评估他们的行为
   - 记录他们的游戏风格、破绽和倾向（对未来的游戏有用）
   - 保留之前的观察，但添加一个"赛后评估"部分

3. 阅读你现有的 LESSONS_LEARNED.md（如果存在），然后更新它:
   - 本局游戏中哪些策略有效或失败
   - 下次你会怎么做
   - 关于更好地扮演你的角色（{role_name(agent_role)}）的一般原则
   - 你注意到的其他玩家行为模式
   - 重要: 保留之前游戏的经验——追加新经验，不要覆盖旧的

保持所有条目简洁但有洞察力。专注于对未来游戏有用的可行要点。"""

    return f"""=== GAME OVER ===
Winner: {wl}
You ({"WON" if won else "LOST"}) as {role_name(agent_role)}.
Game lasted {total_rounds} rounds.

All roles (now revealed):
{roles_str}

Elimination timeline:
{elim_str if elim_str else "  (no eliminations)"}

Read your diary files (DIARY_*.txt) and knowledge files (KNOWLEDGE_*.txt) to recall your thoughts during the game.

Now do the following:

1. Write GAME_SUMMARY.txt — a full recap of the game from your perspective:
   - Key moments and turning points
   - What you got right and wrong about other players
   - How the game unfolded vs. your expectations

2. For each player ({others_str}), UPDATE their KNOWLEDGE_<name>.txt:
   - Now that you know their true role, reassess their behavior
   - Note their playing style, tells, and tendencies (useful for future games)
   - Keep previous observations but add a "Post-Game" section with your updated assessment

3. Read your existing LESSONS_LEARNED.md (if it exists), then UPDATE it:
   - What strategies worked or failed this game
   - What you'd do differently next time
   - General principles for playing your role ({role_name(agent_role)}) better
   - Patterns you noticed about how other players behave
   - IMPORTANT: Preserve lessons from previous games — append new lessons, don't overwrite old ones

Keep all entries concise but insightful. Focus on actionable takeaways for future games."""


def mayor_election_meeting_prompt(alive_players: list[str]) -> str:
    """Build the meeting context for the Day 0 mayor election discussion."""
    players_str = ", ".join(sorted(alive_players))
    if get_lang() == "cn":
        return f"""=== 第0天 — 警长竞选 ===
存活玩家: {players_str}

在第一个夜晚之前，全体玩家必须选出一名警长。
警长在每次白天会议中优先发言，并在投票平局时做出最终决定。
如果警长死亡，他将从存活玩家中指定一名继任者。

讨论谁应该成为警长。考虑领导能力、可信度和策略。
你可以提名自己或其他人。"""

    return f"""=== Day 0 — Mayor Election ===
Alive players: {players_str}

Before the first night, the town must elect a Mayor.
The Mayor speaks first in every day meeting and breaks ties if the elimination vote is split evenly between two options.
If the Mayor dies, they appoint a successor from the surviving players.

Discuss who should be Mayor. Consider leadership ability, trustworthiness, and strategy.
You may nominate yourself or others."""


def mayor_vote_prompt(alive_players: list[str]) -> str:
    """Build the vote prompt for electing a mayor (can vote for anyone including self)."""
    candidates_str = ", ".join(sorted(alive_players))
    if get_lang() == "cn":
        return f"""讨论结束。投票选出警长。
你可以投票给任何玩家，包括你自己。
候选人: {candidates_str}

得票最多的玩家成为警长（简单多数）。

仅返回有效JSON: {{"vote": "<玩家名>", "reasoning": "..."}}

你的投票必须是候选人之一。"""

    return f"""The discussion is over. Vote for who should be Mayor.
You may vote for any player, including yourself.
Candidates: {candidates_str}

The player with the most votes becomes Mayor (simple plurality).

Return ONLY valid JSON: {{"vote": "<player_name>", "reasoning": "..."}}

Your vote MUST be one of the listed candidates."""


def mayor_tiebreak_prompt(tied_options: list[str]) -> str:
    """Prompt the mayor to break a tie between two options."""
    options_str = ", ".join(f'"{opt}"' for opt in tied_options)
    if get_lang() == "cn":
        return f"""投票结果出现平局。作为警长，你必须打破平局。

平局选项为: {options_str}
("abstain" 表示不淘汰任何人。)

从平局选项中选择一个来决定结果。

仅返回有效JSON: {{"vote": "<选项>", "reasoning": "..."}}

你的投票必须是以下之一: {options_str}。"""

    return f"""The elimination vote has resulted in a tie. As Mayor, you must break the tie.

The tied options are: {options_str}
("abstain" means no one is eliminated.)

Choose one of the tied options to determine the outcome.

Return ONLY valid JSON: {{"vote": "<option>", "reasoning": "..."}}

Your vote MUST be one of: {options_str}."""


def mayor_succession_prompt(dying_mayor: str, alive_players: list[str]) -> str:
    """Prompt the dying mayor to appoint a successor."""
    candidates = [p for p in alive_players if p != dying_mayor]
    candidates_str = ", ".join(sorted(candidates))
    if get_lang() == "cn":
        return f"""你即将死亡，但作为警长你必须指定一名继任者。
从存活玩家中选择一名作为新警长。
候选人: {candidates_str}

仅返回有效JSON: {{"vote": "<玩家名>", "reasoning": "..."}}

你的投票必须是候选人之一。"""

    return f"""You are about to die, but as Mayor you must appoint a successor.
Choose one of the surviving players to become the new Mayor.
Candidates: {candidates_str}

Return ONLY valid JSON: {{"vote": "<player_name>", "reasoning": "..."}}

Your vote MUST be one of the listed candidates."""
