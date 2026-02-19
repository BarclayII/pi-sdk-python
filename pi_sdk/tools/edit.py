"""
Edit tool for modifying files with fuzzy matching.

This module provides the EditTool which performs fuzzy-matching text replacement.
"""

import os
from dataclasses import dataclass, field

from pi_sdk.tools.base import Tool, ToolParameter, ToolResult, ToolSchema
from pi_sdk.tools.edit_diff import (
    FuzzyMatchResult,
    detect_line_ending,
    fuzzy_find_text,
    normalize_to_lf,
    restore_line_endings,
    strip_bom,
)
from pi_sdk.tools.path_utils import resolve_to_cwd


@dataclass
class EditTool(Tool):
    """Tool for editing files with fuzzy matching."""

    name: str = "edit"
    description: str = (
        "Make an edit to a file. "
        "Uses fuzzy matching to find the old_text and replace it with new_text. "
        "The old_text must match exactly (allowing for whitespace differences). "
        "You MUST read the file first before using edit."
    )
    schema: ToolSchema = field(
        default_factory=lambda: ToolSchema(
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description="Path to the file to edit",
                ),
                ToolParameter(
                    name="old_text",
                    type="string",
                    description="Text to search for and replace",
                ),
                ToolParameter(
                    name="new_text",
                    type="string",
                    description="New text to replace with",
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
        """Execute the edit operation.

        Args:
            tool_call_id: ID of the tool call
            args: Tool arguments (path, old_text, new_text)

        Returns:
            ToolResult with success message or error
        """
        path = args.get("path")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")

        if not isinstance(path, str):
            return ToolResult(
                content="Error: path must be a string",
                is_error=True,
            )

        if not isinstance(old_text, str):
            return ToolResult(
                content="Error: old_text must be a string",
                is_error=True,
            )

        if not isinstance(new_text, str):
            return ToolResult(
                content="Error: new_text must be a string",
                is_error=True,
            )

        if not old_text:
            return ToolResult(
                content="Error: old_text cannot be empty",
                is_error=True,
            )

        try:
            # Resolve path relative to cwd
            resolved_path = resolve_to_cwd(path, self.cwd)

            if not os.path.exists(resolved_path):
                return ToolResult(
                    content=f"Error: File not found: {path}",
                    is_error=True,
                )

            # Read the file
            with open(resolved_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Store BOM if present and remove it
            bom, content = strip_bom(content)

            # Detect and normalize line endings
            line_ending = detect_line_ending(content)
            normalized_content = normalize_to_lf(content)

            # Also normalize old_text for matching
            normalized_old_text = normalize_to_lf(old_text)

            # Find the text to replace
            match_result: FuzzyMatchResult = fuzzy_find_text(
                normalized_content, normalized_old_text
            )

            if not match_result.found:
                return ToolResult(
                    content=f"Error: Could not find the specified old_text in {path}. "
                    f"Make sure you have the exact text (allowing for whitespace differences).",
                    is_error=True,
                )

            # Check for uniqueness if fuzzy match
            if match_result.is_fuzzy:
                # Count occurrences to warn if not unique
                count = normalized_content.count(normalized_old_text)
                if count > 1:
                    return ToolResult(
                        content=f"Error: Found {count} occurrences of old_text. "
                        f"Please provide more unique text to replace.",
                        is_error=True,
                    )

            # Perform the replacement
            new_content = (
                normalized_content[: match_result.index]
                + new_text
                + normalized_content[match_result.index + len(match_result.match) :]
            )

            # Restore line endings and BOM
            new_content = restore_line_endings(new_content, line_ending)
            new_content = bom + new_content

            # Write the file back
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(
                content=f"Successfully edited {path} - replaced text at position {match_result.index}"
            )

        except PermissionError:
            return ToolResult(
                content=f"Error: Permission denied writing to {path}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                content=f"Error editing {path}: {e!s}",
                is_error=True,
            )
