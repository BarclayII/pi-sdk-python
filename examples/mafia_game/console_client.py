"""Console client: renders game events to stdout with rich formatting.

Speech chunks for the day/mafia meeting stream live (sequential). Parallel
streams (eagerness polling, parallel voting, parallel diary writing) are
suppressed in favor of the completion events that follow them — this keeps
the single-pane console readable.
"""

from __future__ import annotations

import colorsys
import hashlib

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from event_bus import Client
from events import (
    ConsensusReached,
    Death,
    DiaryEntry,
    Eagerness,
    EagernessConsensus,
    Event,
    FacilitatorReasoning,
    GameResult,
    GameStart,
    MayorElected,
    MayorTiebreak,
    NightAction,
    NightActionStart,
    PhaseChange,
    PostgameReflection,
    RoleAssigned,
    RoundStart,
    SilentTurn,
    Speech,
    SpeakerChosen,
    SpeechChunk,
    SystemMessage,
    ToolCall,
    ToolResult,
    Vote,
    VoteResult,
)


_PALETTE = [
    "red", "green", "yellow", "magenta", "cyan",
    "medium_spring_green", "purple", "green_yellow",
    "deep_pink1", "orange1", "cyan1", "red1", "yellow1",
    "blue1", "magenta1", "green1",
]

# First-seen name claims its hashed slot; later collisions linear-probe to the
# next free slot. Assignments are cached so each name stays on one color for
# the whole process.
_color_assignments: dict[str, str] = {}
_used_indices: set[int] = set()


def _color_for(name: str) -> str:
    cached = _color_assignments.get(name)
    if cached is not None:
        return cached
    digest = hashlib.md5(name.encode()).digest()[:2]
    index = int.from_bytes(digest, "big") % len(_PALETTE)
    if len(_used_indices) < len(_PALETTE):
        while index in _used_indices:
            index = (index + 1) % len(_PALETTE)
    _used_indices.add(index)
    color = _PALETTE[index]
    _color_assignments[name] = color
    return color


def _channel_tag(channel: str) -> str | None:
    if channel == "public":
        return None
    if channel == "mafia":
        return "mafia-only"
    if channel.startswith("player:"):
        return f"private→{channel[len('player:') :]}"
    return channel


class ConsoleClient(Client):
    """Spectator console renderer. Sees every channel."""

    def __init__(self, console: Console | None = None) -> None:
        super().__init__()
        self.console = console or Console()
        self._streaming_speaker: str | None = None

    async def handle(self, event: Event) -> None:
        method = getattr(self, f"_on_{type(event).__name__}", None)
        if method is not None:
            method(event)
        else:
            self.console.print(f"[dim]{type(event).__name__}: {event}[/dim]")

    def _print_channel_prefix(self, channel: str) -> str:
        tag = _channel_tag(channel)
        return f"[dim italic]\\[{tag}][/dim italic] " if tag else ""

    def _finish_stream(self) -> None:
        if self._streaming_speaker is not None:
            self.console.print()  # newline after live stream
            self._streaming_speaker = None

    # --- handlers ---

    def _on_GameStart(self, e: GameStart) -> None:
        self._finish_stream()
        lines = [f"Players: {', '.join(e.players)}"]
        self.console.print(
            Panel(Text("\n".join(lines)), title="Mafia Game", style="bold")
        )

    def _on_RoleAssigned(self, e: RoleAssigned) -> None:
        self._finish_stream()
        prefix = self._print_channel_prefix(e.channel)
        color = _color_for(e.player)
        self.console.print(
            f"{prefix}[{color}]{e.player}[/{color}] assigned role: [bold]{e.role}[/bold]"
        )

    def _on_RoundStart(self, e: RoundStart) -> None:
        self._finish_stream()
        self.console.rule(f"[bold]Round {e.round_id}[/bold]")

    def _on_PhaseChange(self, e: PhaseChange) -> None:
        self._finish_stream()
        mayor = f" · mayor: {e.mayor}" if e.mayor else ""
        self.console.rule(
            f"[bold yellow]{e.phase.upper()}[/bold yellow] (round {e.round_id}){mayor}"
        )
        self.console.print(
            f"[dim]alive: {', '.join(e.alive)}"
            + (f" · dead: {', '.join(e.dead)}" if e.dead else "")
            + "[/dim]"
        )

    def _on_SystemMessage(self, e: SystemMessage) -> None:
        self._finish_stream()
        prefix = self._print_channel_prefix(e.channel)
        self.console.print(f"{prefix}[italic]{e.text}[/italic]")

    def _on_SpeechChunk(self, e: SpeechChunk) -> None:
        # Only stream live for serial speech; parallel contexts would interleave.
        if e.context != "speech":
            return
        if self._streaming_speaker != e.speaker:
            self._finish_stream()
            prefix = self._print_channel_prefix(e.channel)
            color = _color_for(e.speaker)
            self.console.print(
                f"{prefix}[{color}]{e.speaker}[/{color}] [dim]streaming…[/dim] ",
                end="",
            )
            self._streaming_speaker = e.speaker
        self.console.print(e.delta, end="", soft_wrap=True, highlight=False)

    def _on_ToolCall(self, e: ToolCall) -> None:
        self._finish_stream()
        self.console.print(
            f"[dim]   ↳ {e.speaker} tool: {e.name}({e.arguments_summary})[/dim]"
        )

    def _on_ToolResult(self, e: ToolResult) -> None:
        self._finish_stream()
        self.console.print(f"[dim]   ↲ {e.result_preview}[/dim]")

    def _on_Eagerness(self, e: Eagerness) -> None:
        self._finish_stream()
        color = _color_for(e.name)
        self.console.print(
            f"[dim]eagerness · [/dim][{color}]{e.name}[/{color}] "
            f"[dim]{e.rating:.1f}[/dim] [dim italic]({e.reason})[/dim italic]"
        )

    def _on_SpeakerChosen(self, e: SpeakerChosen) -> None:
        self._finish_stream()
        color = _color_for(e.speaker)
        self.console.print(
            f"[dim]round {e.round_num} → picked[/dim] [{color}]{e.speaker}[/{color}]"
        )

    def _on_Speech(self, e: Speech) -> None:
        self._finish_stream()
        prefix = self._print_channel_prefix(e.channel)
        color = _color_for(e.speaker)
        self.console.print(
            f"{prefix}[{color}][bold]{e.speaker}[/bold][/{color}]: {e.text}"
        )

    def _on_SilentTurn(self, e: SilentTurn) -> None:
        self._finish_stream()
        color = _color_for(e.speaker)
        self.console.print(
            f"[dim]round {e.round_num} · [/dim][{color}]{e.speaker}[/{color}] "
            "[dim](stayed silent)[/dim]"
        )

    def _on_EagernessConsensus(self, e: EagernessConsensus) -> None:
        self._finish_stream()
        self.console.print(
            f"[dim italic]eagerness consensus at round {e.round_num} "
            "— meeting ends[/dim italic]"
        )

    def _on_FacilitatorReasoning(self, e: FacilitatorReasoning) -> None:
        self._finish_stream()
        self.console.print(f"[dim italic]facilitator: {e.text}[/dim italic]")

    def _on_ConsensusReached(self, e: ConsensusReached) -> None:
        self._finish_stream()
        self.console.print(
            f"[italic]consensus reached at round {e.round_num} on "
            f"[bold]{e.target}[/bold][/italic]"
        )

    def _on_Vote(self, e: Vote) -> None:
        self._finish_stream()
        prefix = self._print_channel_prefix(e.channel)
        voter_color = _color_for(e.voter)
        target_color = _color_for(e.target) if e.target != "abstain" else "dim"
        reasoning = f" [dim italic]({e.reasoning})[/dim italic]" if e.reasoning else ""
        self.console.print(
            f"{prefix}[dim]{e.vote_type}-vote ·[/dim] "
            f"[{voter_color}]{e.voter}[/{voter_color}] → "
            f"[{target_color}]{e.target}[/{target_color}]{reasoning}"
        )

    def _on_VoteResult(self, e: VoteResult) -> None:
        self._finish_stream()
        if e.winner:
            color = _color_for(e.winner)
            self.console.print(
                f"[bold]{e.vote_type}-vote result:[/bold] "
                f"[{color}]{e.winner}[/{color}] [dim]({e.reason})[/dim]"
            )
        else:
            tied = f" tied: {', '.join(e.tied)}" if e.tied else ""
            self.console.print(
                f"[bold]{e.vote_type}-vote result:[/bold] "
                f"[yellow]no winner[/yellow] [dim]({e.reason}){tied}[/dim]"
            )

    def _on_MayorTiebreak(self, e: MayorTiebreak) -> None:
        self._finish_stream()
        mayor_color = _color_for(e.mayor)
        chosen_color = _color_for(e.chosen)
        self.console.print(
            f"[{mayor_color}]{e.mayor}[/{mayor_color}] (mayor) broke tie between "
            f"{', '.join(e.tied_between)} → [{chosen_color}]{e.chosen}[/{chosen_color}]"
        )

    def _on_Death(self, e: Death) -> None:
        self._finish_stream()
        color = _color_for(e.player)
        self.console.print(
            f"[red bold]✗ DEATH[/red bold] [{color}]{e.player}[/{color}] "
            f"[dim]({e.cause}) · role: {e.role}[/dim]"
        )

    def _on_MayorElected(self, e: MayorElected) -> None:
        self._finish_stream()
        color = _color_for(e.name)
        self.console.print(
            f"[yellow bold]★ MAYOR[/yellow bold] [{color}]{e.name}[/{color}] "
            f"[dim]({e.via})[/dim]"
        )

    def _on_NightActionStart(self, e: NightActionStart) -> None:
        self._finish_stream()
        prefix = self._print_channel_prefix(e.channel)
        actor_color = _color_for(e.actor)
        self.console.print(
            f"{prefix}[bold]▸ {e.role.upper()} TURN[/bold] "
            f"[{actor_color}]({e.actor})[/{actor_color}] [dim]deciding…[/dim]"
        )

    def _on_NightAction(self, e: NightAction) -> None:
        self._finish_stream()
        prefix = self._print_channel_prefix(e.channel)
        actor_color = _color_for(e.actor)
        target = (
            f"[{_color_for(e.target)}]{e.target}[/{_color_for(e.target)}]"
            if e.target
            else "[dim]—[/dim]"
        )
        reasoning = (
            f"\n    [dim italic]↳ {e.reasoning}[/dim italic]" if e.reasoning else ""
        )
        self.console.print(
            f"{prefix}[{actor_color}]{e.actor}[/{actor_color}] "
            f"[dim]({e.role})[/dim] {e.action} → {target} "
            f"[bold]{e.outcome}[/bold]{reasoning}"
        )

    def _on_DiaryEntry(self, e: DiaryEntry) -> None:
        self._finish_stream()
        prefix = self._print_channel_prefix(e.channel)
        color = _color_for(e.name)
        preview = e.text.strip().replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "…"
        self.console.print(
            f"{prefix}[dim]diary (r{e.round_id}) ·[/dim] "
            f"[{color}]{e.name}[/{color}] [dim]{preview}[/dim]"
        )

    def _on_PostgameReflection(self, e: PostgameReflection) -> None:
        self._finish_stream()
        prefix = self._print_channel_prefix(e.channel)
        color = _color_for(e.name)
        preview = e.text.strip().replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "…"
        self.console.print(
            f"{prefix}[dim]postgame ·[/dim] [{color}]{e.name}[/{color}] "
            f"[dim]{preview}[/dim]"
        )

    def _on_GameResult(self, e: GameResult) -> None:
        self._finish_stream()
        lines = [f"Winner: {e.winner}", "Final roles:"]
        for name, role in sorted(e.final_roles.items()):
            status = "alive" if name in e.alive else "dead"
            lines.append(f"  {name}: {role} ({status})")
        self.console.print(
            Panel(Text("\n".join(lines)), title="Game Over", style="bold green")
        )
