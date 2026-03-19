"""
Agent module for pi-sdk-python.

This module provides the stateful Agent class that manages conversations with the LLM.
"""

import json
import logging
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
    Usage,
    UserMessage,
)

logger = logging.getLogger(__name__)


def _format_messages_for_compact(messages: list[Message]) -> str:
    """Format messages into a compact text representation for summarization.

    Converts structured messages into a flat text format:
      USER: ...
      ASSISTANT: ...
      TOOL(name, {args}): content
    """
    # Build lookup of tool_call_id -> (name, arguments) from AssistantMessages
    tool_call_map: dict[str, tuple[str, dict]] = {}
    for msg in messages:
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolCallContent):
                    tool_call_map[block.id] = (block.name, block.arguments)

    lines: list[str] = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            lines.append(f"USER: {content}")
        elif isinstance(msg, AssistantMessage):
            text_parts = [b.text for b in msg.content if isinstance(b, TextContent)]
            if text_parts:
                lines.append(f"ASSISTANT: {' '.join(text_parts)}")
        elif isinstance(msg, ToolResultMessage):
            _, args = tool_call_map.get(msg.tool_call_id, (msg.tool_name, {}))
            error_tag = " [ERROR]" if msg.is_error else ""
            lines.append(
                f"TOOL({msg.tool_name}, {json.dumps(args)}):{error_tag} {msg.content}"
            )

    return "\n".join(lines)


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
        auto_compact: bool = True,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.max_turns = max_turns
        self.on_event = on_event
        self.auto_compact = auto_compact
        self.messages: list[Message] = []
        self._context_window: int | None = None

        if skills_dir:
            skills_xml = load_skills(skills_dir)
            if skills_xml:
                self.system_prompt += "\n\n" + skills_xml

    async def run(
        self,
        user_input: str,
        response_format: dict | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run the agent loop for a single user input.

        Appends the user message and all subsequent assistant/tool messages
        to self.messages, so the caller can issue multiple run() calls for
        multi-round conversations.

        Args:
            user_input: The user's message text.
            response_format: Optional structured output format
                (e.g. {"type": "json_schema", "json_schema": {...}}).

        Yields:
            AgentEvent instances for each step of the agent loop.
        """
        yield AgentStart()

        logger.info("User prompt:\n%s", user_input)
        self.messages.append(UserMessage(content=user_input))

        for turn in range(self.max_turns):
            yield TurnStart(turn=turn)

            # Auto-compact if approaching context limit
            await self._maybe_compact()

            # Stream LLM response
            assistant_message: AssistantMessage | None = None
            async for event in self.llm.stream(
                self.messages, self.tools, self.system_prompt, response_format
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

    def _get_last_usage(self) -> Usage | None:
        """Find the most recent AssistantMessage's usage info."""
        for msg in reversed(self.messages):
            if isinstance(msg, AssistantMessage) and msg.usage:
                return msg.usage
        return None

    async def _maybe_compact(self) -> None:
        """Compact messages if approaching the context window limit."""
        if not self.auto_compact or len(self.messages) < 4:
            return

        usage = self._get_last_usage()
        if usage is None or usage.input_tokens == 0:
            return

        # Fetch and cache context window size
        if self._context_window is None:
            self._context_window = await self.llm.get_context_window()

        threshold = int(self._context_window * 0.80)
        if usage.input_tokens < threshold:
            return

        logger.info(
            "Auto-compacting (input_tokens=%d, threshold=%d)",
            usage.input_tokens,
            threshold,
        )
        await self.compact()

    async def _summarize(self, messages: list[Message]) -> str:
        """Summarize messages via an LLM call."""
        formatted = _format_messages_for_compact(messages)
        summary_messages: list[Message] = [
            UserMessage(
                content=(
                    "Summarize this conversation history concisely. "
                    "Preserve key decisions, file paths, errors, and outcomes.\n\n"
                    f"{formatted}"
                )
            )
        ]
        result = ""
        async for event in self.llm.stream(
            summary_messages, tools=None, system_prompt=None
        ):
            if isinstance(event.event, AssistantMessage):
                for block in event.event.content:
                    if isinstance(block, TextContent):
                        result += block.text
        return result

    async def compact(self) -> str | None:
        """Manually compact the conversation history.

        Forces compaction regardless of token usage, summarizing all messages
        into a summary UserMessage followed by an assistant acknowledgment.

        Returns:
            The summary text if compaction was performed, None otherwise.
        """
        if len(self.messages) < 4:
            logger.info("Skipping compact: fewer than 4 messages")
            return None

        logger.info("Manually compacting %d messages", len(self.messages))

        try:
            summary = await self._summarize(self.messages)
        except Exception:
            logger.warning(
                "Summarization failed during manual compaction", exc_info=True
            )
            return None

        if not summary:
            return None

        self.messages = [
            UserMessage(content=f"<context-summary>\n{summary}\n</context-summary>"),
            AssistantMessage(
                role="assistant",
                content=[TextContent(text="Understood, I have the context.")],
            ),
        ]
        return summary

    def reset(self):
        """Clear message history."""
        self.messages = []
