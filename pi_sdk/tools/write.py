"""
Write tool for creating/updating files.

This module provides the WriteTool which writes content to files.
"""

import os
from dataclasses import dataclass, field

from pi_sdk.tools.base import Tool, ToolParameter, ToolResult, ToolSchema
from pi_sdk.tools.path_utils import resolve_to_cwd


@dataclass
class WriteTool(Tool):
    """Tool for writing content to files."""

    name: str = "write"
    description: str = (
        "Write content to a file. "
        "If the file exists, it will be overwritten. "
        "Parent directories will be created if they don't exist."
    )
    schema: ToolSchema = field(
        default_factory=lambda: ToolSchema(
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file to write",
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Content to write to the file",
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
        """Execute the write operation.

        Args:
            tool_call_id: ID of the tool call
            args: Tool arguments (path, content)

        Returns:
            ToolResult with success message or error
        """
        path = args.get("path")
        content = args.get("content", "")

        if not isinstance(path, str):
            return ToolResult(
                content="Error: path must be a string",
                is_error=True,
            )

        if not isinstance(content, str):
            return ToolResult(
                content="Error: content must be a string",
                is_error=True,
            )

        try:
            # Resolve path relative to cwd
            resolved_path = resolve_to_cwd(path, self.cwd)

            # Create parent directories if they don't exist
            parent_dir = os.path.dirname(resolved_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            # Write the file
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                content=f"Successfully wrote {len(content)} bytes to {path}"
            )

        except PermissionError:
            return ToolResult(
                content=f"Error: Permission denied writing to {path}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                content=f"Error writing to {path}: {e!s}",
                is_error=True,
            )
