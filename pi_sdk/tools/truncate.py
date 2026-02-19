"""
Truncation utilities for tool outputs.

This module provides functions to truncate content that is too large
to be sent to the LLM.
"""

from dataclasses import dataclass
import sys


@dataclass
class TruncationResult:
    """Result of a truncation operation."""

    content: str
    was_truncated: bool
    original_size: int
    truncated_size: int
    line_count: int


def format_size(byte_count: int) -> str:
    """Format a byte count as a human-readable string.

    Args:
        byte_count: Number of bytes

    Returns:
        Formatted string like "1.5KB", "2.3MB"
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if byte_count < 1024.0:
            # Use integer format for whole numbers >= 10
            if byte_count < 10:
                return f"{byte_count:.1f}{unit}"
            return f"{int(byte_count)}{unit}"
        byte_count /= 1024.0
    return f"{byte_count:.1f}TB"


def truncate_head(
    content: str,
    max_lines: int = 2000,
    max_bytes: int = 50 * 1024,
) -> TruncationResult:
    """Truncate content from the beginning (for read tool).

    Args:
        content: The content to truncate
        max_lines: Maximum number of lines to keep
        max_bytes: Maximum number of bytes to keep

    Returns:
        TruncationResult with truncated content and metadata
    """
    lines = content.splitlines(keepends=True)
    original_size = len(content.encode("utf-8"))

    # Build result line by line, checking both constraints
    result_lines: list[str] = []
    current_bytes = 0
    was_truncated = False

    for i, line in enumerate(lines):
        line_bytes = len(line.encode("utf-8"))
        new_bytes = current_bytes + line_bytes

        if i >= max_lines or new_bytes > max_bytes:
            was_truncated = True
            break

        result_lines.append(line)
        current_bytes = new_bytes

    truncated_content = "".join(result_lines)

    if was_truncated:
        truncated_size = len(truncated_content.encode("utf-8"))
        message = (
            f"\n\n... (content truncated: {format_size(original_size)} original, "
            f"{len(lines)} lines, showing first {len(result_lines)} lines / "
            f"{format_size(truncated_size)})"
        )
        truncated_content += message

    return TruncationResult(
        content=truncated_content,
        was_truncated=was_truncated,
        original_size=original_size,
        truncated_size=len(truncated_content.encode("utf-8")),
        line_count=len(result_lines),
    )


def truncate_tail(
    content: str,
    max_lines: int = 2000,
    max_bytes: int = 50 * 1024,
) -> TruncationResult:
    """Truncate content from the end (for bash tool).

    Args:
        content: The content to truncate
        max_lines: Maximum number of lines to keep
        max_bytes: Maximum number of bytes to keep

    Returns:
        TruncationResult with truncated content and metadata
    """
    lines = content.splitlines(keepends=True)
    original_size = len(content.encode("utf-8"))

    # Build result from the end, checking both constraints
    result_lines: list[str] = []
    current_bytes = 0
    was_truncated = False

    for line in reversed(lines):
        line_bytes = len(line.encode("utf-8"))
        new_bytes = current_bytes + line_bytes

        if len(result_lines) >= max_lines or new_bytes > max_bytes:
            was_truncated = True
            break

        result_lines.append(line)
        current_bytes = new_bytes

    # Reverse back to get correct order
    result_lines.reverse()

    truncated_content = "".join(result_lines)

    if was_truncated:
        truncated_size = len(truncated_content.encode("utf-8"))
        message = (
            f"... (content truncated: {format_size(original_size)} original, "
            f"{len(lines)} lines, showing last {len(result_lines)} lines / "
            f"{format_size(truncated_size)}) ...\n\n"
        )
        truncated_content = message + truncated_content

    return TruncationResult(
        content=truncated_content,
        was_truncated=was_truncated,
        original_size=original_size,
        truncated_size=len(truncated_content.encode("utf-8")),
        line_count=len(result_lines),
    )
