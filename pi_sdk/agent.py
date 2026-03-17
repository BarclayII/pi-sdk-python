"""
Agent loop for pi-sdk-python.

This module provides the core agent loop that manages conversations with the LLM.
"""

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Union

from pi_sdk.agent_types import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    TextDelta,
    ToolExecEnd,
    ToolExecStart,
    ToolResultData,
    TurnEnd,
    TurnStart,
)
from pi_sdk.llm_client import LLMClient, StreamEvent
from pi_sdk.skills import load_skills
from pi_sdk.tools.base import Tool
from pi_sdk.types import (
    AssistantMessage,
    Message,
    ToolCallContent,
    ToolResultMessage,
    UserMessage,
)


@dataclass
class AgentConfig:
    """Configuration for the agent loop."""

    llm: LLMClient
    system_prompt: str
    tools: list[Tool] = None
    max_turns: int = 50
    skills_dir: str | None = None
    on_event: Callable[[AgentEvent], None] | None = None

    def __post_init__(self):
        if self.tools is None:
            self.tools = []
        if self.skills_dir:
            skills_xml = load_skills(self.skills_dir)
            if skills_xml:
                self.system_prompt = self.system_prompt + "\n\n" + skills_xml


async def agent_loop(
    user_input: str,
    config: AgentConfig,
    messages: list[Message] | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """Run the agent loop.

    Args:
        user_input: Initial user input
        config: Agent configuration
        messages: Optional message history for multi-round conversations.
            When provided, the list is mutated in place — new messages are
            appended so the caller can reuse it across calls.

    Yields:
        AgentEvent instances for each step of the agent loop
    """
    yield AgentStart()

    if messages is None:
        messages = []
    messages.append(UserMessage(content=user_input))

    for turn in range(config.max_turns):
        yield TurnStart(turn=turn)

        # Stream LLM response
        assistant_message: AssistantMessage | None = None
        async for event in config.llm.stream(
            messages, config.tools, config.system_prompt
        ):
            if isinstance(event.event, TextDelta):
                yield TextDelta(delta=event.event.delta)
            elif isinstance(event.event, AssistantMessage):
                assistant_message = event.event

        if assistant_message is None:
            # This shouldn't happen, but handle gracefully
            assistant_message = AssistantMessage(
                role="assistant", content=[], model="", stop_reason=""
            )

        messages.append(assistant_message)

        # Extract tool calls
        tool_calls = [
            block
            for block in assistant_message.content
            if isinstance(block, ToolCallContent)
        ]

        if not tool_calls:
            # No more tool calls, we're done
            yield TurnEnd(turn=turn)
            break

        # Execute tool calls
        for tool_call in tool_calls:
            yield ToolExecStart(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                arguments=tool_call.arguments,
            )

            # Find the tool
            tool = None
            for t in config.tools:
                if t.name == tool_call.name:
                    tool = t
                    break

            if tool is None:
                result = ToolResultData(
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    content=f"Error: Tool '{tool_call.name}' not found",
                    is_error=True,
                )
            else:
                try:
                    tool_result = await tool.execute(tool_call.id, tool_call.arguments)
                    result = ToolResultData(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=tool_result.content,
                        is_error=tool_result.is_error,
                    )
                except Exception as e:
                    result = ToolResultData(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=f"Error executing tool: {e!s}",
                        is_error=True,
                    )

            yield ToolExecEnd(
                tool_call_id=result.tool_call_id,
                name=result.name,
                content=result.content,
                is_error=result.is_error,
            )

            # Add tool result to messages
            messages.append(
                ToolResultMessage(
                    role="tool_result",
                    tool_call_id=result.tool_call_id,
                    tool_name=result.name,
                    content=result.content,
                    is_error=result.is_error,
                )
            )

        yield TurnEnd(turn=turn)

    yield AgentEnd(messages=messages)


async def run_agent(
    user_input: str,
    config: AgentConfig,
    messages: list[Message] | None = None,
) -> list[Message]:
    """Run the agent loop and return final messages.

    Args:
        user_input: Initial user input
        config: Agent configuration
        messages: Optional message history for multi-round conversations.
            When provided, the list is mutated in place.

    Returns:
        List of all messages from the conversation
    """
    final_messages: list[Message] = []

    async for event in agent_loop(user_input, config, messages):
        if config.on_event:
            config.on_event(event)

        if isinstance(event, AgentEnd):
            final_messages = event.messages

    return final_messages
