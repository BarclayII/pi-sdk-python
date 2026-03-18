"""
LiteLLM client wrapper for streaming LLM requests.

This module provides a unified interface for calling various LLM providers
through LiteLLM.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Literal, Union

import httpx
import litellm

AIHUBMIX_API_BASE = "https://aihubmix.com/api/v1"

from pi_sdk.agent_types import TextDelta
from pi_sdk.types import (
    AssistantMessage,
    ContentBlock,
    ImageContent,
    Message,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)


@dataclass
class StreamEvent:
    """Union type for stream events."""

    event: Union[TextDelta, AssistantMessage]


@dataclass
class LLMClient:
    """Client for LLM requests via LiteLLM."""

    model: str  # e.g. "anthropic/claude-sonnet-4-20250514"
    api_key: str | None = None
    api_base: str = AIHUBMIX_API_BASE
    max_tokens: int = 8192
    temperature: float | None = None

    async def get_context_window(self) -> int:
        """Query the aihubmix /models endpoint for this model's context window.

        Returns:
            context_length for the model

        Raises:
            RuntimeError: if the request fails or the response is unexpected
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/models",
                params={"model": self.model},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch model info: HTTP {response.status_code}"
            )
        data = response.json()
        if not data.get("success"):
            raise RuntimeError("Model info request returned success=false")
        if not data.get("data"):
            raise RuntimeError(f"No model data returned for model '{self.model}'")
        return data["data"][0]["context_length"]

    async def stream(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream a completion from the LLM.

        Args:
            messages: List of messages in the conversation
            tools: List of tools (Tool protocol instances)
            system_prompt: Optional system prompt

        Yields:
            StreamEvent with either TextDelta or AssistantMessage
        """
        # Convert messages to LiteLLM format
        litellm_messages = self._convert_messages(messages, system_prompt)

        # Convert tools to OpenAI function-calling format
        functions = None
        if tools:
            functions = [self._convert_tool(tool) for tool in tools]

        # Prepare LiteLLM kwargs
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": litellm_messages,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        if functions:
            kwargs["tools"] = functions
            kwargs["tool_choice"] = "auto"

        if self.api_key:
            kwargs["api_key"] = self.api_key

        if self.api_base:
            kwargs["api_base"] = self.api_base

        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        # Stream the response
        chunks: list[Any] = []
        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            chunks.append(chunk)

            # Yield text deltas
            if hasattr(chunk, "choices") and chunk.choices:
                choice = chunk.choices[0]
                if hasattr(choice, "delta"):
                    delta = choice.delta
                    if hasattr(delta, "content") and delta.content:
                        yield StreamEvent(event=TextDelta(delta=delta.content))

        # Reconstruct the full message from chunks
        message = litellm.stream_chunk_builder(chunks, messages=litellm_messages)

        # Parse the response into AssistantMessage
        assistant_message = self._parse_assistant_message(message)
        yield StreamEvent(event=assistant_message)

    def _convert_messages(
        self, messages: list[Message], system_prompt: str | None
    ) -> list[dict[str, Any]]:
        """Convert pi_sdk Message types to LiteLLM format.

        Args:
            messages: List of messages
            system_prompt: Optional system prompt

        Returns:
            List of LiteLLM message dictionaries
        """
        result: list[dict[str, Any]] = []

        # Add system prompt first if provided
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if isinstance(msg, UserMessage):
                result.append(self._convert_user_message(msg))
            elif isinstance(msg, AssistantMessage):
                result.append(self._convert_assistant_message(msg))
            elif isinstance(msg, ToolResultMessage):
                result.append(self._convert_tool_result_message(msg))

        return result

    def _convert_user_message(self, msg: UserMessage) -> dict[str, Any]:
        """Convert a UserMessage to LiteLLM format."""
        if isinstance(msg.content, str):
            return {"role": "user", "content": msg.content}

        # Handle content blocks
        content: list[dict[str, Any]] = []
        for block in msg.content:
            if isinstance(block, TextContent):
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ImageContent):
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{block.mime_type};base64,{block.data}"
                        },
                    }
                )

        return {"role": "user", "content": content}

    def _convert_assistant_message(self, msg: AssistantMessage) -> dict[str, Any]:
        """Convert an AssistantMessage to LiteLLM format."""
        # Build content list
        content: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []

        for block in msg.content:
            if isinstance(block, TextContent):
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ThinkingContent):
                # Skip thinking content for now (not supported by all providers)
                pass
            elif isinstance(block, ToolCallContent):
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.arguments)
                            if isinstance(block.arguments, dict)
                            else block.arguments,
                        },
                    }
                )

        result: dict[str, Any] = {"role": "assistant"}

        if content:
            result["content"] = content

        if tool_calls:
            result["tool_calls"] = tool_calls

        return result

    def _convert_tool_result_message(self, msg: ToolResultMessage) -> dict[str, Any]:
        """Convert a ToolResultMessage to LiteLLM format."""
        return {
            "role": "tool",
            "tool_call_id": msg.tool_call_id,
            "name": msg.tool_name,
            "content": msg.content,
        }

    def _convert_tool(self, tool: Any) -> dict[str, Any]:
        """Convert a Tool to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.schema.to_openai_schema(),
            },
        }

    def _parse_assistant_message(self, response: Any) -> AssistantMessage:
        """Parse a LiteLLM response into an AssistantMessage.

        Args:
            response: LiteLLM response object (ModelResponse or Message)

        Returns:
            AssistantMessage with parsed content
        """
        content: list[ContentBlock] = []

        # Handle ModelResponse (from stream_chunk_builder) - extract message
        message = response
        if hasattr(response, "choices") and response.choices:
            message = response.choices[0].message

        # Parse text content
        if hasattr(message, "content") and message.content:
            if isinstance(message.content, str):
                content.append(TextContent(text=message.content))
            else:
                # Handle list of content blocks
                for block in message.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        content.append(TextContent(text=block.get("text", "")))

        # Parse tool calls
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_calls = message.tool_calls

        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                function = tool_call.get("function", {})
                content.append(
                    ToolCallContent(
                        type="tool_call",
                        id=tool_call.get("id", ""),
                        name=function.get("name", ""),
                        arguments=(
                            function.get("arguments", {})
                            if isinstance(function.get("arguments"), dict)
                            else {}
                        ),
                    )
                )
            elif hasattr(tool_call, "function"):
                # Handle litellm ChatCompletionMessageToolCall objects
                function = tool_call.function
                args = function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                content.append(
                    ToolCallContent(
                        type="tool_call",
                        id=tool_call.id,
                        name=function.name,
                        arguments=args,
                    )
                )

        # Parse usage
        usage = Usage()
        usage_response = response if hasattr(response, "usage") else message
        if hasattr(usage_response, "usage") and usage_response.usage:
            usage_info = usage_response.usage
            if hasattr(usage_info, "prompt_tokens"):
                usage.input_tokens = usage_info.prompt_tokens
            if hasattr(usage_info, "completion_tokens"):
                usage.output_tokens = usage_info.completion_tokens
            if hasattr(usage_info, "cache_read_tokens"):
                usage.cache_read_tokens = usage_info.cache_read_tokens
            if hasattr(usage_info, "cache_write_tokens"):
                usage.cache_write_tokens = usage_info.cache_write_tokens

        # Get model and stop_reason from the appropriate source
        model = getattr(response, "model", getattr(message, "model", ""))
        stop_reason = ""
        if hasattr(response, "choices") and response.choices:
            stop_reason = getattr(response.choices[0], "finish_reason", "")

        return AssistantMessage(
            role="assistant",
            content=content,
            model=model,
            stop_reason=stop_reason,
            usage=usage,
        )
