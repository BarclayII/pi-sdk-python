# PI SDK Python

A minimal, general-purpose Python SDK for building LLM-powered tools and agents. Built on top of [LiteLLM](https://github.com/BerriAI/litellm), it provides a unified interface for working with multiple LLM providers including Anthropic Claude, OpenAI GPT, Google Gemini, and more.

## Features

- 🚀 **Stateful Agent** - Easy-to-use Agent class with streaming and multi-turn support
- 🔧 **Tool Calling** - Built-in support for LLM function/tool calling
- 🎯 **Multi-Provider** - Works with 100+ LLM providers via LiteLLM
- 📝 **Coding Tools** - Pre-built tools for file operations and code editing
- 💬 **Streaming** - Real-time streaming of LLM responses
- 🔄 **Multi-Turn Conversations** - Maintain conversation history across turns
- ⚡ **Async First** - Built with async/await for optimal performance

## Installation

```bash
pip install pi-sdk-python
```

Or install from source:

```bash
git clone https://github.com/BarclayII/pi-sdk-python.git
cd pi-sdk-python
pip install -e .
```

### Development Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

### 1. Set Up Environment

Create a `.env` file with your API configuration:

```bash
# Choose your model (via LiteLLM)
MODEL=anthropic/claude-sonnet-4-20250514

# Add your API key
API_KEY=your_api_key_here

# Optional: Custom API base URL
API_BASE=
```

See `.env.example` for more options.

### 2. Simple Chat Example

```python
import asyncio
import os
from dotenv import load_dotenv
from pi_sdk import Agent, LLMClient, TextDelta

load_dotenv()

async def main():
    # Create LLM client
    client = LLMClient(
        model=os.getenv("MODEL", "anthropic/claude-sonnet-4-20250514"),
        api_key=os.getenv("API_KEY"),
    )

    # Create agent
    agent = Agent(
        llm=client,
        system_prompt="You are a helpful assistant.",
        tools=[],  # No tools for simple chat
    )

    # Run agent
    async for event in agent.run("Hello! What can you help me with?"):
        if isinstance(event, TextDelta):
            print(event.delta, end="", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Coding Agent Example

Build an agent with file operations and command execution:

```python
import asyncio
import os
from dotenv import load_dotenv
from pi_sdk import Agent, LLMClient, TextDelta, ToolExecStart
from pi_sdk.tools import create_coding_tools

load_dotenv()

async def main():
    # Create LLM client
    client = LLMClient(
        model=os.getenv("MODEL"),
        api_key=os.getenv("API_KEY"),
    )

    # Create coding tools (read, write, edit, bash)
    tools = create_coding_tools(cwd=".")

    # Create agent
    agent = Agent(
        llm=client,
        system_prompt="You are an expert coding assistant.",
        tools=tools,
        max_turns=50,
    )

    # Run agent with tool support
    async for event in agent.run("Create a hello.py file"):
        if isinstance(event, TextDelta):
            print(event.delta, end="", flush=True)
        elif isinstance(event, ToolExecStart):
            print(f"\n[Tool: {event.name}]", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
```

## Core Concepts

### Agent

The `Agent` class manages the conversation flow between the user, LLM, and tools:

```python
async for event in agent.run(user_input):
    match event:
        case AgentStart():
            print("Agent started")
        case TextDelta(delta):
            print(delta, end="", flush=True)
        case ToolExecStart(name, arguments):
            print(f"\nExecuting {name} with {arguments}")
        case ToolExecEnd(content, is_error):
            print(f"Result: {content}")
        case TurnEnd(turn):
            print(f"\nTurn {turn} complete")
        case AgentEnd(messages):
            print("Agent finished")
```

### Messages

Messages follow a standardized format:

```python
from pi_sdk import UserMessage, AssistantMessage, ToolResultMessage

# User message
user_msg = UserMessage(content="Hello!")

# Assistant message with text and tool calls
assistant_msg = AssistantMessage(
    content=[
        TextContent(text="Let me check that file..."),
        ToolCallContent(id="1", name="read", arguments={"path": "file.txt"})
    ]
)

# Tool result message
tool_msg = ToolResultMessage(
    tool_call_id="1",
    tool_name="read",
    content="File contents here"
)
```

### LLM Client

The `LLMClient` wraps LiteLLM for unified access to multiple providers:

```python
from pi_sdk import LLMClient

# Anthropic Claude
client = LLMClient(
    model="anthropic/claude-sonnet-4-20250514",
    api_key="sk-ant-...",
)

# OpenAI GPT
client = LLMClient(
    model="openai/gpt-4o",
    api_key="sk-...",
)

# Google Gemini
client = LLMClient(
    model="google/gemini-2.0-flash-exp",
    api_key="...",
)

# Custom API endpoint
client = LLMClient(
    model="custom/model",
    api_key="...",
    api_base="https://custom-api.example.com/v1",
)
```

### Built-in Tools

#### Coding Tools

Create a complete set of file operation tools:

```python
from pi_sdk.tools import create_coding_tools

tools = create_coding_tools(cwd=".")  # [ReadTool, BashTool, EditTool, WriteTool]
```

**Available tools:**

- **`read`** - Read file contents with optional line offset/limit
- **`write`** - Write content to files (creates parent directories)
- **`edit`** - Edit files using fuzzy text matching
- **`bash`** - Execute shell commands with timeout

### Custom Tools

Create your own tools by implementing the `Tool` protocol:

```python
from dataclasses import dataclass
from pi_sdk.tools.base import Tool, ToolSchema, ToolParameter, ToolResult

@dataclass
class MyTool:
    """Custom tool implementation."""

    name: str = "my_tool"
    description: str = "Description of what this tool does"
    schema: ToolSchema = ToolSchema(
        parameters=[
            ToolParameter(
                name="param1",
                type="string",
                description="First parameter",
                required=True,
            ),
        ]
    )

    async def execute(self, tool_call_id: str, args: dict) -> ToolResult:
        """Execute the tool."""
        try:
            result = f"Processed: {args['param1']}"
            return ToolResult(content=result, is_error=False)
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)
```

### Multi-Turn Conversations

The `Agent` maintains conversation history automatically across calls:

```python
agent = Agent(llm=client, system_prompt="...", tools=tools)

# First turn
async for event in agent.run("What files are in this directory?"):
    pass

# Second turn - uses history from first turn
async for event in agent.run("Read the first file"):
    pass

# Third turn - full context preserved
async for event in agent.run("Edit line 5 of that file"):
    pass

# Reset history if needed
agent.reset()
```

### Event Handling

Subscribe to agent events for logging, monitoring, or UI updates:

```python
from pi_sdk import Agent, AgentEvent

def on_event(event: AgentEvent):
    """Handle agent events."""
    print(f"Event: {type(event).__name__}")

agent = Agent(
    llm=client,
    system_prompt="...",
    tools=tools,
    on_event=on_event,  # Event callback
)
```

## API Reference

### Core Classes

#### `LLMClient`

```python
LLMClient(
    model: str,                    # Model identifier (e.g., "anthropic/claude-sonnet-4-20250514")
    api_key: str | None = None,    # API key for the provider
    api_base: str | None = None,   # Custom API base URL
    max_tokens: int = 8192,        # Maximum tokens in response
    temperature: float | None = None,  # Sampling temperature
)
```

#### `Agent`

```python
Agent(
    llm: LLMClient,                           # LLM client instance
    system_prompt: str,                       # System prompt for the agent
    tools: list[Tool] = [],                   # List of available tools
    max_turns: int = 50,                      # Maximum conversation turns
    skills_dir: str | None = None,            # Optional skills directory
    on_event: Callable[[AgentEvent], None] | None = None,  # Event callback
)
```

**Methods:**

- `async run(user_input: str) -> AsyncGenerator[AgentEvent, None]` — Run the agent for a user input, yielding events.
- `reset()` — Clear message history.

### Events

- **`AgentStart`** - Agent loop started
- **`AgentEnd`** - Agent loop completed (includes final messages)
- **`TurnStart`** - New turn started
- **`TurnEnd`** - Turn completed
- **`TextDelta`** - Streaming text chunk from LLM
- **`ToolExecStart`** - Tool execution started
- **`ToolExecEnd`** - Tool execution completed

### Message Types

- **`UserMessage`** - Message from the user
- **`AssistantMessage`** - Response from the LLM
- **`ToolResultMessage`** - Result from tool execution

### Content Types

- **`TextContent`** - Plain text content
- **`ImageContent`** - Base64-encoded image
- **`ThinkingContent`** - Reasoning/thinking content (Claude-style)
- **`ToolCallContent`** - Function/tool call

## Examples

Run the included examples:

### Simple Chat

```bash
python examples/simple_chat.py
```

Interactive chat without tools.

### Coding Agent

```bash
python examples/coding_agent.py
```

Agent with file operations and command execution.

## Supported Models

Via LiteLLM, supports 100+ models including:

### Anthropic

- `anthropic/claude-sonnet-4-20250514`
- `anthropic/claude-3-5-sonnet-20241022`
- `anthropic/claude-3-opus-20240229`

### OpenAI

- `openai/gpt-4o`
- `openai/gpt-4o-mini`
- `openai/gpt-4-turbo`

### Google

- `google/gemini-2.0-flash-exp`
- `google/gemini-1.5-pro`

### Others

- Azure OpenAI
- Ollama (local models)
- Together AI
- Groq
- And many more...

See [LiteLLM documentation](https://docs.litellm.ai/docs/providers) for full provider list.

## Configuration

### Environment Variables

```bash
# Required
MODEL=anthropic/claude-sonnet-4-20250514
API_KEY=your_api_key_here

# Optional
API_BASE=                    # Custom API endpoint
SYSTEM_PROMPT=              # Override default system prompt
CWD=.                       # Working directory for file operations
```

### Python Configuration

```python
from pi_sdk import LLMClient, Agent

# Configure LLM client
client = LLMClient(
    model="anthropic/claude-sonnet-4-20250514",
    api_key="sk-ant-...",
    api_base=None,           # Optional custom endpoint
    max_tokens=8192,         # Response token limit
    temperature=None,        # Sampling temperature (provider default)
)

# Create agent
agent = Agent(
    llm=client,
    system_prompt="Your system prompt here",
    tools=create_coding_tools(cwd="."),
    max_turns=50,            # Maximum conversation turns
)
```

## Development

### Running Tests

```bash
# Run basic tests
python test_sdk.py

# Run with pytest (if installed)
pytest
```

### Project Structure

```
pi-sdk-python/
├── pi_sdk/
│   ├── __init__.py          # Public API exports
│   ├── agent.py             # Agent loop implementation
│   ├── agent_types.py       # Event types
│   ├── llm_client.py        # LiteLLM wrapper
│   ├── types.py             # Message types
│   └── tools/
│       ├── __init__.py      # Tool exports
│       ├── base.py          # Tool protocol
│       ├── read.py          # Read file tool
│       ├── write.py         # Write file tool
│       ├── edit.py          # Edit file tool
│       ├── bash.py          # Bash command tool
│       └── ...              # Utilities
├── examples/
│   ├── simple_chat.py       # Simple chat example
│   └── coding_agent.py      # Coding agent example
├── pyproject.toml           # Project metadata
└── README.md                # This file
```

## Requirements

- Python 3.11+
- litellm >= 1.81
- python-dotenv >= 1.0

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is open source. Please check the repository for license details.

## Acknowledgments

- Built on [LiteLLM](https://github.com/BerriAI/litellm) for multi-provider LLM access
- Inspired by modern agentic frameworks and tool-calling patterns

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/yourusername/pi-sdk-python).

---

**Happy building! 🚀**
