"""
Agent module for pi-sdk-python.

This module provides the stateful Agent class that manages conversations with the LLM.
"""

import json
from typing import AsyncGenerator, Callable

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
from pi_sdk.llm_client import LLMClient, StreamEvent
from pi_sdk.skills import load_skills
from pi_sdk.tools.base import Tool
from pi_sdk.types import (
    AssistantMessage,
    Message,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
    UserMessage,
)


class Agent:
    """Stateful agent that holds messages and config, making multi-round conversations natural."""

    def __init__(
        self,
        llm: LLMClient,
        system_prompt: str,
        tools: list[Tool] | None = None,
        max_turns: int = 50,
        skills_dir: str | None = None,
        on_event: Callable[[AgentEvent], None] | None = None,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.max_turns = max_turns
        self.on_event = on_event
        self.messages: list[Message] = []

        if skills_dir:
            skills_xml = load_skills(skills_dir)
            if skills_xml:
                self.system_prompt += "\n\n" + skills_xml

    async def run(self, user_input: str) -> AsyncGenerator[AgentEvent, None]:
        """Run the agent loop for a single user input.

        Appends the user message and all subsequent assistant/tool messages
        to self.messages, so the caller can issue multiple run() calls for
        multi-round conversations.

        Yields:
            AgentEvent instances for each step of the agent loop.
        """
        yield AgentStart()

        self.messages.append(UserMessage(content=user_input))

        for turn in range(self.max_turns):
            yield TurnStart(turn=turn)

            # Stream LLM response
            assistant_message: AssistantMessage | None = None
            async for event in self.llm.stream(
                self.messages, self.tools, self.system_prompt
            ):
                if isinstance(event.event, TextDelta):
                    yield TextDelta(delta=event.event.delta)
                elif isinstance(event.event, AssistantMessage):
                    assistant_message = event.event

            if assistant_message is None:
                assistant_message = AssistantMessage(
                    role="assistant", content=[], model="", stop_reason=""
                )

            self.messages.append(assistant_message)

            # Extract tool calls
            tool_calls = [
                block
                for block in assistant_message.content
                if isinstance(block, ToolCallContent)
            ]

            if not tool_calls:
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
                for t in self.tools:
                    if t.name == tool_call.name:
                        tool = t
                        break

                if tool is None:
                    result = ToolExecEnd(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=f"Error: Tool '{tool_call.name}' not found",
                        is_error=True,
                    )
                else:
                    try:
                        tool_result = await tool.execute(
                            tool_call.id, tool_call.arguments
                        )
                        result = ToolExecEnd(
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                            content=tool_result.content,
                            is_error=tool_result.is_error,
                        )
                    except Exception as e:
                        result = ToolExecEnd(
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                            content=f"Error executing tool: {e!s}",
                            is_error=True,
                        )

                yield result

                # Add tool result to messages
                self.messages.append(
                    ToolResultMessage(
                        tool_call_id=result.tool_call_id,
                        tool_name=result.name,
                        content=result.content,
                        is_error=result.is_error,
                    )
                )

            yield TurnEnd(turn=turn)

        yield AgentEnd(messages=self.messages)

    def reset(self):
        """Clear message history."""
        self.messages = []
