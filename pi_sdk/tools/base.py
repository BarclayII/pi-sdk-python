"""
Tool protocol and base classes for pi-sdk-python.

This module defines the Tool protocol and related classes used throughout the SDK.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass
class ToolParameter:
    """A parameter definition for a tool."""

    name: str
    type: str  # "string", "integer", "number", "boolean"
    description: str
    required: bool = True
    enum: list[str] | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format.

        Returns:
            JSON Schema dictionary for this parameter
        """
        param_def: dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }

        if self.enum:
            param_def["enum"] = self.enum

        return param_def


@dataclass
class ToolResult:
    """Result of a tool execution."""

    content: str
    is_error: bool = False


@dataclass
class ToolSchema:
    """Schema definition for a tool."""

    parameters: list[ToolParameter]

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling format.

        Returns:
            OpenAI function schema dictionary
        """
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }


@runtime_checkable
class Tool(Protocol):
    """Protocol for tools that can be executed by the agent."""

    name: str
    description: str
    schema: ToolSchema

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
    ) -> ToolResult: ...
