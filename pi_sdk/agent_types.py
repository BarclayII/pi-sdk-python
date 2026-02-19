"""
Agent event types for pi-sdk-python.

This module defines the event types emitted by the agent loop.
"""

from dataclasses import dataclass

from pi_sdk.types import Message


@dataclass
class AgentStart:
    """Event emitted when the agent starts."""


@dataclass
class AgentEnd:
    """Event emitted when the agent ends."""

    messages: list[Message]


@dataclass
class TurnStart:
    """Event emitted at the start of each turn."""

    turn: int


@dataclass
class TurnEnd:
    """Event emitted at the end of each turn."""

    turn: int


@dataclass
class TextDelta:
    """Event emitted for each text delta from the LLM."""

    delta: str


@dataclass
class ToolExecStart:
    """Event emitted when a tool execution starts."""

    tool_call_id: str
    name: str
    arguments: dict


@dataclass
class ToolExecEnd:
    """Event emitted when a tool execution ends."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool


@dataclass
class ToolResultData:
    """Data for a tool result."""

    tool_call_id: str
    name: str
    content: str
    is_error: bool


# Union type for all agent events
AgentEvent = (
    AgentStart
    | AgentEnd
    | TurnStart
    | TurnEnd
    | TextDelta
    | ToolExecStart
    | ToolExecEnd
)
