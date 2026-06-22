"""
Vision / Video Chat Example

This example demonstrates how to send images and videos to a multimodal
model (e.g. kimi-k2.7-code) using pi-sdk-python.

Usage:
    # Ask about an image
    python examples/vision_chat.py image.png "What is inside this image?"

    # Ask about a video
    python examples/vision_chat.py video.mp4 "Describe the content of this video."

If no arguments are given, it defaults to image.png with a generic prompt.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from pi_sdk import (
    Agent,
    ImageContent,
    LLMClient,
    TextContent,
    TextDelta,
    VideoContent,
)

# Load environment variables
load_dotenv()

# Extensions we treat as video; everything else is treated as an image.
VIDEO_EXTS = {
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mov",
    ".avi",
    ".flv",
    ".webm",
    ".wmv",
    ".3gp",
    ".3gpp",
}


def build_media_block(path: str):
    """Return an ImageContent or VideoContent based on the file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return VideoContent.from_path(path)
    return ImageContent.from_path(path)


async def main():
    """Run the vision/video chat example."""
    # Parse args: <media_path> [prompt...]
    media_path = sys.argv[1] if len(sys.argv) > 1 else "image.png"
    prompt = (
        " ".join(sys.argv[2:])
        if len(sys.argv) > 2
        else f"What is inside {media_path}?"
    )

    # Get configuration from environment (.env)
    model = os.getenv("MODEL", "kimi-k2.7-code")
    api_key = os.getenv("API_KEY")
    api_base = os.getenv("API_BASE")

    if not api_key:
        print("Error: API_KEY environment variable is required")
        return

    if not os.path.exists(media_path):
        print(f"Error: file not found: {media_path}")
        return

    # Create the LLM client
    client = LLMClient(
        model=model,
        api_key=api_key,
        api_base=api_base,
    )

    # Configure the agent (no tools needed for a vision query)
    agent = Agent(
        llm=client,
        system_prompt="You are a helpful assistant.",
        tools=[],
    )

    media_block = build_media_block(media_path)

    print("=" * 60)
    print(f"PI SDK Python - Vision Chat ({model})")
    print("=" * 60)
    print(f"\nFile:   {media_path} ({media_block.mime_type})")
    print(f"Prompt: {prompt}\n")

    # Send text + media as multimodal content
    async for event in agent.run(
        [
            TextContent(text=prompt),
            media_block,
        ]
    ):
        if isinstance(event, TextDelta):
            print(event.delta, end="", flush=True)

    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
