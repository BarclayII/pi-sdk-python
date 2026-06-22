"""
Read tool for reading files.

This module provides the ReadTool which reads content from files.
"""

import os
from dataclasses import dataclass, field

import magic

from pi_sdk.tools.base import Tool, ToolParameter, ToolResult, ToolSchema
from pi_sdk.tools.path_utils import resolve_to_cwd
from pi_sdk.tools.truncate import truncate_head
from pi_sdk.types import ImageContent, TextContent, VideoContent


@dataclass
class ReadTool(Tool):
    """Tool for reading file contents."""

    name: str = "read"
    description: str = (
        "Read the contents of a file. "
        "Optionally specify offset and limit to read a portion of the file. "
        "Images and videos are read as media so they can be viewed directly."
    )
    schema: ToolSchema = field(
        default_factory=lambda: ToolSchema(
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file to read",
                ),
                ToolParameter(
                    name="offset",
                    type="integer",
                    description="Line number to start reading from (0-indexed)",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of lines to read",
                    required=False,
                ),
            ]
        )
    )
    cwd: str = "."

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, object],
    ) -> ToolResult:
        """Execute the read operation.

        Args:
            tool_call_id: ID of the tool call
            args: Tool arguments (path, offset?, limit?)

        Returns:
            ToolResult with file contents or error
        """
        path = args.get("path")
        offset = args.get("offset")
        limit = args.get("limit")

        if not isinstance(path, str):
            return ToolResult(
                content="Error: path must be a string",
                is_error=True,
            )

        if offset is not None and not isinstance(offset, int):
            return ToolResult(
                content="Error: offset must be an integer",
                is_error=True,
            )

        if limit is not None and not isinstance(limit, int):
            return ToolResult(
                content="Error: limit must be an integer",
                is_error=True,
            )

        # Default values
        offset = offset if offset is not None else 0
        limit = limit if limit is not None else 0  # 0 means all lines

        try:
            # Resolve path relative to cwd
            resolved_path = resolve_to_cwd(path, self.cwd)

            if not os.path.exists(resolved_path):
                return ToolResult(
                    content=f"Error: File not found: {path}",
                    is_error=True,
                )

            if not os.path.isfile(resolved_path):
                return ToolResult(
                    content=f"Error: Not a file: {path}",
                    is_error=True,
                )

            # Detect the file type from its contents (not the extension)
            mime_type = magic.from_file(resolved_path, mime=True)
            if mime_type.startswith("image/"):
                return self._read_image(resolved_path, path, mime_type)
            if mime_type.startswith("video/"):
                return self._read_video(resolved_path, path, mime_type)

            # Read text file
            with open(resolved_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Apply offset
            if offset > 0:
                if offset >= len(lines):
                    return ToolResult(
                        content=f"Error: offset {offset} is beyond file length ({len(lines)} lines)",
                        is_error=True,
                    )
                lines = lines[offset:]

            # Apply limit
            if limit > 0:
                lines = lines[:limit]

            content = "".join(lines)

            # Truncate if too large
            result = truncate_head(content)
            return ToolResult(content=result.content)

        except PermissionError:
            return ToolResult(
                content=f"Error: Permission denied reading {path}",
                is_error=True,
            )
        except UnicodeDecodeError:
            return ToolResult(
                content=f"Error: Could not decode {path} as UTF-8 text",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                content=f"Error reading {path}: {e!s}",
                is_error=True,
            )

    def _read_image(
        self, resolved_path: str, display_path: str, mime_type: str
    ) -> ToolResult:
        """Read an image file and return it as viewable media.

        Args:
            resolved_path: Resolved path to the image
            display_path: Original path for display
            mime_type: Detected MIME type (e.g. "image/png")

        Returns:
            ToolResult whose content carries the image as a content block
        """
        return ToolResult(
            content=[
                TextContent(text=f"Contents of {display_path} ({mime_type}):"),
                ImageContent.from_path(resolved_path, mime_type=mime_type),
            ]
        )

    def _read_video(
        self, resolved_path: str, display_path: str, mime_type: str
    ) -> ToolResult:
        """Read a video file and return it as viewable media.

        Args:
            resolved_path: Resolved path to the video
            display_path: Original path for display
            mime_type: Detected MIME type (e.g. "video/mp4")

        Returns:
            ToolResult whose content carries the video as a content block
        """
        return ToolResult(
            content=[
                TextContent(text=f"Contents of {display_path} ({mime_type}):"),
                VideoContent.from_path(resolved_path, mime_type=mime_type),
            ]
        )
