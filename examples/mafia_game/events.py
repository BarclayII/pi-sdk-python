"""Structured events emitted by the game server for client rendering.

Events are the sole narration channel: every user-visible thing the game does
(speeches, votes, deaths, private role results, etc.) is emitted as an event.
Clients subscribe and choose how to render.

The ``channel`` field describes visibility semantics so future player-facing
clients can filter correctly. The console (spectator) client sees all channels.

    - ``"public"`` — visible to every player
    - ``"mafia"`` — visible only to mafia members
    - ``"player:<name>"`` — visible only to that player
"""

from __future__ import annotations

from dataclasses import dataclass, field


def player_channel(name: str) -> str:
    return f"player:{name}"


@dataclass(frozen=True, kw_only=True)
class Event:
    channel: str = "public"


@dataclass(frozen=True, kw_only=True)
class GameStart(Event):
    players: list[str]
    roles: dict[str, str]


@dataclass(frozen=True, kw_only=True)
class RoleAssigned(Event):
    """Private notification to each player of their own role."""

    player: str
    role: str


@dataclass(frozen=True, kw_only=True)
class RoundStart(Event):
    round_id: int


@dataclass(frozen=True, kw_only=True)
class PhaseChange(Event):
    phase: str  # "mayor_election" | "night" | "day" | "diary" | "postgame"
    round_id: int
    alive: list[str]
    dead: list[str]
    mayor: str | None


@dataclass(frozen=True, kw_only=True)
class SystemMessage(Event):
    """Free-form narration for things without a dedicated event type."""

    text: str


@dataclass(frozen=True, kw_only=True)
class SpeechChunk(Event):
    """Streaming LLM text delta while an agent is generating output."""

    speaker: str
    delta: str
    context: (
        str  # "speech" | "eagerness" | "vote" | "diary" | "night_action" | "postgame"
    )


@dataclass(frozen=True, kw_only=True)
class ToolCall(Event):
    speaker: str
    name: str
    arguments_summary: str


@dataclass(frozen=True, kw_only=True)
class ToolResult(Event):
    speaker: str
    result_preview: str


@dataclass(frozen=True, kw_only=True)
class Eagerness(Event):
    name: str
    rating: float
    reason: str


@dataclass(frozen=True, kw_only=True)
class SpeakerChosen(Event):
    speaker: str
    round_num: int


@dataclass(frozen=True, kw_only=True)
class Speech(Event):
    """A completed public (or mafia) utterance, after <speak> extraction."""

    speaker: str
    round_num: int
    text: str


@dataclass(frozen=True, kw_only=True)
class SilentTurn(Event):
    speaker: str
    round_num: int


@dataclass(frozen=True, kw_only=True)
class EagernessConsensus(Event):
    round_num: int


@dataclass(frozen=True, kw_only=True)
class FacilitatorReasoning(Event):
    text: str


@dataclass(frozen=True, kw_only=True)
class ConsensusReached(Event):
    round_num: int
    target: str


@dataclass(frozen=True, kw_only=True)
class Vote(Event):
    voter: str
    target: str
    reasoning: str
    vote_type: str  # "mayor" | "eliminate" | "kill"


@dataclass(frozen=True, kw_only=True)
class VoteResult(Event):
    vote_type: str
    winner: str | None
    tied: list[str] = field(default_factory=list)
    reason: str = ""  # "majority" | "no_majority" | "tie" | "tiebreak" | "random"


@dataclass(frozen=True, kw_only=True)
class MayorTiebreak(Event):
    mayor: str
    chosen: str
    tied_between: list[str]


@dataclass(frozen=True, kw_only=True)
class Death(Event):
    player: str
    cause: str  # "mafia_kill" | "poison" | "voted_out"
    role: str


@dataclass(frozen=True, kw_only=True)
class MayorElected(Event):
    name: str
    via: str  # "vote" | "tiebreak_random" | "succession" | "succession_fallback"


@dataclass(frozen=True, kw_only=True)
class NightActionStart(Event):
    """A role is beginning their night decision. Marks a sub-phase boundary.

    Channel is ``player:<actor>`` (solo roles) or ``"mafia"`` (team meeting).
    """

    role: str  # "detective" | "guardian" | "doctor" | "mafia"
    actor: str


@dataclass(frozen=True, kw_only=True)
class NightAction(Event):
    """Outcome of a night role's private action.

    Channel is ``player:<actor>`` so only the actor (and spectator) sees it.
    """

    role: str  # "detective" | "guardian" | "doctor" | "mafia"
    actor: str
    action: str  # "investigate" | "protect" | "save" | "poison" | "kill"
    target: str | None
    outcome: str  # "mafia" | "not_mafia" | "protected" | "saved" | "poisoned"
    # | "failed" | "no_kill" | "targeted"
    reasoning: str = ""


@dataclass(frozen=True, kw_only=True)
class DiaryEntry(Event):
    name: str
    round_id: int
    text: str


@dataclass(frozen=True, kw_only=True)
class PostgameReflection(Event):
    name: str
    text: str


@dataclass(frozen=True, kw_only=True)
class GameResult(Event):
    winner: str
    final_roles: dict[str, str]
    alive: list[str]
