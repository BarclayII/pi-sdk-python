"""
Message protocol for pi-sdk-python.

This module defines the message types that are used throughout the SDK.
These match the LiteLLM/OpenAI message format.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Union


@dataclass
class TextContent:
    """Text content in a message."""

    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ImageContent:
    """Image content in a message."""

    type: Literal["image"] = "image"
    data: str = ""  # base64 encoded image data
    mime_type: str = "image/png"


@dataclass
class ThinkingContent:
    """Thinking content in a message (Claude-style reasoning)."""

    type: Literal["thinking"] = "thinking"
    thinking: str = ""


@dataclass
class ToolCallContent:
    """Tool call content in a message."""

    type: Literal["tool_call"] = "tool_call"
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


ContentBlock = Union[TextContent, ImageContent, ThinkingContent, ToolCallContent]


@dataclass
class Usage:
    """Token usage information."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class UserMessage:
    """A user message."""

    role: Literal["user"] = "user"
    content: Union[str, list[Union[TextContent, ImageContent]]] = ""


@dataclass
class AssistantMessage:
    """An assistant message."""

    role: Literal["assistant"] = "assistant"
    content: list[ContentBlock] = field(default_factory=list)
    model: str = ""
    stop_reason: str = ""
    usage: Usage = field(default_factory=Usage)


@dataclass
class ToolResultMessage:
    """A tool result message."""

    role: Literal["tool"] = "tool"  # LiteLLM expects "tool" not "tool_result"
    tool_call_id: str = ""
    tool_name: str = ""
    content: str = ""
    is_error: bool = False


Message = Union[UserMessage, AssistantMessage, ToolResultMessage]
