"""
Agentic Vision / Video Chat Example

Demonstrates that the agent can read images and videos *on its own* when a
plain-text prompt refers to a file (e.g. "What is inside image.png?").

Unlike examples/vision_chat.py -- where the caller attaches the media block
themselves -- here the agent is given the standard coding tools (which include
`read`). The `read` tool detects media via libmagic and returns it as a content
block, so a multimodal model (e.g. kimi-k2.7-code) views it directly in the
tool result. No manual attaching of media required.

Usage:
    python examples/agentic_vision_chat.py "What is inside image.png?"
    python examples/agentic_vision_chat.py "What happens in video.mp4?"

If no prompt is given, it defaults to asking about image.png.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from pi_sdk import Agent, LLMClient, TextDelta, ToolExecStart
from pi_sdk.tools import create_coding_tools

# Load environment variables
load_dotenv()


async def main():
    """Run the agentic vision/video chat example."""
    prompt = (
        " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is inside image.png?"
    )

    # Get configuration from environment (.env)
    model = os.getenv("MODEL", "openai/kimi-k2.7-code")
    api_key = os.getenv("API_KEY")
    api_base = os.getenv("API_BASE")

    if not api_key:
        print("Error: API_KEY environment variable is required")
        return

    # Create the LLM client
    client = LLMClient(
        model=model,
        api_key=api_key,
        api_base=api_base,
    )

    # Give the agent the coding tools -- `read` handles images and videos.
    agent = Agent(
        llm=client,
        system_prompt=(
            "You are a helpful assistant. Use the read tool to inspect files "
            "(including images and videos) when the user asks about them."
        ),
        tools=create_coding_tools(cwd="."),
    )

    print("=" * 60)
    print(f"PI SDK Python - Agentic Vision Chat ({model})")
    print("=" * 60)
    print(f"\nPrompt: {prompt}\n")

    async for event in agent.run(prompt):
        if isinstance(event, ToolExecStart):
            print(f"\n[tool: {event.name}({event.arguments})]\n")
        elif isinstance(event, TextDelta):
            print(event.delta, end="", flush=True)

    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
