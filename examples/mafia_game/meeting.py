"""Meeting room with facilitator-driven speaker selection and voting."""

import asyncio
import json
import logging
import math
import random
import re
from dataclasses import dataclass, field
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
    facilitator_prompt,
    mafia_kill_vote_prompt,
    mayor_vote_prompt,
    vote_prompt,
)

logger = logging.getLogger(__name__)


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

FACILITATOR_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "facilitator_weights",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "weights": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                },
                "consensus_reached": {"type": "boolean"},
                "consensus_target": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": [
                "weights",
                "consensus_reached",
                "consensus_target",
                "reasoning",
            ],
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
                "LLM call failed (attempt %d/%d): %s", attempt + 1, retries + 1, e
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
                "Agent %s failed (attempt %d/%d): %s",
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
            print(response)
            return json.loads(_strip_markdown_json(response))
        except (json.JSONDecodeError, TypeError):
            if attempt == parse_retries:
                logger.warning(
                    "Failed to parse JSON from %s after %d retries: %s",
                    agent_name,
                    parse_retries,
                    response[:200],
                )
                return None
            logger.warning(
                "JSON parse failed for %s (attempt %d), asking to retry",
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
class FacilitatorResult:
    """Result from the facilitator including speaker weights and consensus detection."""

    weights: dict[str, float]
    consensus_reached: bool = False
    consensus_target: str = ""


async def get_facilitator_weights(
    facilitator: Agent,
    participants: list[str],
    transcript_lines: list[str],
) -> FacilitatorResult:
    """Ask the facilitator agent for speaker weights and consensus detection.

    Returns a FacilitatorResult with weights and consensus info. Falls back to
    uniform weights with no consensus if the response can't be parsed.
    """
    default = FacilitatorResult(weights={p: 1.0 for p in participants})

    # Start with fresh context each time — no accumulated history.
    facilitator.reset()
    recent = (
        "\n".join(transcript_lines[-20:]) if transcript_lines else "(no transcript yet)"
    )
    prompt = facilitator_prompt(participants, recent)
    parsed = await _get_agent_json(
        "facilitator",
        facilitator,
        prompt,
        response_format=FACILITATOR_SCHEMA,
    )

    if not parsed:
        return default

    weights = parsed.get("weights", {})
    valid = all(
        p in weights and isinstance(weights[p], (int, float)) for p in participants
    )
    if valid:
        reasoning = parsed.get("reasoning", "")
        if reasoning:
            logger.info("Facilitator reasoning: %s", reasoning)
        return FacilitatorResult(
            weights={p: float(weights[p]) for p in participants},
            consensus_reached=bool(parsed.get("consensus_reached", False)),
            consensus_target=str(parsed.get("consensus_target", "")),
        )

    logger.warning("Invalid facilitator weights, using uniform")
    return default


async def run_meeting(
    participants: dict[str, Agent],
    facilitator: Agent,
    transcript_path: str,
    max_rounds: int,
    meeting_context: str,
    log_callback: Callable[[str, str], None] | None = None,
    stream_callback: Callable[[str, str], None] | None = None,
    first_speaker: str | None = None,
) -> list[str]:
    """Run a meeting with facilitator-driven speaker selection.

    Args:
        participants: Mapping of agent_name -> Agent.
        facilitator: Agent used for speaker selection and speech validation.
        transcript_path: Path to write the transcript file.
        max_rounds: Number of speaking rounds.
        meeting_context: Context string prepended to each agent's prompt.
        log_callback: Optional (agent_name, message) callback for tmux logging.
        stream_callback: Optional (agent_name, text_chunk) callback for real-time
            streaming of LLM output and tool events to tmux windows.
        first_speaker: Optional player name to force as speaker for round 0.

    Returns:
        List of transcript lines.
    """
    participant_names = list(participants.keys())
    transcript_lines: list[str] = []
    last_speaker: str | None = None
    last_seen_index: dict[str, int] = {name: 0 for name in participant_names}
    has_spoken: set[str] = set()

    with open(transcript_path, "w") as f:
        f.write(f"=== Meeting Transcript ===\n\n")

    for round_num in range(max_rounds):
        # Force first_speaker for round 0 if set and alive
        if round_num == 0 and first_speaker and first_speaker in participants:
            speaker = first_speaker
        else:
            # Get facilitator weights and consensus signal
            result = await get_facilitator_weights(
                facilitator, participant_names, transcript_lines
            )

            # Check for unanimous consensus — end meeting early
            if result.consensus_reached and result.consensus_target:
                logger.info(
                    "Early termination at round %d: unanimous consensus on %s",
                    round_num + 1,
                    result.consensus_target,
                )
                break

            # Prevent consecutive same speaker
            if (
                last_speaker
                and last_speaker in result.weights
                and len(result.weights) > 1
            ):
                result.weights[last_speaker] = float("-inf")

            # Exponentiate raw weights to get unnormalized probabilities
            names = list(result.weights.keys())
            weight_values = [math.exp(result.weights[n]) for n in names]
            speaker = random.choices(names, weights=weight_values, k=1)[0]
        logger.info(f"Orchestrator picked {speaker}.")

        # Build prompt with delta transcript
        if speaker not in has_spoken:
            # First turn: full context + all lines so far
            transcript_so_far = (
                "\n".join(transcript_lines)
                if transcript_lines
                else "(meeting just started)"
            )
            prompt = f"""{meeting_context}

Meeting transcript so far:
{transcript_so_far}

It's your turn to speak. Keep your response to 2-4 sentences."""
        else:
            # Subsequent turns: delta only
            logger.info(
                f"Last message spoken: {transcript_lines[last_seen_index[speaker]]}"
            )
            assert transcript_lines[last_seen_index[speaker]].startswith(
                f"**{speaker}**"
            )
            new_lines = transcript_lines[last_seen_index[speaker] + 1 :]
            if new_lines:
                delta = "\n".join(new_lines)
                prompt = f"""New messages since you last spoke:
{delta}

It's your turn to speak. Keep your response to 2-4 sentences."""
            else:
                prompt = "No new messages. It's your turn to speak. Keep your response to 2-4 sentences."

        if log_callback:
            log_callback(speaker, f"[Round {round_num + 1}] Speaking...")

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
            logger.info("Round %d - %s: (stayed silent)", round_num + 1, speaker)
            continue

        # Validate: check for third-person self-reference
        perspective_ok = await _validate_speech_perspective(
            speech, speaker, facilitator.llm
        )
        if not perspective_ok:
            logger.warning(
                "Round %d - %s: third-person speech detected, retrying",
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
                    "Round %d - %s: (stayed silent on retry)", round_num + 1, speaker
                )
                continue

        line = f"**{speaker}**: {speech}"
        transcript_lines.append(line)
        last_seen_index[speaker] = len(transcript_lines) - 1
        has_spoken.add(speaker)
        last_speaker = speaker

        # Append to transcript file
        with open(transcript_path, "a") as f:
            f.write(f"{line}\n\n")

        logger.info("Round %d - %s: %s", round_num + 1, speaker, speech)

    return transcript_lines


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

    for name, agent in participants.items():
        if vote_type == "kill":
            # Mafia vote: use explicit valid_targets (all alive players)
            candidates = valid_targets or [p for p in participant_names if p != name]
            prompt_text = mafia_kill_vote_prompt(candidates)
        elif vote_type == "mayor":
            # Mayor election: can vote for anyone including self
            candidates = valid_targets or participant_names
            prompt_text = mayor_vote_prompt(participant_names)
        else:
            candidates = [p for p in participant_names if p != name]
            prompt_text = vote_prompt(participant_names, name, mayor=mayor)

        # Agents are stateful and already saw the meeting via delta delivery,
        # so we only send the vote prompt (no redundant transcript).
        full_prompt = prompt_text

        try:
            per_voter_stream = (
                (lambda text, n=name: stream_callback(n, text))
                if stream_callback
                else None
            )
            parsed = await _get_agent_json(
                name,
                agent,
                full_prompt,
                stream_callback=per_voter_stream,
                response_format=VOTE_SCHEMA,
            )
        except Exception as e:
            logger.error("Error getting vote from %s: %s", name, e)
            parsed = None

        if parsed and "vote" in parsed:
            # Validate vote target
            vote_target = parsed["vote"]
            if vote_target != "abstain" and vote_target not in candidates:
                raise ValueError(
                    f"Invalid vote from {name}: '{vote_target}' not in candidates {candidates}"
                )
            votes[name] = parsed
        else:
            raise RuntimeError(f"Failed to parse vote from {name} after retries")

    # Tally votes
    tally: dict[str, int] = {}
    for voter, vote_data in votes.items():
        target = vote_data["vote"]
        if target != "abstain":
            weight = 2 if (vote_type == "eliminate" and voter == mayor) else 1
            tally[target] = tally.get(target, 0) + weight

    if not tally:
        return None, votes

    max_votes = max(tally.values())
    tied = [name for name, count in tally.items() if count == max_votes]

    # Ties mean no consensus — no action taken
    if len(tied) > 1:
        logger.info("Vote tied between %s — no consensus reached", tied)
        return None, votes

    winner = tied[0]

    # For elimination votes, require strict majority (> half of total vote weight)
    if vote_type == "eliminate":
        total_weight = len(participants) + (1 if mayor and mayor in participants else 0)
        majority_threshold = total_weight / 2
        if max_votes <= majority_threshold:
            logger.info(
                "No elimination: top vote count %d does not exceed majority threshold %.1f",
                max_votes,
                majority_threshold,
            )
            return None, votes

    return winner, votes
