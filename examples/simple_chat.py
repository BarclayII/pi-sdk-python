"""
Simple Chat Example

This example demonstrates how to use pi-sdk-python for a simple chat
without any tools.
"""

import asyncio
import os
from dotenv import load_dotenv

from pi_sdk import Agent, LLMClient, TextDelta

# Load environment variables
load_dotenv()


async def main():
    """Run the simple chat example."""
    # Get configuration from environment
    model = os.getenv("MODEL", "anthropic/claude-sonnet-4-20250514")
    api_key = os.getenv("API_KEY")
    api_base = os.getenv("API_BASE")

    # Validate configuration
    if not api_key:
        print("Error: API_KEY environment variable is required")
        print("Set it in your .env file or export it:")
        print("  export API_KEY=your_api_key_here")
        return

    # Create the LLM client
    client = LLMClient(
        model=model,
        api_key=api_key,
        api_base=api_base,
    )

    # Configure the agent (no tools)
    agent = Agent(
        llm=client,
        system_prompt="You are a helpful assistant. Be concise and friendly.",
        tools=[],  # No tools for simple chat
    )

    # Get user input
    print("=" * 60)
    print("PI SDK Python - Simple Chat")
    print("=" * 60)
    print("\nEnter your message (or 'quit' to exit):\n")

    while True:
        try:
            user_input = input("> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            # Run the agent loop
            print()
            async for event in agent.run(user_input):
                if isinstance(event, TextDelta):
                    print(event.delta, end="", flush=True)

            print("\n")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
