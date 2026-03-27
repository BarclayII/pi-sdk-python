"""Orchestrator for Mafia game phases: night, day, and diary."""

import asyncio
import random
import shutil
from collections import Counter
from pathlib import Path

from pi_sdk import Agent

from game_state import GameState
from meeting import (
    VOTE_SCHEMA,
    _get_agent_json,
    _get_agent_response,
    run_meeting,
    run_vote,
)
from prompts import (
    diary_prompt,
    format_vote_outcome,
    mayor_election_diary_prompt,
    mayor_election_meeting_prompt,
    mayor_succession_prompt,
    phase_context_prompt,
    postgame_prompt,
)
from roles import (
    INVESTIGATE_SCHEMA,
    PROTECT_SCHEMA,
    DOCTOR_ACTION_SCHEMA,
    detective_prompt,
    guardian_prompt,
    doctor_prompt,
)
from tmux_utils import log_to_agent, mark_agent_dead, stream_to_agent

from loguru import logger


def _distribute_transcript(
    file_path: str,
    agent_dirs: dict[str, str],
    allowed_agents: list[str],
) -> None:
    """Copy a transcript file into allowed agents' data/ directories."""
    filename = Path(file_path).name
    for name in allowed_agents:
        if name in agent_dirs:
            dest_dir = Path(agent_dirs[name]) / "data"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_dir / filename)


def _get_dead_players(state: GameState) -> list[str]:
    """Get list of dead players."""
    return [p for p in state.players if p not in state.alive]


def _get_mafia_allies_alive(state: GameState, name: str) -> list[str] | None:
    """Get alive mafia allies for a player, or None if not mafia."""
    if state.roles.get(name) != "mafia":
        return None
    return [m for m in state.get_by_role("mafia") if m != name]


def _phase_context(
    state: GameState,
    phase: str,
    name: str | None = None,
) -> str:
    """Build phase context prompt, optionally including mafia allies for a specific player."""
    mafia_allies_alive = None
    if name and state.roles.get(name) == "mafia":
        mafia_allies_alive = _get_mafia_allies_alive(state, name)
    return phase_context_prompt(
        round_id=state.round_id,
        alive_players=sorted(state.alive),
        dead_players=_get_dead_players(state),
        mafia_alive_count=len(state.get_by_role("mafia")),
        phase=phase,
        mafia_allies_alive=mafia_allies_alive,
        mayor=state.mayor,
    )


async def mayor_election_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    facilitator: Agent,
    mayor_rounds: int,
    session_name: str,
    use_llm_consensus: bool = False,
) -> None:
    """Run the Day 0 mayor election: discussion + vote."""
    data_dir = Path(state.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("--- Day 0: Mayor Election ---")
    for name in state.alive:
        log_to_agent(agent_dirs[name], "--- Day 0: Mayor Election ---")

    alive_agents = {name: agents[name] for name in state.alive}
    transcript_path = str(data_dir / "DAY_0_MAYOR_ELECTION.txt")

    meeting_context = mayor_election_meeting_prompt(sorted(state.alive))

    await run_meeting(
        participants=alive_agents,
        facilitator=facilitator,
        transcript_path=transcript_path,
        max_rounds=mayor_rounds,
        meeting_context=meeting_context,
        log_callback=lambda name, msg: log_to_agent(agent_dirs[name], msg),
        stream_callback=lambda name, text: stream_to_agent(agent_dirs[name], text),
        use_llm_consensus=use_llm_consensus,
    )

    # Vote for mayor (simple plurality, can vote for self)
    for name in state.alive:
        log_to_agent(agent_dirs[name], "--- MAYOR VOTE ---")

    winner, vote_results = await run_vote(
        participants=alive_agents,
        vote_type="mayor",
        stream_callback=lambda name, text: stream_to_agent(agent_dirs[name], text),
    )

    # Append vote results to transcript
    with open(transcript_path, "a") as f:
        f.write("\n=== Mayor Vote ===\n")
        for voter, data in vote_results.items():
            f.write(f"{voter} voted: {data['vote']}\n")
        f.write(f"\nElected Mayor: {winner or 'no one (tie)'}\n")

    if winner:
        state.mayor = winner
        logger.info("Mayor elected: {}", winner)
        for name in state.alive:
            log_to_agent(agent_dirs[name], f"Mayor elected: {winner}")
    else:
        # Tie — pick randomly from tied candidates
        tally = Counter(
            d["vote"] for d in vote_results.values() if d["vote"] != "abstain"
        )
        if tally:
            max_count = max(tally.values())
            tied = [n for n, c in tally.items() if c == max_count]
            state.mayor = random.choice(tied)
            logger.info("Mayor tie — randomly selected: {}", state.mayor)
            for name in state.alive:
                log_to_agent(
                    agent_dirs[name], f"Mayor elected (tiebreak): {state.mayor}"
                )

    # Distribute transcript to all players
    _distribute_transcript(transcript_path, agent_dirs, state.players)


async def mayor_election_diary_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
) -> None:
    """Have all agents write a Day 0 diary after the mayor election."""
    data_dir = Path(state.data_dir)
    transcript_path = data_dir / "DAY_0_MAYOR_ELECTION.txt"
    election_transcript = (
        transcript_path.read_text() if transcript_path.exists() else ""
    )

    alive_sorted = sorted(state.alive)

    async def _write_diary(name: str) -> None:
        log_to_agent(agent_dirs[name], "--- Writing diary for Day 0 ---")
        prompt = mayor_election_diary_prompt(name, alive_sorted, election_transcript)
        await _get_agent_response(
            name,
            agents[name],
            prompt,
            stream_callback=lambda text, n=name: stream_to_agent(agent_dirs[n], text),
        )
        log_to_agent(agent_dirs[name], "Diary written.")

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_write_diary(n) for n in eligible))


async def _handle_mayor_succession(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    dead_player: str,
    session_name: str,
) -> None:
    """If the dead player is the mayor, have them appoint a successor."""
    if state.mayor != dead_player:
        return

    alive_list = sorted(state.alive)
    if not alive_list:
        state.mayor = None
        return

    logger.info("Mayor {} is dying — appointing successor", dead_player)

    # Ask the dying mayor to appoint a successor (they're still in agents dict)
    if dead_player in agents:
        prompt = mayor_succession_prompt(dead_player, alive_list)
        parsed = await _get_agent_json(
            dead_player,
            agents[dead_player],
            prompt,
            stream_callback=lambda text: stream_to_agent(agent_dirs[dead_player], text),
            response_format=VOTE_SCHEMA,
        )

        if (
            parsed
            and parsed.get("vote") in alive_list
            and parsed["vote"] != dead_player
        ):
            state.mayor = parsed["vote"]
            logger.info("New mayor appointed: {}", state.mayor)
            for name in state.alive:
                log_to_agent(
                    agent_dirs[name],
                    f"The dying Mayor {dead_player} appointed {state.mayor} as the new Mayor.",
                )
            return

    # Fallback: if parsing fails or invalid, pick the first alive player
    state.mayor = alive_list[0]
    logger.info("Mayor succession fallback: {}", state.mayor)
    for name in state.alive:
        log_to_agent(
            agent_dirs[name],
            f"The Mayor's last wish was unclear. {state.mayor} becomes the new Mayor.",
        )


async def night_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    facilitator: Agent,
    mafia_rounds: int,
    session_name: str,
    use_llm_consensus: bool = False,
) -> tuple[str | None, str | None]:
    """Run the night phase.

    Returns:
        (killed_name or None, poisoned_name or None)
    """
    data_dir = Path(state.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    round_id = state.round_id

    # === PHASE 1: Detective, Mafia, and Guardian act simultaneously ===
    killed = None
    protected = None

    async def _detective_action() -> None:
        detectives = state.get_by_role("detective")
        if not detectives:
            return
        detective = detectives[0]
        log_to_agent(agent_dirs[detective], f"--- Night {round_id}: Investigation ---")

        agent = agents[detective]
        context = _phase_context(state, "Night — Investigation", detective)
        prompt = context + "\n\n" + detective_prompt(sorted(state.alive), detective)
        parsed = await _get_agent_json(
            detective,
            agent,
            prompt,
            stream_callback=lambda text: stream_to_agent(agent_dirs[detective], text),
            response_format=INVESTIGATE_SCHEMA,
        )

        investigated = None
        if isinstance(parsed, dict) and "investigate" in parsed:
            target = parsed["investigate"]
            if target in state.alive and target != detective:
                investigated = target

        if investigated:
            is_mafia = state.roles[investigated] == "mafia"
            result_text = (
                f"Night {round_id} Investigation:\n"
                f"You investigated {investigated}.\n"
                f"Result: {investigated} is {'a MAFIA member' if is_mafia else 'NOT Mafia'}.\n"
            )
        else:
            result_text = f"Night {round_id}: Investigation failed (invalid target).\n"

        notes_path = data_dir / f"NIGHT_DETECTIVE_NOTES_{round_id}.txt"
        notes_path.write_text(result_text)
        _distribute_transcript(str(notes_path), agent_dirs, [detective])
        log_to_agent(agent_dirs[detective], result_text.strip())

    async def _mafia_action() -> str | None:
        mafia_members = state.get_by_role("mafia")
        if not mafia_members:
            return None

        for m in mafia_members:
            log_to_agent(agent_dirs[m], f"--- Night {round_id}: Mafia Meeting ---")

        transcript_path = str(data_dir / f"NIGHT_MAFIA_{round_id}.txt")
        target = None

        if len(mafia_members) == 1:
            mafia_name = mafia_members[0]
            agent = agents[mafia_name]
            others = sorted(state.alive)
            others_str = ", ".join(others)

            context = _phase_context(state, "Night — Mafia Decision", mafia_name)
            prompt = (
                f"{context}\n\n"
                f"You are the only Mafia member. Choose someone to eliminate tonight, "
                f"or vote 'abstain' to keep everyone alive.\n"
                f"You may target anyone — including yourself (risky, but the guardian might save you).\n"
                f"Alive players: {others_str}\n\n"
                f'Return ONLY valid JSON: {{"vote": "<player_name> or abstain", "reasoning": "..."}}'
            )
            parsed = await _get_agent_json(
                mafia_name,
                agent,
                prompt,
                stream_callback=lambda text: stream_to_agent(
                    agent_dirs[mafia_name], text
                ),
                response_format=VOTE_SCHEMA,
            )

            if isinstance(parsed, dict) and "vote" in parsed:
                vote = parsed["vote"]
                if vote == "abstain":
                    target = None
                elif vote in others:
                    target = vote

            with open(transcript_path, "w") as f:
                f.write(f"=== Night {round_id} - Mafia Decision ===\n\n")
                f.write(
                    f"{mafia_name} decided to {'kill ' + target if target else 'skip killing'}.\n"
                )
        else:
            mafia_agents = {m: agents[m] for m in mafia_members}

            meeting_context = (
                f"{_phase_context(state, 'Night — Mafia Meeting')}\n\n"
                "This is a secret Mafia meeting. Discuss who to eliminate tonight. "
                "You may also choose to keep everyone alive. "
                "Only Mafia members are present. Be strategic."
            )

            await run_meeting(
                participants=mafia_agents,
                facilitator=facilitator,
                transcript_path=transcript_path,
                max_rounds=mafia_rounds,
                meeting_context=meeting_context,
                log_callback=lambda name, msg: log_to_agent(agent_dirs[name], msg),
                stream_callback=lambda name, text: stream_to_agent(
                    agent_dirs[name], text
                ),
                use_llm_consensus=use_llm_consensus,
            )

            all_targets = sorted(state.alive)
            target, vote_results = await run_vote(
                participants=mafia_agents,
                vote_type="kill",
                valid_targets=all_targets,
                stream_callback=lambda name, text: stream_to_agent(
                    agent_dirs[name], text
                ),
            )

            with open(transcript_path, "a") as f:
                f.write("\n=== Mafia Vote ===\n")
                for voter, data in vote_results.items():
                    f.write(f"{voter} voted: {data['vote']}\n")
                f.write(f"\nTarget: {target or 'no kill'}\n")

        _distribute_transcript(transcript_path, agent_dirs, mafia_members)

        for m in mafia_members:
            log_to_agent(agent_dirs[m], f"Mafia target: {target or 'no one'}")

        return target

    async def _guardian_action() -> str | None:
        guardians = state.get_by_role("guardian")
        if not guardians:
            return None

        guardian_name = guardians[0]
        log_to_agent(
            agent_dirs[guardian_name], f"--- Night {round_id}: Guardian Decision ---"
        )

        agent = agents[guardian_name]
        context = _phase_context(state, "Night — Guardian Decision", guardian_name)
        prompt = (
            context
            + "\n\n"
            + guardian_prompt(
                sorted(state.alive), guardian_name, state.guardian_last_protected
            )
        )
        parsed = await _get_agent_json(
            guardian_name,
            agent,
            prompt,
            stream_callback=lambda text: stream_to_agent(
                agent_dirs[guardian_name], text
            ),
            response_format=PROTECT_SCHEMA,
        )

        notes_parts = [f"Night {round_id} Guardian Notes:\n"]
        result = None

        if isinstance(parsed, dict) and parsed.get("protect"):
            protect_target = parsed["protect"]
            valid_targets = [
                p
                for p in state.alive
                if p != guardian_name and p != state.guardian_last_protected
            ]
            if protect_target in valid_targets:
                result = protect_target
                state.guardian_last_protected = result
                notes_parts.append(f"You protected {result} tonight.\n")
            else:
                notes_parts.append(
                    f"Invalid target '{protect_target}'. No one was protected.\n"
                )
                state.guardian_last_protected = None

            if parsed.get("reasoning"):
                notes_parts.append(f"Reasoning: {parsed['reasoning']}\n")
        else:
            notes_parts.append("Decision failed (invalid response).\n")
            state.guardian_last_protected = None

        notes_path = data_dir / f"NIGHT_GUARDIAN_NOTES_{round_id}.txt"
        notes_path.write_text("\n".join(notes_parts))
        _distribute_transcript(str(notes_path), agent_dirs, [guardian_name])
        log_to_agent(agent_dirs[guardian_name], "\n".join(notes_parts).strip())

        return result

    # Run detective, mafia, and guardian simultaneously
    _, killed, protected = await asyncio.gather(
        _detective_action(),
        _mafia_action(),
        _guardian_action(),
    )

    # === Resolve guardian protection before doctor sees the result ===
    if protected and killed == protected:
        killed = None

    # === PHASE 2: Doctor acts after seeing the post-guardian result ===
    doctors = state.get_by_role("doctor")
    doctor_saved = False
    poisoned = None
    if doctors and (state.doctor_has_save or state.doctor_has_poison):
        doctor_name = doctors[0]
        log_to_agent(
            agent_dirs[doctor_name], f"--- Night {round_id}: Doctor Decision ---"
        )

        agent = agents[doctor_name]
        context = _phase_context(state, "Night — Doctor Decision", doctor_name)
        prompt = (
            context
            + "\n\n"
            + doctor_prompt(
                killed_player=killed,
                alive_players=sorted(state.alive),
                doctor_name=doctor_name,
                has_save=state.doctor_has_save,
                has_poison=state.doctor_has_poison,
            )
        )
        parsed = await _get_agent_json(
            doctor_name,
            agent,
            prompt,
            stream_callback=lambda text: stream_to_agent(agent_dirs[doctor_name], text),
            response_format=DOCTOR_ACTION_SCHEMA,
        )

        notes_parts = [f"Night {round_id} Doctor Notes:\n"]

        if isinstance(parsed, dict):
            if parsed.get("save") and state.doctor_has_save and killed:
                doctor_saved = True
                state.doctor_has_save = False
                notes_parts.append(f"You used your Save ability to revive {killed}.\n")
            elif parsed.get("save") and not state.doctor_has_save:
                notes_parts.append(
                    "You tried to save but already used your Save ability.\n"
                )
            elif parsed.get("save") and not killed:
                notes_parts.append("You tried to save but no one was killed.\n")

            # Handle poison
            poison_target = parsed.get("poison", "")
            if poison_target and state.doctor_has_poison:
                valid_poison = [
                    p for p in state.alive if p != doctor_name and p != killed
                ]
                if poison_target in valid_poison:
                    poisoned = poison_target
                    state.doctor_has_poison = False
                    notes_parts.append(f"You used your Poison ability on {poisoned}.\n")
                else:
                    notes_parts.append(
                        f"Invalid poison target '{poison_target}'. Poison not used.\n"
                    )
            elif poison_target and not state.doctor_has_poison:
                notes_parts.append(
                    "You tried to poison but already used your Poison ability.\n"
                )

            if parsed.get("reasoning"):
                notes_parts.append(f"Reasoning: {parsed['reasoning']}\n")
        else:
            notes_parts.append("Decision failed (invalid response).\n")

        notes_path = data_dir / f"NIGHT_DOCTOR_NOTES_{round_id}.txt"
        notes_path.write_text("\n".join(notes_parts))
        _distribute_transcript(str(notes_path), agent_dirs, [doctor_name])
        log_to_agent(agent_dirs[doctor_name], "\n".join(notes_parts).strip())

    # If doctor saved the killed player, they survive
    if doctor_saved and killed:
        killed = None

    return killed, poisoned


async def day_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    facilitator: Agent,
    day_rounds: int,
    killed: str | None,
    poisoned: str | None,
    session_name: str,
    use_llm_consensus: bool = False,
) -> tuple[str | None, list[str]]:
    """Run the day phase.

    Returns:
        (eliminated_name or None, day_transcript_lines)
    """
    data_dir = Path(state.data_dir)
    round_id = state.round_id

    # Announce deaths
    deaths: list[str] = []
    if killed:
        role = state.roles[killed].capitalize()
        deaths.append(
            f"{killed} was killed by the Mafia during the night. Their role was: {role}."
        )
        state.eliminate(killed, "killed by mafia")
        mark_agent_dead(session_name, killed, agent_dirs[killed])
        # Mayor succession if killed player was mayor
        await _handle_mayor_succession(state, agent_dirs, agents, killed, session_name)

    if poisoned:
        role = state.roles[poisoned].capitalize()
        deaths.append(
            f"{poisoned} was found dead from poisoning during the night. Their role was: {role}."
        )
        state.eliminate(poisoned, "poisoned by doctor")
        mark_agent_dead(session_name, poisoned, agent_dirs[poisoned])
        # Mayor succession if poisoned player was mayor
        await _handle_mayor_succession(
            state, agent_dirs, agents, poisoned, session_name
        )

    death_announcement = (
        "\n".join(deaths) if deaths else "No one died during the night."
    )

    # Log to all alive agents
    for name in state.alive:
        log_to_agent(agent_dirs[name], f"--- Day {round_id} ---")
        log_to_agent(agent_dirs[name], death_announcement)

    # Check win condition
    winner = state.check_win()
    if winner:
        return None, []

    alive_agents = {name: agents[name] for name in state.alive}

    transcript_path = str(data_dir / f"DAY_{round_id}.txt")

    meeting_context = (
        f"{_phase_context(state, 'Day Meeting')}\n\n"
        f"{death_announcement}\n\n"
        "Discuss who you think is Mafia and who should be eliminated. "
        "Be strategic — observe behavior, form alliances, and make your case."
    )

    transcript_lines = await run_meeting(
        participants=alive_agents,
        facilitator=facilitator,
        transcript_path=transcript_path,
        max_rounds=day_rounds,
        meeting_context=meeting_context,
        log_callback=lambda name, msg: log_to_agent(agent_dirs[name], msg),
        stream_callback=lambda name, text: stream_to_agent(agent_dirs[name], text),
        first_speaker=state.mayor,
        use_llm_consensus=use_llm_consensus,
    )

    # Vote
    for name in state.alive:
        log_to_agent(agent_dirs[name], "--- VOTING ---")

    eliminated, vote_results = await run_vote(
        participants=alive_agents,
        stream_callback=lambda name, text: stream_to_agent(agent_dirs[name], text),
        mayor=state.mayor,
    )

    # Append vote results to transcript (no reasoning, just votes + outcome)
    eliminated_role = state.roles[eliminated] if eliminated else None
    vote_lines = ["\n=== Day Vote ==="]
    for voter, data in vote_results.items():
        vote_lines.append(f"{voter} voted: {data['vote']}")
    vote_lines.append(f"\n{format_vote_outcome(eliminated, eliminated_role)}")

    with open(transcript_path, "a") as f:
        f.write("\n".join(vote_lines) + "\n")

    # Include vote results in transcript lines for diary phase
    transcript_lines.extend(vote_lines)

    # Distribute day transcript to all players (alive and dead can observe)
    _distribute_transcript(transcript_path, agent_dirs, state.players)

    if eliminated:
        role = state.roles[eliminated].capitalize()
        state.eliminate(eliminated, "voted out")
        mark_agent_dead(session_name, eliminated, agent_dirs[eliminated])
        for name in state.alive:
            log_to_agent(
                agent_dirs[name], f"{eliminated} was voted out. Their role was: {role}."
            )
        # Mayor succession if voted-out player was mayor
        await _handle_mayor_succession(
            state, agent_dirs, agents, eliminated, session_name
        )

    return eliminated, transcript_lines


async def diary_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    day_transcript_lines: list[str],
) -> None:
    """Have all agents (alive and dead) write diary and knowledge files."""
    round_id = state.round_id
    alive_sorted = sorted(state.alive)

    # Build the day transcript string
    day_transcript = (
        "\n".join(day_transcript_lines)
        if day_transcript_lines
        else "(no day meeting this round)"
    )

    async def _write_diary(name: str) -> None:
        log_to_agent(agent_dirs[name], f"--- Writing diary for round {round_id} ---")

        # Read night transcript for this player's role
        night_transcript = None
        role = state.roles.get(name)
        data_dir = Path(state.data_dir)
        if role == "mafia":
            night_path = data_dir / f"NIGHT_MAFIA_{round_id}.txt"
            if night_path.exists():
                night_transcript = night_path.read_text()
        elif role == "detective":
            night_path = data_dir / f"NIGHT_DETECTIVE_NOTES_{round_id}.txt"
            if night_path.exists():
                night_transcript = night_path.read_text()
        elif role == "doctor":
            night_path = data_dir / f"NIGHT_DOCTOR_NOTES_{round_id}.txt"
            if night_path.exists():
                night_transcript = night_path.read_text()
        elif role == "guardian":
            night_path = data_dir / f"NIGHT_GUARDIAN_NOTES_{round_id}.txt"
            if night_path.exists():
                night_transcript = night_path.read_text()

        prompt = diary_prompt(
            name, round_id, alive_sorted, day_transcript, night_transcript
        )

        await _get_agent_response(
            name,
            agents[name],
            prompt,
            stream_callback=lambda text, n=name: stream_to_agent(agent_dirs[n], text),
        )

        log_to_agent(agent_dirs[name], "Diary written.")

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_write_diary(n) for n in eligible))


async def postgame_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    winner: str,
) -> None:
    """Have all agents reflect on the completed game, update knowledge, and write lessons learned."""
    logger.info("--- Post-game reflection phase ---")

    other_players = {
        name: [p for p in state.players if p != name] for name in state.players
    }

    async def _reflect(name: str) -> None:
        log_to_agent(agent_dirs[name], "--- Post-game reflection ---")

        prompt = postgame_prompt(
            agent_name=name,
            agent_role=state.roles[name],
            winner=winner,
            all_roles=state.roles,
            eliminated=state.eliminated,
            total_rounds=state.round_id,
            other_players=other_players[name],
        )

        await _get_agent_response(
            name,
            agents[name],
            prompt,
            stream_callback=lambda text, n=name: stream_to_agent(agent_dirs[n], text),
        )

        log_to_agent(agent_dirs[name], "Post-game reflection complete.")

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_reflect(n) for n in eligible))
