"""Meeting room with eagerness-based speaker selection and voting."""

import asyncio
import json
import math
import random
import re
from dataclasses import dataclass
from typing import Any

from pi_sdk import (
    Agent,
    LLMClient,
    TextDelta,
    ToolExecEnd,
    ToolExecStart,
    UserMessage,
)

from event_bus import EventBus
from events import (
    ConsensusReached,
    Eagerness,
    EagernessConsensus,
    FacilitatorReasoning,
    MayorTiebreak,
    SilentTurn,
    Speech,
    SpeakerChosen,
    SpeechChunk,
    ToolCall,
    ToolResult,
    Vote,
    VoteResult,
)
from i18n import get_lang, t
from prompts import (
    consensus_prompt,
    eagerness_prompt,
    mafia_kill_vote_prompt,
    mayor_tiebreak_prompt,
    mayor_vote_prompt,
    vote_prompt,
)

from loguru import logger


# --- JSON schemas for structured output ---

VOTE_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "vote",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "vote": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["vote", "reasoning"],
            "additionalProperties": False,
        },
    },
}

EAGERNESS_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "eagerness",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "eagerness": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["eagerness", "reason"],
            "additionalProperties": False,
        },
    },
}

CONSENSUS_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "consensus",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "consensus_reached": {"type": "boolean"},
                "consensus_target": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["consensus_reached", "consensus_target", "reasoning"],
            "additionalProperties": False,
        },
    },
}


async def _llm_single_response(
    llm: LLMClient,
    system_prompt: str,
    user_prompt: str,
    retries: int = 2,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Get a single text response from an LLM (no tools, no agent loop)."""
    messages = [UserMessage(content=user_prompt)]
    for attempt in range(retries + 1):
        try:
            text = ""
            async for event in llm.stream(
                messages,
                tools=None,
                system_prompt=system_prompt,
                response_format=response_format,
            ):
                if isinstance(event.event, TextDelta):
                    text += event.event.delta
            return text
        except Exception as e:
            logger.error(
                "LLM call failed (attempt {}/{}): {}", attempt + 1, retries + 1, e
            )
            if attempt == retries:
                return ""


def _extract_speak(text: str) -> str | None:
    """Extract content from <speak>...</speak> tags.

    Returns the speech content, or None if no tags found (agent chose silence).
    """
    match = re.search(r"<speak>(.*?)</speak>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


async def _validate_speech_perspective(
    speech: str, speaker_name: str, llm: LLMClient
) -> bool:
    """Check if speech refers to the speaker in the third person.

    Returns True if the speech is fine (first-person), False if the speaker
    refers to themselves in the third person.
    """
    user_prompt = (
        f'The speaker\'s name is "{speaker_name}". Does the following speech '
        f"refer to the speaker in the third person (e.g., using their own name "
        f'as if they are someone else)? Reply ONLY "yes" or "no".\n\n'
        f'Speech: "{speech}"'
    )
    response = await _llm_single_response(
        llm,
        "You are a speech perspective checker.",
        user_prompt,
        retries=1,
    )
    return "yes" not in response.strip().lower()


async def _get_agent_response(
    agent_name: str,
    agent: Agent,
    prompt: str,
    bus: EventBus | None = None,
    channel: str = "public",
    context: str = "speech",
    retries: int = 2,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Run agent.run() for a single turn and collect the text response.

    Emits SpeechChunk / ToolCall / ToolResult events on the bus (if provided)
    as the agent streams output.
    """
    for attempt in range(retries + 1):
        try:
            text = ""
            async for event in agent.run(prompt, response_format=response_format):
                if isinstance(event, TextDelta):
                    text += event.delta
                    if bus is not None:
                        bus.emit(
                            SpeechChunk(
                                channel=channel,
                                speaker=agent_name,
                                delta=event.delta,
                                context=context,
                            )
                        )
                elif isinstance(event, ToolExecStart):
                    if bus is not None:
                        bus.emit(
                            ToolCall(
                                channel=channel,
                                speaker=agent_name,
                                name=event.name,
                                arguments_summary=str(event.arguments)[:80],
                            )
                        )
                elif isinstance(event, ToolExecEnd):
                    if bus is not None:
                        bus.emit(
                            ToolResult(
                                channel=channel,
                                speaker=agent_name,
                                result_preview=(event.content or "")[:120],
                            )
                        )
            return text
        except Exception as e:
            logger.error(
                "Agent {} failed (attempt {}/{}): {}",
                agent_name,
                attempt + 1,
                retries + 1,
                e,
            )
            if attempt == retries:
                return ""


def _strip_markdown_json(text: str) -> str:
    """Strip markdown code block wrappers (```json ... ``` or ``` ... ```) from text."""
    stripped = text.strip()
    match = re.match(r"```(?:json)?\s*\n?(.*?)```\s*$", stripped, re.DOTALL)
    return match.group(1).strip() if match else stripped


async def _get_agent_json(
    agent_name: str,
    agent: Agent,
    prompt: str,
    bus: EventBus | None = None,
    channel: str = "public",
    context: str = "speech",
    response_format: dict[str, Any] | None = None,
    parse_retries: int = 2,
) -> dict | None:
    """Get a JSON response from an agent, retrying on parse failure."""
    response = await _get_agent_response(
        agent_name,
        agent,
        prompt,
        bus=bus,
        channel=channel,
        context=context,
        response_format=response_format,
    )

    for attempt in range(parse_retries + 1):
        try:
            logger.debug("Raw JSON response: {}", response)
            return json.loads(_strip_markdown_json(response))
        except (json.JSONDecodeError, TypeError):
            if attempt == parse_retries:
                logger.warning(
                    "Failed to parse JSON from {} after {} retries: {}",
                    agent_name,
                    parse_retries,
                    response[:200],
                )
                return None
            logger.warning(
                "JSON parse failed for {} (attempt {}), asking to retry",
                agent_name,
                attempt + 1,
            )
            response = await _get_agent_response(
                agent_name,
                agent,
                "Your previous response was not valid JSON. "
                "Please respond with ONLY the required JSON object, nothing else.",
                bus=bus,
                channel=channel,
                context=context,
                response_format=response_format,
            )


@dataclass
class ConsensusResult:
    """Result from the facilitator's consensus check."""

    consensus_reached: bool = False
    consensus_target: str = ""


async def poll_eagerness(
    participants: dict[str, Agent],
    transcript_lines: list[str],
    initialized: set[str],
    meeting_context: str,
    bus: EventBus | None = None,
    meeting_channel: str = "public",
    latest_speech: str | None = None,
) -> dict[str, float]:
    """Poll all participants for eagerness ratings in parallel."""

    async def _poll_one(name: str, agent: Agent) -> tuple[str, float]:
        if name not in initialized:
            if get_lang() == "cn":
                transcript_so_far = (
                    "\n".join(transcript_lines)
                    if transcript_lines
                    else "（会议刚开始）"
                )
                context = f"{meeting_context}\n\n目前的会议记录:\n{transcript_so_far}"
            else:
                transcript_so_far = (
                    "\n".join(transcript_lines)
                    if transcript_lines
                    else "(meeting just started)"
                )
                context = f"{meeting_context}\n\nMeeting transcript so far:\n{transcript_so_far}"
        else:
            if get_lang() == "cn":
                context = latest_speech or "（无新消息）"
            else:
                context = latest_speech or "(no new messages)"

        prompt = eagerness_prompt(context)
        parsed = await _get_agent_json(
            name,
            agent,
            prompt,
            bus=bus,
            channel=meeting_channel,
            context="eagerness",
            response_format=EAGERNESS_SCHEMA,
        )

        initialized.add(name)

        if isinstance(parsed, dict) and "eagerness" in parsed:
            rating = float(parsed["eagerness"])
            rating = max(0, min(10.0, rating))
            reason = parsed.get("reason", "")
            if bus is not None:
                bus.emit(
                    Eagerness(
                        channel=meeting_channel,
                        name=name,
                        rating=rating,
                        reason=reason,
                    )
                )
            return name, rating

        logger.warning("Failed to get eagerness from {}, defaulting to 0.0", name)
        return name, 0.0

    results = await asyncio.gather(
        *(_poll_one(name, agent) for name, agent in participants.items())
    )
    return dict(results)


async def check_consensus(
    facilitator: Agent,
    participants: list[str],
    transcript_lines: list[str],
    bus: EventBus | None = None,
    meeting_channel: str = "public",
) -> ConsensusResult:
    """Ask the facilitator if unanimous consensus has been reached."""
    facilitator.reset()
    recent = (
        "\n".join(transcript_lines[-20:]) if transcript_lines else "(no transcript yet)"
    )
    prompt = consensus_prompt(participants, recent)
    parsed = await _get_agent_json(
        "facilitator",
        facilitator,
        prompt,
        bus=bus,
        channel=meeting_channel,
        context="speech",
        response_format=CONSENSUS_SCHEMA,
    )

    if not parsed:
        return ConsensusResult()

    reasoning = parsed.get("reasoning", "")
    if reasoning and bus is not None:
        bus.emit(FacilitatorReasoning(channel=meeting_channel, text=reasoning))

    return ConsensusResult(
        consensus_reached=bool(parsed.get("consensus_reached", False)),
        consensus_target=str(parsed.get("consensus_target", "")),
    )


async def run_meeting(
    participants: dict[str, Agent],
    facilitator: Agent,
    transcript_path: str,
    max_rounds: int,
    meeting_context: str,
    bus: EventBus | None = None,
    meeting_channel: str = "public",
    first_speaker: str | None = None,
    use_llm_consensus: bool = False,
) -> list[str]:
    """Run a meeting with eagerness-based speaker selection."""
    participant_names = list(participants.keys())
    transcript_lines: list[str] = []
    last_speaker: str | None = None
    initialized: set[str] = set()
    latest_speech: str | None = None

    with open(transcript_path, "w") as f:
        f.write(f"{t('meeting_transcript')}\n\n")

    for round_num in range(max_rounds):
        if round_num == 0 and first_speaker and first_speaker in participants:
            others = {n: a for n, a in participants.items() if n != first_speaker}
            if others:
                await poll_eagerness(
                    others,
                    transcript_lines,
                    initialized,
                    meeting_context,
                    bus=bus,
                    meeting_channel=meeting_channel,
                    latest_speech=latest_speech,
                )
            speaker = first_speaker
        else:
            eagerness = await poll_eagerness(
                participants,
                transcript_lines,
                initialized,
                meeting_context,
                bus=bus,
                meeting_channel=meeting_channel,
                latest_speech=latest_speech,
            )

            if last_speaker and last_speaker in eagerness and len(eagerness) > 1:
                eagerness[last_speaker] = float("-inf")

            if transcript_lines and all(v <= 3 for v in eagerness.values()):
                if bus is not None:
                    bus.emit(
                        EagernessConsensus(
                            channel=meeting_channel, round_num=round_num + 1
                        )
                    )
                break

            names = list(eagerness.keys())
            weight_values = [
                math.exp(eagerness[n]) if eagerness[n] > 0 else 0 for n in names
            ]
            speaker = random.choices(names, weights=weight_values, k=1)[0]

        if bus is not None:
            bus.emit(
                SpeakerChosen(
                    channel=meeting_channel, speaker=speaker, round_num=round_num + 1
                )
            )

        if speaker not in initialized:
            if get_lang() == "cn":
                transcript_so_far = (
                    "\n".join(transcript_lines)
                    if transcript_lines
                    else "（会议刚开始）"
                )
                prompt = f"""{meeting_context}

目前的会议记录:
{transcript_so_far}

轮到你发言了。请保持简洁，2-4句话。"""
            else:
                transcript_so_far = (
                    "\n".join(transcript_lines)
                    if transcript_lines
                    else "(meeting just started)"
                )
                prompt = f"""{meeting_context}

Meeting transcript so far:
{transcript_so_far}

It's your turn to speak. Keep your response to 2-4 sentences."""
            initialized.add(speaker)
        else:
            if get_lang() == "cn":
                prompt = "轮到你发言了。请保持简洁，2-4句话。"
            else:
                prompt = "It's your turn to speak. Keep your response to 2-4 sentences."

        agent = participants[speaker]
        response = await _get_agent_response(
            speaker,
            agent,
            prompt,
            bus=bus,
            channel=meeting_channel,
            context="speech",
        )
        response = response.strip()

        speech = _extract_speak(response)
        if not speech:
            if bus is not None:
                bus.emit(
                    SilentTurn(
                        channel=meeting_channel,
                        speaker=speaker,
                        round_num=round_num + 1,
                    )
                )
            continue

        perspective_ok = await _validate_speech_perspective(
            speech, speaker, facilitator.llm
        )
        if not perspective_ok:
            logger.warning(
                "Round {} - {}: third-person speech detected, retrying",
                round_num + 1,
                speaker,
            )
            if get_lang() == "cn":
                retry_prompt = (
                    f"{prompt}\n\n"
                    f"重要：你就是 {speaker}。请用第一人称说话。"
                    f"不要用自己的名字或第三人称称呼自己。"
                )
            else:
                retry_prompt = (
                    f"{prompt}\n\n"
                    f"IMPORTANT: You ARE {speaker}. Speak in first person. "
                    f"Do not refer to yourself by name or in the third person."
                )
            response = await _get_agent_response(
                speaker,
                agent,
                retry_prompt,
                bus=bus,
                channel=meeting_channel,
                context="speech",
            )
            response = response.strip()
            speech = _extract_speak(response)
            if not speech:
                if bus is not None:
                    bus.emit(
                        SilentTurn(
                            channel=meeting_channel,
                            speaker=speaker,
                            round_num=round_num + 1,
                        )
                    )
                continue

        line = f"**{speaker}**: {speech}"
        transcript_lines.append(line)
        latest_speech = line
        last_speaker = speaker

        with open(transcript_path, "a") as f:
            f.write(f"{line}\n\n")

        if bus is not None:
            bus.emit(
                Speech(
                    channel=meeting_channel,
                    speaker=speaker,
                    round_num=round_num + 1,
                    text=speech,
                )
            )

        if use_llm_consensus:
            result = await check_consensus(
                facilitator,
                participant_names,
                transcript_lines,
                bus=bus,
                meeting_channel=meeting_channel,
            )
            if result.consensus_reached and result.consensus_target:
                if bus is not None:
                    bus.emit(
                        ConsensusReached(
                            channel=meeting_channel,
                            round_num=round_num + 1,
                            target=result.consensus_target,
                        )
                    )
                break

    return transcript_lines


async def _mayor_tiebreak(
    mayor_name: str,
    mayor_agent: Agent,
    tied_options: list[str],
    bus: EventBus | None = None,
    channel: str = "public",
    max_retries: int = 2,
) -> str:
    """Ask the mayor to break a tie between two options, retrying on invalid choice."""
    options_str = ", ".join(f'"{opt}"' for opt in tied_options)
    prompt_text = mayor_tiebreak_prompt(tied_options)

    for attempt in range(max_retries + 1):
        parsed = await _get_agent_json(
            mayor_name,
            mayor_agent,
            prompt_text,
            bus=bus,
            channel=channel,
            context="vote",
            response_format=VOTE_SCHEMA,
        )
        if isinstance(parsed, dict) and "vote" in parsed:
            choice = parsed["vote"]
            if choice in tied_options:
                if bus is not None:
                    bus.emit(
                        MayorTiebreak(
                            channel=channel,
                            mayor=mayor_name,
                            chosen=choice,
                            tied_between=tied_options,
                        )
                    )
                return choice
            logger.warning(
                "Mayor {} chose invalid option '{}' (attempt {}/{})",
                mayor_name,
                choice,
                attempt + 1,
                max_retries + 1,
            )
            if attempt < max_retries:
                prompt_text = (
                    f'Your choice "{choice}" is not valid. '
                    f"You must choose one of: {options_str}. Please try again.\n\n"
                    f'Return ONLY valid JSON: {{"vote": "<option>", "reasoning": "..."}}'
                )
                continue
        else:
            logger.warning(
                "Failed to parse mayor tiebreak response (attempt {}/{})",
                attempt + 1,
                max_retries + 1,
            )
            if attempt < max_retries:
                prompt_text = (
                    "Your response could not be parsed. "
                    f"You must choose one of: {options_str}.\n\n"
                    f'Return ONLY valid JSON: {{"vote": "<option>", "reasoning": "..."}}'
                )
                continue

    fallback = random.choice(tied_options)
    logger.warning(
        "Mayor tiebreak failed after retries, falling back to random choice: {}",
        fallback,
    )
    if bus is not None:
        bus.emit(
            MayorTiebreak(
                channel=channel,
                mayor=mayor_name,
                chosen=fallback,
                tied_between=tied_options,
            )
        )
    return fallback


async def run_vote(
    participants: dict[str, Agent],
    vote_type: str = "eliminate",
    valid_targets: list[str] | None = None,
    bus: EventBus | None = None,
    channel: str = "public",
    mayor: str | None = None,
) -> tuple[str | None, dict[str, dict]]:
    """Run a vote among participants."""
    participant_names = list(participants.keys())
    votes: dict[str, dict] = {}

    async def _cast_vote(name: str, agent: Agent) -> tuple[str, dict]:
        if vote_type == "kill":
            candidates = valid_targets or [p for p in participant_names if p != name]
            prompt_text = mafia_kill_vote_prompt(candidates)
        elif vote_type == "mayor":
            candidates = valid_targets or participant_names
            prompt_text = mayor_vote_prompt(participant_names)
        else:
            candidates = [p for p in participant_names if p != name]
            prompt_text = vote_prompt(participant_names, name, mayor=mayor)

        parsed = await _get_agent_json(
            name,
            agent,
            prompt_text,
            bus=bus,
            channel=channel,
            context="vote",
            response_format=VOTE_SCHEMA,
        )

        if isinstance(parsed, dict) and "vote" in parsed:
            vote_target = parsed["vote"]
            if vote_target != "abstain" and vote_target not in candidates:
                raise ValueError(
                    f"Invalid vote from {name}: '{vote_target}' not in candidates {candidates}"
                )
            return name, parsed
        raise RuntimeError(f"Failed to parse vote from {name} after retries")

    results = await asyncio.gather(
        *(_cast_vote(name, agent) for name, agent in participants.items())
    )
    for name, vote_data in results:
        votes[name] = vote_data
        if bus is not None:
            bus.emit(
                Vote(
                    channel=channel,
                    voter=name,
                    target=vote_data["vote"],
                    reasoning=vote_data.get("reasoning", ""),
                    vote_type=vote_type,
                )
            )

    tally: dict[str, int] = {}
    for voter, vote_data in votes.items():
        target = vote_data["vote"]
        if vote_type == "eliminate":
            tally[target] = tally.get(target, 0) + 1
        else:
            if target != "abstain":
                tally[target] = tally.get(target, 0) + 1

    if not tally:
        if bus is not None:
            bus.emit(
                VoteResult(
                    channel=channel,
                    vote_type=vote_type,
                    winner=None,
                    reason="no_votes",
                )
            )
        return None, votes

    max_votes = max(tally.values())
    tied = [name for name, count in tally.items() if count == max_votes]

    if vote_type == "eliminate":
        total_voters = len(votes)
        majority_threshold = total_voters / 2
        if max_votes < majority_threshold:
            if bus is not None:
                bus.emit(
                    VoteResult(
                        channel=channel,
                        vote_type=vote_type,
                        winner=None,
                        reason="no_majority",
                        tied=tied,
                    )
                )
            return None, votes

        if (
            len(tied) == 2
            and max_votes == majority_threshold
            and mayor
            and mayor in participants
        ):
            tiebreak_winner = await _mayor_tiebreak(
                mayor, participants[mayor], tied, bus=bus, channel=channel
            )
            if tiebreak_winner == "abstain":
                if bus is not None:
                    bus.emit(
                        VoteResult(
                            channel=channel,
                            vote_type=vote_type,
                            winner=None,
                            reason="tiebreak_abstain",
                            tied=tied,
                        )
                    )
                return None, votes
            if bus is not None:
                bus.emit(
                    VoteResult(
                        channel=channel,
                        vote_type=vote_type,
                        winner=tiebreak_winner,
                        reason="tiebreak",
                        tied=tied,
                    )
                )
            return tiebreak_winner, votes

        if len(tied) > 1:
            if bus is not None:
                bus.emit(
                    VoteResult(
                        channel=channel,
                        vote_type=vote_type,
                        winner=None,
                        reason="tie",
                        tied=tied,
                    )
                )
            return None, votes

        winner = tied[0]
        if winner == "abstain":
            if bus is not None:
                bus.emit(
                    VoteResult(
                        channel=channel,
                        vote_type=vote_type,
                        winner=None,
                        reason="abstain_majority",
                    )
                )
            return None, votes
        if bus is not None:
            bus.emit(
                VoteResult(
                    channel=channel,
                    vote_type=vote_type,
                    winner=winner,
                    reason="majority",
                )
            )
        return winner, votes

    if len(tied) > 1:
        if bus is not None:
            bus.emit(
                VoteResult(
                    channel=channel,
                    vote_type=vote_type,
                    winner=None,
                    reason="tie",
                    tied=tied,
                )
            )
        return None, votes

    winner = tied[0]
    if bus is not None:
        bus.emit(
            VoteResult(
                channel=channel,
                vote_type=vote_type,
                winner=winner,
                reason="plurality",
            )
        )
    return winner, votes
