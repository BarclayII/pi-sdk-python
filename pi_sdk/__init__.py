"""
pi-sdk-python - Minimal Python Agent SDK

A minimal, general-purpose Python SDK for building LLM-powered tools and agents.
"""

# Public API - Types
from pi_sdk.types import (
    AssistantMessage,
    ImageContent,
    Message,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)

# Public API - LLM Client
from pi_sdk.llm_client import LLMClient, StreamEvent, TextDelta as ClientTextDelta

# Public API - Agent
from pi_sdk.agent import AgentConfig, agent_loop, run_agent
from pi_sdk.agent_types import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    TextDelta,
    ToolExecEnd,
    ToolExecStart,
    TurnEnd,
    TurnStart,
)

# Public API - Skills
from pi_sdk.skills import load_skills

# Public API - Tools
from pi_sdk.tools import create_coding_tools
from pi_sdk.tools.base import Tool, ToolParameter, ToolResult, ToolSchema

__version__ = "0.1.0"

__all__ = [
    # Types
    "UserMessage",
    "AssistantMessage",
    "ToolResultMessage",
    "Message",
    "TextContent",
    "ImageContent",
    "ThinkingContent",
    "ToolCallContent",
    "Usage",
    # LLM Client
    "LLMClient",
    "StreamEvent",
    # Agent
    "AgentConfig",
    "agent_loop",
    "run_agent",
    "AgentEvent",
    "AgentStart",
    "AgentEnd",
    "TurnStart",
    "TurnEnd",
    "TextDelta",
    "ToolExecStart",
    "ToolExecEnd",
    # Skills
    "load_skills",
    # Tools
    "Tool",
    "ToolParameter",
    "ToolResult",
    "ToolSchema",
    "create_coding_tools",
]
