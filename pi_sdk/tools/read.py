"""
Read tool for reading files.

This module provides the ReadTool which reads content from files.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from pi_sdk.tools.base import Tool, ToolParameter, ToolResult, ToolSchema
from pi_sdk.tools.path_utils import resolve_to_cwd
from pi_sdk.tools.truncate import truncate_head


@dataclass
class ReadTool(Tool):
    """Tool for reading file contents."""

    name: str = "read"
    description: str = (
        "Read the contents of a file. "
        "Optionally specify offset and limit to read a portion of the file. "
        "Images are returned as base64 encoded data URLs."
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

    # Image file extensions that should be returned as base64
    IMAGE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".svg",
    }

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

            # Check if it's an image file
            ext = Path(resolved_path).suffix.lower()
            if ext in self.IMAGE_EXTENSIONS:
                return self._read_image(resolved_path, path)

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

    def _read_image(self, resolved_path: str, display_path: str) -> ToolResult:
        """Read an image file and return as base64 data URL.

        Args:
            resolved_path: Resolved path to the image
            display_path: Original path for display

        Returns:
            ToolResult with base64 encoded image
        """
        import base64

        # Get mime type from extension
        ext = Path(resolved_path).suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".svg": "image/svg+xml",
        }
        mime_type = mime_types.get(ext, "image/png")

        # Read and encode image
        with open(resolved_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("ascii")

        data_url = f"data:{mime_type};base64,{image_data}"
        return ToolResult(content=data_url)
