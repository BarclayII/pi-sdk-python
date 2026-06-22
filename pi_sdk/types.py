"""
Message protocol for pi-sdk-python.

This module defines the message types that are used throughout the SDK.
These match the LiteLLM/OpenAI message format.
"""

import base64
import mimetypes
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

    @classmethod
    def from_path(cls, path: str, mime_type: str | None = None) -> "ImageContent":
        """Build an ImageContent from a local file path.

        Reads the file, base64-encodes it, and auto-detects the MIME type
        from the file extension (falling back to ``image/png``).

        Args:
            path: Path to the image file.
            mime_type: Override the auto-detected MIME type.

        Returns:
            An ImageContent ready to include in a UserMessage.
        """
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        if mime_type is None:
            mime_type = mimetypes.guess_type(path)[0] or "image/png"
        return cls(data=data, mime_type=mime_type)


@dataclass
class VideoContent:
    """Video content in a message."""

    type: Literal["video"] = "video"
    data: str = ""  # base64 encoded video data
    mime_type: str = "video/mp4"

    @classmethod
    def from_path(cls, path: str, mime_type: str | None = None) -> "VideoContent":
        """Build a VideoContent from a local file path.

        Reads the file, base64-encodes it, and auto-detects the MIME type
        from the file extension (falling back to ``video/mp4``).

        Args:
            path: Path to the video file.
            mime_type: Override the auto-detected MIME type.

        Returns:
            A VideoContent ready to include in a UserMessage.
        """
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        if mime_type is None:
            mime_type = mimetypes.guess_type(path)[0] or "video/mp4"
        return cls(data=data, mime_type=mime_type)


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


ContentBlock = Union[
    TextContent, ImageContent, VideoContent, ThinkingContent, ToolCallContent
]


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
    content: Union[str, list[Union[TextContent, ImageContent, VideoContent]]] = ""


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
    """A tool result message.

    ``content`` may be a plain string, or a list of content blocks
    (e.g. TextContent + ImageContent / VideoContent) for tools that
    return media — these are passed to the model as a multimodal tool
    result.
    """

    role: Literal["tool"] = "tool"  # LiteLLM expects "tool" not "tool_result"
    tool_call_id: str = ""
    tool_name: str = ""
    content: Union[str, list[Union[TextContent, ImageContent, VideoContent]]] = ""
    is_error: bool = False


Message = Union[UserMessage, AssistantMessage, ToolResultMessage]


def summarize_content(
    content: Union[str, list[Any]],
) -> str:
    """Produce a short, log/display-friendly summary of message content.

    Replaces media blocks (image/video) with placeholders so large base64
    payloads never end up in logs, compaction text, or event displays.
    """
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content:
        if isinstance(block, TextContent):
            parts.append(block.text)
        else:
            parts.append(f"[{getattr(block, 'type', 'content')}]")
    return " ".join(parts)
