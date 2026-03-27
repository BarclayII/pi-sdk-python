"""System prompt templates for the Mafia game."""


def agent_system_prompt(
    personality: str,
    role_description: str,
    agent_name: str,
    mafia_allies: list[str] | None = None,
) -> str:
    """Build the static system prompt for an agent (set once at game start)."""
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

IMPORTANT: Keep your responses concise (2-4 sentences per speaking turn). Stay in character. Do NOT reveal your role unless it's strategically beneficial.

IMPORTANT: When speaking, voting, or answering questions, respond with plain text in your message. NEVER use bash commands (like echo) or write to files to deliver your answers.

When speaking in meetings, wrap your public speech in <speak>...</speak> tags. Only the content inside these tags will be visible to other players. You may read files and think privately outside the tags. If you choose not to include a <speak> tag, you will remain silent this round."""


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
    dead_str = ", ".join(sorted(dead_players)) if dead_players else "none"
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
    """Prompt an agent to write their diary entry for the round.

    Includes the full day transcript (and optional night transcript) inline
    so the agent has a complete recap. The agent may also read their data
    folder for historical diary entries.
    """
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
        return f"Eliminated: {eliminated}. Their role was: {role.capitalize()}."
    return "No one was eliminated."


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
    winner_label = "Village" if winner == "village" else "Mafia"
    won = (winner == "village" and agent_role != "mafia") or (
        winner == "mafia" and agent_role == "mafia"
    )

    roles_str = "\n".join(
        f"  - {name}: {role.capitalize()}" for name, role in sorted(all_roles.items())
    )
    elim_str = "\n".join(
        f"  - Round {r}: {name} ({cause})" for r, name, cause in eliminated
    )

    others_str = ", ".join(other_players)

    return f"""=== GAME OVER ===
Winner: {winner_label}
You ({"WON" if won else "LOST"}) as {agent_role.capitalize()}.
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
   - General principles for playing your role ({agent_role}) better
   - Patterns you noticed about how other players behave
   - IMPORTANT: Preserve lessons from previous games — append new lessons, don't overwrite old ones

Keep all entries concise but insightful. Focus on actionable takeaways for future games."""


def mayor_election_meeting_prompt(alive_players: list[str]) -> str:
    """Build the meeting context for the Day 0 mayor election discussion."""
    players_str = ", ".join(sorted(alive_players))
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
    return f"""The discussion is over. Vote for who should be Mayor.
You may vote for any player, including yourself.
Candidates: {candidates_str}

The player with the most votes becomes Mayor (simple plurality).

Return ONLY valid JSON: {{"vote": "<player_name>", "reasoning": "..."}}

Your vote MUST be one of the listed candidates."""


def mayor_tiebreak_prompt(tied_options: list[str]) -> str:
    """Prompt the mayor to break a tie between two options."""
    options_str = ", ".join(f'"{opt}"' for opt in tied_options)
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
    return f"""You are about to die, but as Mayor you must appoint a successor.
Choose one of the surviving players to become the new Mayor.
Candidates: {candidates_str}

Return ONLY valid JSON: {{"vote": "<player_name>", "reasoning": "..."}}

Your vote MUST be one of the listed candidates."""
