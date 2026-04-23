"""Orchestrator for Mafia game phases: night, day, and diary."""

from __future__ import annotations

import asyncio
import random
import shutil
from collections import Counter
from pathlib import Path

from pi_sdk import Agent

from event_bus import EventBus
from events import (
    Death,
    DiaryEntry,
    MayorElected,
    NightAction,
    PhaseChange,
    PostgameReflection,
    SystemMessage,
    player_channel,
)
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
    DOCTOR_ACTION_SCHEMA,
    INVESTIGATE_SCHEMA,
    PROTECT_SCHEMA,
    detective_prompt,
    doctor_prompt,
    guardian_prompt,
)

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
    return [p for p in state.players if p not in state.alive]


def _get_mafia_allies_alive(state: GameState, name: str) -> list[str] | None:
    if state.roles.get(name) != "mafia":
        return None
    return [m for m in state.get_by_role("mafia") if m != name]


def _phase_context(
    state: GameState,
    phase: str,
    name: str | None = None,
) -> str:
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


def _emit_phase(bus: EventBus, state: GameState, phase: str) -> None:
    bus.emit(
        PhaseChange(
            phase=phase,
            round_id=state.round_id,
            alive=sorted(state.alive),
            dead=_get_dead_players(state),
            mayor=state.mayor,
        )
    )


async def mayor_election_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    facilitator: Agent,
    mayor_rounds: int,
    bus: EventBus,
    use_llm_consensus: bool = False,
) -> None:
    """Run the Day 0 mayor election: discussion + vote."""
    data_dir = Path(state.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    _emit_phase(bus, state, "mayor_election")

    alive_agents = {name: agents[name] for name in state.alive}
    transcript_path = str(data_dir / "DAY_0_MAYOR_ELECTION.txt")

    meeting_context = mayor_election_meeting_prompt(sorted(state.alive))

    await run_meeting(
        participants=alive_agents,
        facilitator=facilitator,
        transcript_path=transcript_path,
        max_rounds=mayor_rounds,
        meeting_context=meeting_context,
        bus=bus,
        meeting_channel="public",
        use_llm_consensus=use_llm_consensus,
    )

    bus.emit(SystemMessage(text=t("mayor_vote")))

    winner, vote_results = await run_vote(
        participants=alive_agents,
        vote_type="mayor",
        bus=bus,
        channel="public",
    )

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
        bus.emit(MayorElected(name=winner, via="vote"))
    else:
        tally = Counter(
            d["vote"] for d in vote_results.values() if d["vote"] != "abstain"
        )
        if tally:
            max_count = max(tally.values())
            tied = [n for n, c in tally.items() if c == max_count]
            state.mayor = random.choice(tied)
            bus.emit(MayorElected(name=state.mayor, via="tiebreak_random"))

    _distribute_transcript(transcript_path, agent_dirs, state.players)


async def mayor_election_diary_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    bus: EventBus,
) -> None:
    """Have all agents write a Day 0 diary after the mayor election."""
    data_dir = Path(state.data_dir)
    transcript_path = data_dir / "DAY_0_MAYOR_ELECTION.txt"
    election_transcript = (
        transcript_path.read_text() if transcript_path.exists() else ""
    )

    alive_sorted = sorted(state.alive)

    _emit_phase(bus, state, "diary")

    async def _write_diary(name: str) -> None:
        prompt = mayor_election_diary_prompt(name, alive_sorted, election_transcript)
        text = await _get_agent_response(
            name,
            agents[name],
            prompt,
            bus=bus,
            channel=player_channel(name),
            context="diary",
        )
        bus.emit(
            DiaryEntry(
                channel=player_channel(name),
                name=name,
                round_id=0,
                text=text,
            )
        )

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_write_diary(n) for n in eligible))


async def _handle_mayor_succession(
    state: GameState,
    agents: dict[str, Agent],
    dead_player: str,
    bus: EventBus,
) -> None:
    """If the dead player is the mayor, have them appoint a successor."""
    if state.mayor != dead_player:
        return

    alive_list = sorted(state.alive)
    if not alive_list:
        state.mayor = None
        return

    bus.emit(SystemMessage(text=t("mayor_dying_successor", dead_player)))

    if dead_player in agents:
        prompt = mayor_succession_prompt(dead_player, alive_list)
        parsed = await _get_agent_json(
            dead_player,
            agents[dead_player],
            prompt,
            bus=bus,
            channel=player_channel(dead_player),
            context="vote",
            response_format=VOTE_SCHEMA,
        )

        if (
            parsed
            and parsed.get("vote") in alive_list
            and parsed["vote"] != dead_player
        ):
            state.mayor = parsed["vote"]
            bus.emit(MayorElected(name=state.mayor, via="succession"))
            return

    state.mayor = alive_list[0]
    bus.emit(MayorElected(name=state.mayor, via="succession_fallback"))


async def night_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    facilitator: Agent,
    mafia_rounds: int,
    bus: EventBus,
    use_llm_consensus: bool = False,
) -> tuple[str | None, str | None]:
    """Run the night phase.

    Returns:
        (killed_name or None, poisoned_name or None)
    """
    data_dir = Path(state.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    round_id = state.round_id

    _emit_phase(bus, state, "night")

    # === PHASE 1: Detective, Mafia, and Guardian act simultaneously ===

    async def _detective_action() -> None:
        detectives = state.get_by_role("detective")
        if not detectives:
            return
        detective = detectives[0]
        channel = player_channel(detective)

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
            bus=bus,
            channel=channel,
            context="night_action",
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
            bus.emit(
                NightAction(
                    channel=channel,
                    role="detective",
                    actor=detective,
                    action="investigate",
                    target=investigated,
                    outcome="mafia" if is_mafia else "not_mafia",
                )
            )
        else:
            result_text = t("investigation_failed", round_id) + "\n"
            bus.emit(
                NightAction(
                    channel=channel,
                    role="detective",
                    actor=detective,
                    action="investigate",
                    target=None,
                    outcome="failed",
                )
            )

        notes_path = data_dir / f"NIGHT_DETECTIVE_NOTES_{round_id}.txt"
        notes_path.write_text(result_text)
        _distribute_transcript(str(notes_path), agent_dirs, [detective])

    async def _mafia_action() -> str | None:
        mafia_members = state.get_by_role("mafia")
        if not mafia_members:
            return None

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
                bus=bus,
                channel=player_channel(mafia_name),
                context="night_action",
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
                bus=bus,
                meeting_channel="mafia",
                use_llm_consensus=use_llm_consensus,
            )

            all_targets = sorted(state.alive)
            target, vote_results = await run_vote(
                participants=mafia_agents,
                vote_type="kill",
                valid_targets=all_targets,
                bus=bus,
                channel="mafia",
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

        bus.emit(
            NightAction(
                channel="mafia",
                role="mafia",
                actor="mafia",
                action="kill",
                target=target,
                outcome="targeted" if target else "no_kill",
            )
        )

        return target

    async def _guardian_action() -> str | None:
        guardians = state.get_by_role("guardian")
        if not guardians:
            return None

        guardian_name = guardians[0]
        channel = player_channel(guardian_name)

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
            bus=bus,
            channel=channel,
            context="night_action",
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

        bus.emit(
            NightAction(
                channel=channel,
                role="guardian",
                actor=guardian_name,
                action="protect",
                target=result,
                outcome="protected" if result else "failed",
            )
        )

        return result

    _, killed, protected = await asyncio.gather(
        _detective_action(),
        _mafia_action(),
        _guardian_action(),
    )

    if protected and killed == protected:
        guardians = state.get_by_role("guardian")
        guardian_name = guardians[0] if guardians else None
        killed = None
        if guardian_name:
            bus.emit(
                SystemMessage(
                    channel=player_channel(guardian_name),
                    text=t("guardian_saved", protected),
                )
            )

    # === PHASE 2: Doctor acts after seeing the post-guardian result ===
    doctors = state.get_by_role("doctor")
    doctor_saved = False
    poisoned = None
    if doctors and (state.doctor_has_save or state.doctor_has_poison):
        doctor_name = doctors[0]
        channel = player_channel(doctor_name)

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
            bus=bus,
            channel=channel,
            context="night_action",
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
                bus.emit(
                    NightAction(
                        channel=channel,
                        role="doctor",
                        actor=doctor_name,
                        action="save",
                        target=killed,
                        outcome="saved",
                    )
                )
            elif parsed.get("save") and not state.doctor_has_save:
                notes_parts.append(t("save_already_used") + "\n")
            elif parsed.get("save") and not killed:
                notes_parts.append(t("save_no_target") + "\n")

            poison_target = parsed.get("poison", "")
            if poison_target and state.doctor_has_poison:
                valid_poison = [
                    p for p in state.alive if p != doctor_name and p != killed
                ]
                if poison_target in valid_poison:
                    poisoned = poison_target
                    state.doctor_has_poison = False
                    notes_parts.append(t("used_poison", poisoned) + "\n")
                    bus.emit(
                        NightAction(
                            channel=channel,
                            role="doctor",
                            actor=doctor_name,
                            action="poison",
                            target=poisoned,
                            outcome="poisoned",
                        )
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

    if doctor_saved and killed:
        bus.emit(
            SystemMessage(
                channel=player_channel(doctor_name),
                text=t("doctor_saved", killed),
            )
        )
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
    bus: EventBus,
    use_llm_consensus: bool = False,
) -> tuple[str | None, list[str]]:
    """Run the day phase.

    Returns:
        (eliminated_name or None, day_transcript_lines)
    """
    data_dir = Path(state.data_dir)
    round_id = state.round_id

    _emit_phase(bus, state, "day")

    deaths: list[str] = []
    if killed:
        deaths.append(t("killed_by_mafia", killed, role_name(state.roles[killed])))
        state.eliminate(killed, "killed by mafia")
        bus.emit(Death(player=killed, cause="mafia_kill", role=state.roles[killed]))
        await _handle_mayor_succession(state, agents, killed, bus)

    if poisoned:
        deaths.append(t("killed_by_poison", poisoned, role_name(state.roles[poisoned])))
        state.eliminate(poisoned, "poisoned by doctor")
        bus.emit(Death(player=poisoned, cause="poison", role=state.roles[poisoned]))
        await _handle_mayor_succession(state, agents, poisoned, bus)

    death_announcement = "\n".join(deaths) if deaths else t("no_deaths")

    if not deaths:
        bus.emit(SystemMessage(text=t("no_deaths")))

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
        bus=bus,
        meeting_channel="public",
        first_speaker=state.mayor,
        use_llm_consensus=use_llm_consensus,
    )

    bus.emit(SystemMessage(text=t("voting")))

    eliminated, vote_results = await run_vote(
        participants=alive_agents,
        bus=bus,
        channel="public",
        mayor=state.mayor,
    )

    eliminated_role = state.roles[eliminated] if eliminated else None
    vote_lines = [f"\n{t('day_vote_header')}"]
    for voter, data in vote_results.items():
        vote_lines.append(f"{voter} voted: {data['vote']}")
    vote_lines.append(f"\n{format_vote_outcome(eliminated, eliminated_role)}")

    with open(transcript_path, "a") as f:
        f.write("\n".join(vote_lines) + "\n")

    transcript_lines.extend(vote_lines)

    _distribute_transcript(transcript_path, agent_dirs, state.players)

    if eliminated:
        state.eliminate(eliminated, "voted out")
        bus.emit(
            Death(player=eliminated, cause="voted_out", role=state.roles[eliminated])
        )
        await _handle_mayor_succession(state, agents, eliminated, bus)

    return eliminated, transcript_lines


async def diary_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    day_transcript_lines: list[str],
    bus: EventBus,
) -> None:
    """Have all agents (alive and dead) write diary and knowledge files."""
    round_id = state.round_id
    alive_sorted = sorted(state.alive)

    _emit_phase(bus, state, "diary")

    day_transcript = (
        "\n".join(day_transcript_lines) if day_transcript_lines else t("no_day_meeting")
    )

    async def _write_diary(name: str) -> None:
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
        text = await _get_agent_response(
            name,
            agents[name],
            prompt,
            bus=bus,
            channel=player_channel(name),
            context="diary",
        )

        bus.emit(
            DiaryEntry(
                channel=player_channel(name),
                name=name,
                round_id=round_id,
                text=text,
            )
        )

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_write_diary(n) for n in eligible))


async def postgame_phase(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    winner: str,
    bus: EventBus,
) -> None:
    """Have all agents reflect on the completed game, update knowledge, and write lessons learned."""
    _emit_phase(bus, state, "postgame")

    other_players = {
        name: [p for p in state.players if p != name] for name in state.players
    }

    async def _reflect(name: str) -> None:
        prompt = postgame_prompt(
            agent_name=name,
            agent_role=state.roles[name],
            winner=winner,
            all_roles=state.roles,
            eliminated=state.eliminated,
            total_rounds=state.round_id,
            other_players=other_players[name],
        )

        text = await _get_agent_response(
            name,
            agents[name],
            prompt,
            bus=bus,
            channel=player_channel(name),
            context="postgame",
        )

        bus.emit(
            PostgameReflection(
                channel=player_channel(name),
                name=name,
                text=text,
            )
        )

    eligible = [n for n in sorted(state.players) if n in agent_dirs and n in agents]
    await asyncio.gather(*(_reflect(n) for n in eligible))
