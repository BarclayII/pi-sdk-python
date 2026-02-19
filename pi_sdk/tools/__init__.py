"""
Tools module for pi-sdk-python.

This module provides factory functions for creating tool sets.
"""

from pi_sdk.tools.base import Tool, ToolParameter, ToolResult, ToolSchema
from pi_sdk.tools.bash import BashTool
from pi_sdk.tools.edit import EditTool
from pi_sdk.tools.read import ReadTool
from pi_sdk.tools.write import WriteTool


def create_coding_tools(cwd: str = ".") -> list[Tool]:
    """Create a set of tools for a coding agent.

    Args:
        cwd: Current working directory for path resolution

    Returns:
        List of tools: read, bash, edit, write
    """
    return [
        ReadTool(cwd=cwd),
        BashTool(cwd=cwd),
        EditTool(cwd=cwd),
        WriteTool(cwd=cwd),
    ]


__all__ = [
    "Tool",
    "ToolParameter",
    "ToolResult",
    "ToolSchema",
    "ReadTool",
    "BashTool",
    "EditTool",
    "WriteTool",
    "create_coding_tools",
]
