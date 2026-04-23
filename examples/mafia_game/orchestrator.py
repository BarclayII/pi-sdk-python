"""Orchestrator for Mafia game phases: night, day, and diary."""

from __future__ import annotations

import asyncio
import random
import shutil
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from pi_sdk import Agent

from game_state import GameState
from i18n import get_lang, role_name, t
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

if TYPE_CHECKING:
    from web_events import GameEventBus


def _emit(event_bus: GameEventBus | None, coro):
    """Fire-and-forget an event_bus coroutine if event_bus is present."""
    if event_bus is not None:
        asyncio.ensure_future(coro)


def _make_dual_stream(agent_dirs: dict[str, str], event_bus: GameEventBus | None):
    """Create a stream callback that sends to both tmux and web event bus.

    Returns a (name, text) callback suitable for run_meeting/run_vote.
    """

    def callback(name: str, text: str):
        stream_to_agent(agent_dirs[name], text)
        if event_bus is not None:
            asyncio.ensure_future(event_bus.emit_speech_chunk(name, text))

    return callback


def _make_dual_stream_single(agent_dir: str, name: str, event_bus: GameEventBus | None):
    """Create a stream callback for a single agent (tmux + web)."""

    def callback(text: str):
        stream_to_agent(agent_dir, text)
        if event_bus is not None:
            asyncio.ensure_future(event_bus.emit_speech_chunk(name, text))

    return callback


def _make_dual_log(agent_dirs: dict[str, str], event_bus: GameEventBus | None):
    """Create a log callback that sends to both tmux and web event bus."""

    def callback(name: str, msg: str):
        log_to_agent(agent_dirs[name], msg)
        if event_bus is not None:
            asyncio.ensure_future(event_bus.emit_system_message(f"[{name}] {msg}"))

    return callback


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
    event_bus: GameEventBus | None = None,
) -> None:
    """Run the Day 0 mayor election: discussion + vote."""
    data_dir = Path(state.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info(t("day0_mayor_election"))
    for name in state.alive:
        log_to_agent(agent_dirs[name], t("day0_mayor_election"))

    if event_bus:
        await event_bus.emit_phase_change(
            "mayor_election",
            0,
            sorted(state.alive),
            _get_dead_players(state),
            state.mayor,
        )
        await event_bus.emit_system_message(t("day0_mayor_election"))

    alive_agents = {name: agents[name] for name in state.alive}
    transcript_path = str(data_dir / "DAY_0_MAYOR_ELECTION.txt")

    meeting_context = mayor_election_meeting_prompt(sorted(state.alive))

    await run_meeting(
        participants=alive_agents,
        facilitator=facilitator,
        transcript_path=transcript_path,
        max_rounds=mayor_rounds,
        meeting_context=meeting_context,
        log_callback=_make_dual_log(agent_dirs, event_bus),
        stream_callback=_make_dual_stream(agent_dirs, event_bus),
        use_llm_consensus=use_llm_consensus,
    )

    # Vote for mayor (simple plurality, can vote for self)
    for name in state.alive:
        log_to_agent(agent_dirs[name], t("mayor_vote"))

    winner, vote_results = await run_vote(
        participants=alive_agents,
        vote_type="mayor",
        stream_callback=_make_dual_stream(agent_dirs, event_bus),
    )

    # Emit votes to web
    if event_bus:
        for voter, data in vote_results.items():
            await event_bus.emit_vote(voter, data["vote"], data.get("reasoning", ""))

    # Append vote results to transcript
    with open(transcript_path, "a") as f:
        f.write(f"\n{t('mayor_vote_header')}\n")
        for voter, data in vote_results.items():
            f.write(f"{voter} voted: {data['vote']}\n")
        if winner:
            f.write(f"\n{t('elected_mayor_result', winner)}\n")
        else:
            f.write(f"\n{t('elected_mayor_tie')}\n")

    if winner:
        state.mayor = winner
        logger.info(t("mayor_elected", winner))
        for name in state.alive:
            log_to_agent(agent_dirs[name], t("mayor_elected", winner))
    else:
        # Tie — pick randomly from tied candidates
        tally = Counter(
            d["vote"] for d in vote_results.values() if d["vote"] != "abstain"
        )
        if tally:
            max_count = max(tally.values())
            tied = [n for n, c in tally.items() if c == max_count]
            state.mayor = random.choice(tied)
            logger.info(t("mayor_tie_random", state.mayor))
            for name in state.alive:
                log_to_agent(agent_dirs[name], t("mayor_elected_tiebreak", state.mayor))

    if event_bus and state.mayor:
        await event_bus.emit_mayor_elected(state.mayor)
        await event_bus.emit_vote_result("mayor", state.mayor)

    # Distribute transcript to all players
    _distribute_transcript(transcript_path, agent_dirs, state.players)


async def mayor_election_diary_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    event_bus: GameEventBus | None = None,
) -> None:
    """Have all agents write a Day 0 diary after the mayor election."""
    data_dir = Path(state.data_dir)
    transcript_path = data_dir / "DAY_0_MAYOR_ELECTION.txt"
    election_transcript = (
        transcript_path.read_text() if transcript_path.exists() else ""
    )

    alive_sorted = sorted(state.alive)

    if event_bus:
        await event_bus.emit_phase_change(
            "diary", 0, sorted(state.alive), _get_dead_players(state), state.mayor
        )

    async def _write_diary(name: str) -> None:
        log_to_agent(agent_dirs[name], t("writing_diary_day0"))
        prompt = mayor_election_diary_prompt(name, alive_sorted, election_transcript)

        def _stream(text: str, n: str = name) -> None:
            stream_to_agent(agent_dirs[n], text)
            if event_bus is not None:
                asyncio.ensure_future(event_bus.emit_diary_chunk(n, text))

        text = await _get_agent_response(
            name,
            agents[name],
            prompt,
            stream_callback=_stream,
        )
        log_to_agent(agent_dirs[name], t("diary_written"))
        if event_bus:
            await event_bus.emit_diary_entry(name, text)

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_write_diary(n) for n in eligible))


async def _handle_mayor_succession(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    dead_player: str,
    session_name: str,
    event_bus: GameEventBus | None = None,
) -> None:
    """If the dead player is the mayor, have them appoint a successor."""
    if state.mayor != dead_player:
        return

    alive_list = sorted(state.alive)
    if not alive_list:
        state.mayor = None
        return

    logger.info(t("mayor_dying_successor", dead_player))

    # Ask the dying mayor to appoint a successor (they're still in agents dict)
    if dead_player in agents:
        prompt = mayor_succession_prompt(dead_player, alive_list)
        parsed = await _get_agent_json(
            dead_player,
            agents[dead_player],
            prompt,
            stream_callback=_make_dual_stream_single(
                agent_dirs[dead_player], dead_player, event_bus
            ),
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
                    t("new_mayor_appointed", dead_player, state.mayor),
                )
            if event_bus:
                await event_bus.emit_mayor_elected(state.mayor)
            return

    # Fallback: if parsing fails or invalid, pick the first alive player
    state.mayor = alive_list[0]
    logger.info("Mayor succession fallback: {}", state.mayor)
    for name in state.alive:
        log_to_agent(
            agent_dirs[name],
            t("mayor_succession_fallback", state.mayor),
        )
    if event_bus:
        await event_bus.emit_mayor_elected(state.mayor)


async def night_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    facilitator: Agent,
    mafia_rounds: int,
    session_name: str,
    use_llm_consensus: bool = False,
    event_bus: GameEventBus | None = None,
) -> tuple[str | None, str | None]:
    """Run the night phase.

    Returns:
        (killed_name or None, poisoned_name or None)
    """
    data_dir = Path(state.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    round_id = state.round_id

    if event_bus:
        await event_bus.emit_phase_change(
            "night",
            round_id,
            sorted(state.alive),
            _get_dead_players(state),
            state.mayor,
        )

    # === PHASE 1: Detective, Mafia, and Guardian act simultaneously ===
    killed = None
    protected = None

    async def _detective_action() -> None:
        detectives = state.get_by_role("detective")
        if not detectives:
            return
        detective = detectives[0]
        log_to_agent(agent_dirs[detective], t("night_investigation", round_id))

        agent = agents[detective]
        phase_label = (
            "夜晚 — 预言家查验" if get_lang() == "cn" else "Night — Investigation"
        )
        context = _phase_context(state, phase_label, detective)
        prompt = context + "\n\n" + detective_prompt(sorted(state.alive), detective)
        parsed = await _get_agent_json(
            detective,
            agent,
            prompt,
            stream_callback=_make_dual_stream_single(
                agent_dirs[detective], detective, event_bus
            ),
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
                f"{t('night_investigation_header', round_id)}\n"
                f"{t('you_investigated', investigated)}\n"
                f"{t('investigation_result_mafia', investigated) if is_mafia else t('investigation_result_not_mafia', investigated)}\n"
            )
            if event_bus:
                await event_bus.emit_night_action(
                    "detective",
                    detective,
                    "investigate",
                    investigated,
                    "mafia" if is_mafia else "not_mafia",
                )
        else:
            result_text = t("investigation_failed", round_id) + "\n"
            if event_bus:
                await event_bus.emit_night_action(
                    "detective", detective, "investigate", None, "failed"
                )

        notes_path = data_dir / f"NIGHT_DETECTIVE_NOTES_{round_id}.txt"
        notes_path.write_text(result_text)
        _distribute_transcript(str(notes_path), agent_dirs, [detective])
        log_to_agent(agent_dirs[detective], result_text.strip())

    async def _mafia_action() -> str | None:
        mafia_members = state.get_by_role("mafia")
        if not mafia_members:
            return None

        for m in mafia_members:
            log_to_agent(agent_dirs[m], t("night_mafia_meeting", round_id))

        transcript_path = str(data_dir / f"NIGHT_MAFIA_{round_id}.txt")
        target = None

        if len(mafia_members) == 1:
            mafia_name = mafia_members[0]
            agent = agents[mafia_name]
            others = sorted(state.alive)
            others_str = ", ".join(others)

            phase_label = (
                "夜晚 — 狼人决策" if get_lang() == "cn" else "Night — Mafia Decision"
            )
            context = _phase_context(state, phase_label, mafia_name)

            if get_lang() == "cn":
                prompt = (
                    f"{context}\n\n"
                    f"你是唯一的狼人。选择今晚要击杀的目标，"
                    f"或投 'abstain' 不杀任何人。\n"
                    f"你可以选择任何人——包括你自己（冒险，但守卫可能会保护你）。\n"
                    f"存活玩家: {others_str}\n\n"
                    f'仅返回有效JSON: {{"vote": "<玩家名> 或 abstain", "reasoning": "..."}}'
                )
            else:
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
                stream_callback=_make_dual_stream_single(
                    agent_dirs[mafia_name], mafia_name, event_bus
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
                f.write(f"{t('mafia_night_decision', round_id)}\n\n")
                if target:
                    f.write(t("decided_kill", mafia_name, target) + "\n")
                else:
                    f.write(t("decided_skip", mafia_name) + "\n")
        else:
            mafia_agents = {m: agents[m] for m in mafia_members}

            phase_label = (
                "夜晚 — 狼人会议" if get_lang() == "cn" else "Night — Mafia Meeting"
            )

            if get_lang() == "cn":
                meeting_context = (
                    f"{_phase_context(state, phase_label)}\n\n"
                    "这是狼人秘密会议。讨论今晚要击杀谁。"
                    "你们也可以选择不杀任何人。"
                    "只有狼人在场。请制定策略。"
                )
            else:
                meeting_context = (
                    f"{_phase_context(state, phase_label)}\n\n"
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
                log_callback=_make_dual_log(agent_dirs, event_bus),
                stream_callback=_make_dual_stream(agent_dirs, event_bus),
                use_llm_consensus=use_llm_consensus,
            )

            all_targets = sorted(state.alive)
            target, vote_results = await run_vote(
                participants=mafia_agents,
                vote_type="kill",
                valid_targets=all_targets,
                stream_callback=_make_dual_stream(agent_dirs, event_bus),
            )

            with open(transcript_path, "a") as f:
                f.write(f"\n{t('mafia_vote_header')}\n")
                for voter, data in vote_results.items():
                    f.write(f"{voter} voted: {data['vote']}\n")
                if target:
                    f.write(f"\n{t('target_result', target)}\n")
                else:
                    f.write(f"\n{t('target_no_kill')}\n")

        _distribute_transcript(transcript_path, agent_dirs, mafia_members)

        for m in mafia_members:
            if target:
                log_to_agent(agent_dirs[m], t("mafia_target", target))
            else:
                log_to_agent(agent_dirs[m], t("mafia_target_none"))

        if event_bus:
            if target:
                await event_bus.emit_night_action(
                    "mafia", ", ".join(mafia_members), "kill", target, "targeted"
                )
            else:
                await event_bus.emit_night_action(
                    "mafia", ", ".join(mafia_members), "kill", None, "no_kill"
                )

        return target

    async def _guardian_action() -> str | None:
        guardians = state.get_by_role("guardian")
        if not guardians:
            return None

        guardian_name = guardians[0]
        log_to_agent(agent_dirs[guardian_name], t("night_guardian_decision", round_id))

        agent = agents[guardian_name]
        phase_label = (
            "夜晚 — 守卫守护" if get_lang() == "cn" else "Night — Guardian Decision"
        )
        context = _phase_context(state, phase_label, guardian_name)
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
            stream_callback=_make_dual_stream_single(
                agent_dirs[guardian_name], guardian_name, event_bus
            ),
            response_format=PROTECT_SCHEMA,
        )

        notes_header = (
            f"第{round_id}夜 守卫笔记:\n"
            if get_lang() == "cn"
            else f"Night {round_id} Guardian Notes:\n"
        )
        notes_parts = [notes_header]
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
                notes_parts.append(t("you_protected", result) + "\n")
            else:
                notes_parts.append(t("invalid_protect_target", protect_target) + "\n")
                state.guardian_last_protected = None

            if parsed.get("reasoning"):
                reasoning_label = "理由" if get_lang() == "cn" else "Reasoning"
                notes_parts.append(f"{reasoning_label}: {parsed['reasoning']}\n")
        else:
            notes_parts.append(t("guardian_decision_failed") + "\n")
            state.guardian_last_protected = None

        notes_path = data_dir / f"NIGHT_GUARDIAN_NOTES_{round_id}.txt"
        notes_path.write_text("\n".join(notes_parts))
        _distribute_transcript(str(notes_path), agent_dirs, [guardian_name])
        log_to_agent(agent_dirs[guardian_name], "\n".join(notes_parts).strip())

        if event_bus:
            if result:
                await event_bus.emit_night_action(
                    "guardian", guardian_name, "protect", result, "protected"
                )
            else:
                await event_bus.emit_night_action(
                    "guardian", guardian_name, "protect", None, "failed"
                )

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
        if event_bus:
            await event_bus.emit_system_message(
                f"Guardian saved {protected} from the mafia!"
            )

    # === PHASE 2: Doctor acts after seeing the post-guardian result ===
    doctors = state.get_by_role("doctor")
    doctor_saved = False
    poisoned = None
    if doctors and (state.doctor_has_save or state.doctor_has_poison):
        doctor_name = doctors[0]
        log_to_agent(agent_dirs[doctor_name], t("night_doctor_decision", round_id))

        agent = agents[doctor_name]
        phase_label = (
            "夜晚 — 女巫行动" if get_lang() == "cn" else "Night — Doctor Decision"
        )
        context = _phase_context(state, phase_label, doctor_name)
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
            stream_callback=_make_dual_stream_single(
                agent_dirs[doctor_name], doctor_name, event_bus
            ),
            response_format=DOCTOR_ACTION_SCHEMA,
        )

        notes_header = (
            f"第{round_id}夜 女巫笔记:\n"
            if get_lang() == "cn"
            else f"Night {round_id} Doctor Notes:\n"
        )
        notes_parts = [notes_header]

        if isinstance(parsed, dict):
            if parsed.get("save") and state.doctor_has_save and killed:
                doctor_saved = True
                state.doctor_has_save = False
                notes_parts.append(t("used_save", killed) + "\n")
                if event_bus:
                    await event_bus.emit_night_action(
                        "doctor", doctor_name, "save", killed, "saved"
                    )
            elif parsed.get("save") and not state.doctor_has_save:
                notes_parts.append(t("save_already_used") + "\n")
            elif parsed.get("save") and not killed:
                notes_parts.append(t("save_no_target") + "\n")

            # Handle poison
            poison_target = parsed.get("poison", "")
            if poison_target and state.doctor_has_poison:
                valid_poison = [
                    p for p in state.alive if p != doctor_name and p != killed
                ]
                if poison_target in valid_poison:
                    poisoned = poison_target
                    state.doctor_has_poison = False
                    notes_parts.append(t("used_poison", poisoned) + "\n")
                    if event_bus:
                        await event_bus.emit_night_action(
                            "doctor", doctor_name, "poison", poisoned, "poisoned"
                        )
                else:
                    notes_parts.append(t("invalid_poison_target", poison_target) + "\n")
            elif poison_target and not state.doctor_has_poison:
                notes_parts.append(t("poison_already_used") + "\n")

            if parsed.get("reasoning"):
                reasoning_label = "理由" if get_lang() == "cn" else "Reasoning"
                notes_parts.append(f"{reasoning_label}: {parsed['reasoning']}\n")
        else:
            notes_parts.append(t("doctor_decision_failed") + "\n")

        notes_path = data_dir / f"NIGHT_DOCTOR_NOTES_{round_id}.txt"
        notes_path.write_text("\n".join(notes_parts))
        _distribute_transcript(str(notes_path), agent_dirs, [doctor_name])
        log_to_agent(agent_dirs[doctor_name], "\n".join(notes_parts).strip())

    # If doctor saved the killed player, they survive
    if doctor_saved and killed:
        if event_bus:
            await event_bus.emit_system_message(f"Doctor saved {killed}!")
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
    event_bus: GameEventBus | None = None,
) -> tuple[str | None, list[str]]:
    """Run the day phase.

    Returns:
        (eliminated_name or None, day_transcript_lines)
    """
    data_dir = Path(state.data_dir)
    round_id = state.round_id

    if event_bus:
        await event_bus.emit_phase_change(
            "day", round_id, sorted(state.alive), _get_dead_players(state), state.mayor
        )

    # Announce deaths
    deaths: list[str] = []
    if killed:
        deaths.append(t("killed_by_mafia", killed, role_name(state.roles[killed])))
        state.eliminate(killed, "killed by mafia")
        mark_agent_dead(session_name, killed, agent_dirs[killed])
        if event_bus:
            await event_bus.emit_death(killed, "mafia_kill", state.roles[killed])
        # Mayor succession if killed player was mayor
        await _handle_mayor_succession(
            state, agent_dirs, agents, killed, session_name, event_bus=event_bus
        )

    if poisoned:
        deaths.append(t("killed_by_poison", poisoned, role_name(state.roles[poisoned])))
        state.eliminate(poisoned, "poisoned by doctor")
        mark_agent_dead(session_name, poisoned, agent_dirs[poisoned])
        if event_bus:
            await event_bus.emit_death(poisoned, "poison", state.roles[poisoned])
        # Mayor succession if poisoned player was mayor
        await _handle_mayor_succession(
            state, agent_dirs, agents, poisoned, session_name, event_bus=event_bus
        )

    death_announcement = "\n".join(deaths) if deaths else t("no_deaths")

    # Log to all alive agents
    for name in state.alive:
        log_to_agent(agent_dirs[name], t("day", round_id))
        log_to_agent(agent_dirs[name], death_announcement)

    if event_bus and not deaths:
        await event_bus.emit_system_message(t("no_deaths"))

    # Check win condition
    winner = state.check_win()
    if winner:
        return None, []

    alive_agents = {name: agents[name] for name in state.alive}

    transcript_path = str(data_dir / f"DAY_{round_id}.txt")

    phase_label = "白天会议" if get_lang() == "cn" else "Day Meeting"
    if get_lang() == "cn":
        meeting_context = (
            f"{_phase_context(state, phase_label)}\n\n"
            f"{death_announcement}\n\n"
            "讨论你认为谁是狼人以及谁应该被淘汰。"
            "注意观察、结成联盟、为你的判断据理力争。"
        )
    else:
        meeting_context = (
            f"{_phase_context(state, phase_label)}\n\n"
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
        log_callback=_make_dual_log(agent_dirs, event_bus),
        stream_callback=_make_dual_stream(agent_dirs, event_bus),
        first_speaker=state.mayor,
        use_llm_consensus=use_llm_consensus,
    )

    # Vote
    for name in state.alive:
        log_to_agent(agent_dirs[name], t("voting"))

    eliminated, vote_results = await run_vote(
        participants=alive_agents,
        stream_callback=_make_dual_stream(agent_dirs, event_bus),
        mayor=state.mayor,
    )

    # Emit votes to web
    if event_bus:
        for voter, data in vote_results.items():
            await event_bus.emit_vote(voter, data["vote"], data.get("reasoning", ""))
        await event_bus.emit_vote_result("eliminate", eliminated)

    # Append vote results to transcript (no reasoning, just votes + outcome)
    eliminated_role = state.roles[eliminated] if eliminated else None
    vote_lines = [f"\n{t('day_vote_header')}"]
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
        state.eliminate(eliminated, "voted out")
        mark_agent_dead(session_name, eliminated, agent_dirs[eliminated])
        for name in state.alive:
            log_to_agent(
                agent_dirs[name],
                t(
                    "voted_out_announcement",
                    eliminated,
                    role_name(state.roles[eliminated]),
                ),
            )
        if event_bus:
            await event_bus.emit_death(eliminated, "voted_out", state.roles[eliminated])
        # Mayor succession if voted-out player was mayor
        await _handle_mayor_succession(
            state, agent_dirs, agents, eliminated, session_name, event_bus=event_bus
        )

    return eliminated, transcript_lines


async def diary_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    day_transcript_lines: list[str],
    event_bus: GameEventBus | None = None,
) -> None:
    """Have all agents (alive and dead) write diary and knowledge files."""
    round_id = state.round_id
    alive_sorted = sorted(state.alive)

    if event_bus:
        await event_bus.emit_phase_change(
            "diary",
            round_id,
            sorted(state.alive),
            _get_dead_players(state),
            state.mayor,
        )

    # Build the day transcript string
    day_transcript = (
        "\n".join(day_transcript_lines) if day_transcript_lines else t("no_day_meeting")
    )

    async def _write_diary(name: str) -> None:
        log_to_agent(agent_dirs[name], t("writing_diary_round", round_id))

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

        def _stream(text: str, n: str = name) -> None:
            stream_to_agent(agent_dirs[n], text)
            if event_bus is not None:
                asyncio.ensure_future(event_bus.emit_diary_chunk(n, text))

        text = await _get_agent_response(
            name,
            agents[name],
            prompt,
            stream_callback=_stream,
        )

        log_to_agent(agent_dirs[name], t("diary_written"))
        if event_bus:
            await event_bus.emit_diary_entry(name, text)

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_write_diary(n) for n in eligible))


async def postgame_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    winner: str,
    event_bus: GameEventBus | None = None,
) -> None:
    """Have all agents reflect on the completed game, update knowledge, and write lessons learned."""
    logger.info(t("postgame_reflection"))

    if event_bus:
        await event_bus.emit_phase_change(
            "postgame",
            state.round_id,
            sorted(state.alive),
            _get_dead_players(state),
            state.mayor,
        )

    other_players = {
        name: [p for p in state.players if p != name] for name in state.players
    }

    async def _reflect(name: str) -> None:
        log_to_agent(agent_dirs[name], t("postgame_reflection_agent"))

        prompt = postgame_prompt(
            agent_name=name,
            agent_role=state.roles[name],
            winner=winner,
            all_roles=state.roles,
            eliminated=state.eliminated,
            total_rounds=state.round_id,
            other_players=other_players[name],
        )

        def _stream(text: str, n: str = name) -> None:
            stream_to_agent(agent_dirs[n], text)
            if event_bus is not None:
                asyncio.ensure_future(event_bus.emit_diary_chunk(n, text))

        text = await _get_agent_response(
            name,
            agents[name],
            prompt,
            stream_callback=_stream,
        )

        log_to_agent(agent_dirs[name], t("postgame_reflection_complete"))
        if event_bus:
            await event_bus.emit_diary_entry(name, text)

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_reflect(n) for n in eligible))
