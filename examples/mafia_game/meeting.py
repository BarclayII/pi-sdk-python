"""Meeting room with eagerness-based speaker selection and voting."""

import asyncio
import json
import math
import random
import re
from dataclasses import dataclass
from typing import Any, Callable

from pi_sdk import (
    Agent,
    LLMClient,
    TextDelta,
    ToolExecEnd,
    ToolExecStart,
    UserMessage,
)

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
    # "yes" means third-person detected → speech is NOT fine
    return "yes" not in response.strip().lower()


async def _get_agent_response(
    agent_name: str,
    agent: Agent,
    prompt: str,
    retries: int = 2,
    stream_callback: Callable[[str], None] | None = None,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Run agent.run() for a single turn and collect the text response.

    If stream_callback is provided, text deltas and tool events are forwarded
    to it in real time for display in tmux windows.
    """
    for attempt in range(retries + 1):
        try:
            text = ""
            async for event in agent.run(prompt, response_format=response_format):
                if isinstance(event, TextDelta):
                    text += event.delta
                    if stream_callback:
                        stream_callback(event.delta)
                elif isinstance(event, ToolExecStart):
                    if stream_callback:
                        args_summary = str(event.arguments)[:80]
                        stream_callback(f"\n[>> {event.name}({args_summary})]\n")
                elif isinstance(event, ToolExecEnd):
                    if stream_callback:
                        result_preview = (event.content or "")[:120]
                        stream_callback(f"[<< {result_preview}]\n")
            if stream_callback and text:
                stream_callback("\n")
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
    stream_callback: Callable[[str], None] | None = None,
    response_format: dict[str, Any] | None = None,
    parse_retries: int = 2,
) -> dict | None:
    """Get a JSON response from an agent, retrying on parse failure.

    On the first call, sends the original prompt. If the response isn't valid
    JSON, sends a follow-up asking the agent to fix its output (the agent
    retains conversation context so it can see what went wrong).

    Returns the parsed dict, or None if all attempts fail.
    """
    response = await _get_agent_response(
        agent_name,
        agent,
        prompt,
        stream_callback=stream_callback,
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
                f"Your previous response was not valid JSON. "
                f"Please respond with ONLY the required JSON object, nothing else.",
                stream_callback=stream_callback,
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
    latest_speech: str | None = None,
    stream_callback: Callable[[str, str], None] | None = None,
) -> dict[str, float]:
    """Poll all participants for eagerness ratings in parallel.

    Players who haven't been polled yet receive the full meeting_context +
    transcript. Players who have been polled before receive only the latest
    speech (since they already have prior context in their conversation history).

    Args:
        participants: Mapping of agent_name -> Agent.
        transcript_lines: Full transcript so far.
        initialized: Set of player names who have already been polled at least
            once. Updated in-place to include newly polled players.
        meeting_context: Context string for first-time players.
        latest_speech: The most recent transcript line (e.g. "**alice**: ...").
            None on the very first poll when no one has spoken yet.
        stream_callback: Optional (agent_name, text_chunk) callback.

    Returns a dict of participant_name -> eagerness rating (float).
    Falls back to 0.0 for any participant whose response fails.
    """

    async def _poll_one(name: str, agent: Agent) -> tuple[str, float]:
        if name not in initialized:
            # First poll: full meeting context + transcript
            transcript_so_far = (
                "\n".join(transcript_lines)
                if transcript_lines
                else "(meeting just started)"
            )
            context = (
                f"{meeting_context}\n\nMeeting transcript so far:\n{transcript_so_far}"
            )
        else:
            # Subsequent poll: only the latest speech
            context = latest_speech or "(no new messages)"

        prompt = eagerness_prompt(context)
        per_player_stream = (
            (lambda text, n=name: stream_callback(n, text)) if stream_callback else None
        )
        parsed = await _get_agent_json(
            name,
            agent,
            prompt,
            stream_callback=per_player_stream,
            response_format=EAGERNESS_SCHEMA,
        )

        initialized.add(name)

        if isinstance(parsed, dict) and "eagerness" in parsed:
            rating = float(parsed["eagerness"])
            # Clamp to [0, 10]
            rating = max(0, min(10.0, rating))
            logger.info(
                "Eagerness {}: {:.1f} ({})", name, rating, parsed.get("reason", "")
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
) -> ConsensusResult:
    """Ask the facilitator if unanimous consensus has been reached.

    Returns a ConsensusResult. Falls back to no consensus on parse failure.
    """
    facilitator.reset()
    recent = (
        "\n".join(transcript_lines[-20:]) if transcript_lines else "(no transcript yet)"
    )
    prompt = consensus_prompt(participants, recent)
    parsed = await _get_agent_json(
        "facilitator",
        facilitator,
        prompt,
        response_format=CONSENSUS_SCHEMA,
    )

    if not parsed:
        return ConsensusResult()

    reasoning = parsed.get("reasoning", "")
    if reasoning:
        logger.info("Facilitator reasoning: {}", reasoning)

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
    log_callback: Callable[[str, str], None] | None = None,
    stream_callback: Callable[[str, str], None] | None = None,
    first_speaker: str | None = None,
    use_llm_consensus: bool = False,
) -> list[str]:
    """Run a meeting with eagerness-based speaker selection.

    Each round, all players rate their eagerness to speak (-10 to 10).
    A speaker is selected via exponentially-weighted random choice.
    The meeting ends early if all participants' eagerness is negative
    (eagerness-based consensus). Optionally, an LLM facilitator can also
    check for unanimous consensus after each speech.

    Args:
        participants: Mapping of agent_name -> Agent.
        facilitator: Agent used for speech validation (and consensus detection
            when use_llm_consensus is True).
        transcript_path: Path to write the transcript file.
        max_rounds: Number of speaking rounds.
        meeting_context: Context string prepended to each agent's first prompt.
        log_callback: Optional (agent_name, message) callback for tmux logging.
        stream_callback: Optional (agent_name, text_chunk) callback for real-time
            streaming of LLM output and tool events to tmux windows.
        first_speaker: Optional player name to force as speaker for round 0.
        use_llm_consensus: If True, also run LLM-based consensus detection
            after each speech (more expensive but more nuanced).

    Returns:
        List of transcript lines.
    """
    participant_names = list(participants.keys())
    transcript_lines: list[str] = []
    last_speaker: str | None = None
    initialized: set[str] = set()
    latest_speech: str | None = None

    with open(transcript_path, "w") as f:
        f.write(f"=== Meeting Transcript ===\n\n")

    for round_num in range(max_rounds):
        # Force first_speaker for round 0 if set and alive
        if round_num == 0 and first_speaker and first_speaker in participants:
            # Still send eagerness poll to other players so they get the meeting context
            others = {n: a for n, a in participants.items() if n != first_speaker}
            if others:
                await poll_eagerness(
                    others,
                    transcript_lines,
                    initialized,
                    meeting_context,
                    latest_speech=latest_speech,
                    stream_callback=stream_callback,
                )
            speaker = first_speaker
        else:
            # Poll all players for eagerness
            eagerness = await poll_eagerness(
                participants,
                transcript_lines,
                initialized,
                meeting_context,
                latest_speech=latest_speech,
                stream_callback=stream_callback,
            )

            # Prevent consecutive same speaker
            if last_speaker and last_speaker in eagerness and len(eagerness) > 1:
                eagerness[last_speaker] = float("-inf")

            # Eagerness-based consensus: if everyone's eagerness is negative,
            # end the meeting (players have nothing more to say)
            if transcript_lines and all(v <= 0 for v in eagerness.values()):
                logger.info(
                    "Eagerness consensus at round {}: all players' eagerness is nonpositive, ending meeting",
                    round_num + 1,
                )
                break

            # Exponentiate eagerness to get unnormalized probabilities
            names = list(eagerness.keys())
            weight_values = [
                math.exp(eagerness[n]) if eagerness[n] > 0 else 0 for n in names
            ]
            speaker = random.choices(names, weights=weight_values, k=1)[0]

        logger.info(f"Orchestrator picked {speaker}.")

        if log_callback:
            log_callback(speaker, f"[Round {round_num + 1}] Speaking...")

        # The speaker already has transcript context from the eagerness poll.
        # Just tell them it's their turn to speak.
        if speaker not in initialized:
            # First speaker in round 0 with forced speaker — needs full context
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
            prompt = "It's your turn to speak. Keep your response to 2-4 sentences."

        # Get agent response
        agent = participants[speaker]
        per_speaker_stream = (
            (lambda text: stream_callback(speaker, text)) if stream_callback else None
        )
        response = await _get_agent_response(
            speaker, agent, prompt, stream_callback=per_speaker_stream
        )
        response = response.strip()

        # Extract public speech from <speak> tags; no tag means silence
        speech = _extract_speak(response)
        if not speech:
            logger.info("Round {} - {}: (stayed silent)", round_num + 1, speaker)
            continue

        # Validate: check for third-person self-reference
        perspective_ok = await _validate_speech_perspective(
            speech, speaker, facilitator.llm
        )
        if not perspective_ok:
            logger.warning(
                "Round {} - {}: third-person speech detected, retrying",
                round_num + 1,
                speaker,
            )
            retry_prompt = (
                f"{prompt}\n\n"
                f"IMPORTANT: You ARE {speaker}. Speak in first person. "
                f"Do not refer to yourself by name or in the third person."
            )
            response = await _get_agent_response(
                speaker, agent, retry_prompt, stream_callback=per_speaker_stream
            )
            response = response.strip()
            speech = _extract_speak(response)
            if not speech:
                logger.info(
                    "Round {} - {}: (stayed silent on retry)", round_num + 1, speaker
                )
                continue

        line = f"**{speaker}**: {speech}"
        transcript_lines.append(line)
        latest_speech = line
        last_speaker = speaker

        # Append to transcript file
        with open(transcript_path, "a") as f:
            f.write(f"{line}\n\n")

        logger.info("Round {} - {}: {}", round_num + 1, speaker, speech)

        # Check for LLM-based consensus (optional, more expensive)
        if use_llm_consensus:
            result = await check_consensus(
                facilitator, participant_names, transcript_lines
            )
            if result.consensus_reached and result.consensus_target:
                logger.info(
                    "Early termination at round {}: LLM facilitator detected consensus on {}",
                    round_num + 1,
                    result.consensus_target,
                )
                break

    return transcript_lines


async def _mayor_tiebreak(
    mayor_name: str,
    mayor_agent: Agent,
    tied_options: list[str],
    stream_callback: Callable[[str, str], None] | None = None,
    max_retries: int = 2,
) -> str:
    """Ask the mayor to break a tie between two options, retrying on invalid choice."""
    per_mayor_stream = (
        (lambda text: stream_callback(mayor_name, text)) if stream_callback else None
    )
    options_str = ", ".join(f'"{opt}"' for opt in tied_options)
    prompt_text = mayor_tiebreak_prompt(tied_options)

    for attempt in range(max_retries + 1):
        parsed = await _get_agent_json(
            mayor_name,
            mayor_agent,
            prompt_text,
            stream_callback=per_mayor_stream,
            response_format=VOTE_SCHEMA,
        )
        if isinstance(parsed, dict) and "vote" in parsed:
            choice = parsed["vote"]
            if choice in tied_options:
                logger.info(
                    "Mayor {} broke the tie by choosing: {}", mayor_name, choice
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

    # Fallback: pick randomly from the tied options
    fallback = random.choice(tied_options)
    logger.warning(
        "Mayor tiebreak failed after retries, falling back to random choice: {}",
        fallback,
    )
    return fallback


async def run_vote(
    participants: dict[str, Agent],
    vote_type: str = "eliminate",
    valid_targets: list[str] | None = None,
    stream_callback: Callable[[str, str], None] | None = None,
    mayor: str | None = None,
) -> tuple[str | None, dict[str, dict]]:
    """Run a vote among participants.

    Args:
        participants: Mapping of agent_name -> Agent.
        vote_type: "eliminate" for day vote, "kill" for mafia night vote, "mayor" for mayor election.
        valid_targets: Explicit list of valid vote targets. For mafia kill votes,
            this should be the non-mafia alive players. If None, defaults to
            all participants except the voter.
        mayor: Name of the current mayor. For "eliminate" votes, the mayor's vote
            counts double.

    Returns:
        (winner_name or None, full_votes dict of name -> {"vote": ..., "reasoning": ...})
    """
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

        per_voter_stream = (
            (lambda text, n=name: stream_callback(n, text)) if stream_callback else None
        )
        parsed = await _get_agent_json(
            name,
            agent,
            prompt_text,
            stream_callback=per_voter_stream,
            response_format=VOTE_SCHEMA,
        )

        if isinstance(parsed, dict) and "vote" in parsed:
            vote_target = parsed["vote"]
            if vote_target != "abstain" and vote_target not in candidates:
                raise ValueError(
                    f"Invalid vote from {name}: '{vote_target}' not in candidates {candidates}"
                )
            return name, parsed
        else:
            raise RuntimeError(f"Failed to parse vote from {name} after retries")

    results = await asyncio.gather(
        *(_cast_vote(name, agent) for name, agent in participants.items())
    )
    for name, vote_data in results:
        votes[name] = vote_data

    # Tally votes (including abstain as a valid option for elimination votes)
    tally: dict[str, int] = {}
    for voter, vote_data in votes.items():
        target = vote_data["vote"]
        if vote_type == "eliminate":
            # Count all votes including abstain
            tally[target] = tally.get(target, 0) + 1
        else:
            if target != "abstain":
                tally[target] = tally.get(target, 0) + 1

    if not tally:
        return None, votes

    max_votes = max(tally.values())
    tied = [name for name, count in tally.items() if count == max_votes]

    # For elimination votes, require majority (>= half of all voters, abstain counts in denominator)
    if vote_type == "eliminate":
        total_voters = len(votes)
        majority_threshold = total_voters / 2
        if max_votes < majority_threshold:
            logger.info(
                "No elimination: top vote count {} does not reach majority threshold {:.1f}",
                max_votes,
                majority_threshold,
            )
            return None, votes

        # Exactly two options tied at half — mayor breaks the tie
        if (
            len(tied) == 2
            and max_votes == majority_threshold
            and mayor
            and mayor in participants
        ):
            logger.info("Tie between {} — mayor {} will break the tie", tied, mayor)
            tiebreak_winner = await _mayor_tiebreak(
                mayor, participants[mayor], tied, stream_callback
            )
            if tiebreak_winner == "abstain":
                return None, votes
            return tiebreak_winner, votes

        # More than 2-way tie or no option reaches majority
        if len(tied) > 1:
            logger.info("Vote tied between {} — no consensus reached", tied)
            return None, votes

        winner = tied[0]
        if winner == "abstain":
            return None, votes
        return winner, votes

    # Non-elimination votes: ties mean no consensus
    if len(tied) > 1:
        logger.info("Vote tied between {} — no consensus reached", tied)
        return None, votes

    winner = tied[0]
    return winner, votes
