"""Build Agent instances from agent directory files."""

import os
from pathlib import Path

from pi_sdk import Agent, LLMClient
from pi_sdk.tools import create_coding_tools

from game_state import GameState
from prompts import agent_system_prompt


def build_agent_config(
    agent_name: str,
    agent_dir: str,
    role_description: str,
    mafia_allies: list[str] | None = None,
) -> Agent:
    """Build a persistent Agent from an agent's directory files.

    The system prompt is static (personality + role + game rules).
    Round-specific info is delivered via user messages during gameplay.

    Args:
        agent_name: Name of the agent.
        agent_dir: Path to the agent's directory.
        role_description: The agent's role description text.
        mafia_allies: Names of fellow mafia members (for mafia agents only).

    Returns:
        Configured Agent ready for agent.run().
    """
    agent_path = Path(agent_dir)

    personality = (agent_path / "PERSONALITY.md").read_text().strip()
    model = (agent_path / "MODEL.txt").read_text().strip()

    llm = LLMClient(
        model=f"openai/{model}",
        api_key=os.getenv("API_KEY"),
        api_base=os.getenv("API_BASE", "https://aihubmix.com/api/v1"),
        max_tokens=2048,
    )

    system_prompt = agent_system_prompt(
        personality=personality,
        role_description=role_description,
        agent_name=agent_name,
        mafia_allies=mafia_allies,
    )

    data_dir = str(agent_path / "data")
    return Agent(
        llm=llm,
        system_prompt=system_prompt,
        tools=create_coding_tools(cwd=data_dir),
        max_turns=20,
    )


def build_all_agents(
    state: GameState,
    agent_dirs: dict[str, str],
) -> dict[str, Agent]:
    """Create one persistent Agent per player at game start.

    Args:
        state: Game state with roles assigned.
        agent_dirs: Mapping of player name to agent directory path.

    Returns:
        Mapping of player name to Agent instance.
    """
    all_mafia = [p for p in state.players if state.roles.get(p) == "mafia"]
    agents = {}
    for name in state.players:
        if name not in agent_dirs:
            continue
        mafia_allies = None
        if state.roles.get(name) == "mafia":
            mafia_allies = [m for m in all_mafia if m != name]
        agents[name] = build_agent_config(
            agent_name=name,
            agent_dir=agent_dirs[name],
            role_description=state.get_role_description(name),
            mafia_allies=mafia_allies,
        )
    return agents


def build_facilitator(model: str | None = None) -> Agent:
    """Build an Agent for the facilitator.

    Args:
        model: Model to use. Defaults to env var FACILITATOR_MODEL or openai/claude-haiku-4-5.

    Returns:
        Configured Agent (no tools, always returns JSON).
    """
    model = model or os.getenv("FACILITATOR_MODEL", "openai/claude-haiku-4-5")
    llm = LLMClient(
        model=model,
        api_key=os.getenv("API_KEY"),
        api_base=os.getenv("API_BASE", "https://aihubmix.com/api/v1"),
        max_tokens=4096,
    )
    return Agent(
        llm=llm,
        system_prompt="You are a helpful assistant. Always return ONLY valid JSON.",
    )
