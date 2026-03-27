"""Mafia Game - Multi-Agent LLM Party Game.

Usage:
    python main.py agents/alice agents/bob agents/charlie ... [options]

Each agent directory must contain:
    PERSONALITY.md  - Agent's personality description
    MODEL.txt       - LLM model identifier
"""

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add parent dirs to path so we can import pi_sdk and local modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pi_sdk import Agent

from agent_factory import build_all_agents, build_facilitator
from game_state import GameState
from orchestrator import (
    day_phase,
    diary_phase,
    mayor_election_diary_phase,
    mayor_election_phase,
    night_phase,
    postgame_phase,
)
from tmux_utils import create_session, log_to_agent

from loguru import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mafia Game - Multi-Agent LLM")
    parser.add_argument(
        "agent_dirs",
        nargs="+",
        help="Paths to agent directories (each with PERSONALITY.md and MODEL.txt)",
    )
    parser.add_argument(
        "--mayor-rounds",
        type=int,
        default=30,
        help="Mayor election discussion rounds (default: 30)",
    )
    parser.add_argument(
        "--mafia-rounds",
        type=int,
        default=20,
        help="Mafia meeting discussion rounds (default: 20)",
    )
    parser.add_argument(
        "--day-rounds",
        type=int,
        default=30,
        help="Day meeting discussion rounds (default: 30)",
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="Runtime data directory (default: ./data)",
    )
    parser.add_argument(
        "--session-name",
        default="mafia",
        help="Tmux session name (default: mafia)",
    )
    parser.add_argument(
        "--facilitator-model",
        default=None,
        help="Model for facilitator agent (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--no-tmux",
        action="store_true",
        help="Disable tmux session creation",
    )
    parser.add_argument(
        "--llm-consensus",
        action="store_true",
        help="Use LLM facilitator for consensus detection in addition to eagerness-based consensus",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


async def game_loop(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    facilitator,
    mafia_rounds: int,
    day_rounds: int,
    session_name: str,
    use_llm_consensus: bool = False,
) -> str:
    """Main game loop. Returns winner: 'village' or 'mafia'."""

    while True:
        state.round_id += 1
        logger.info("========== ROUND {} ==========", state.round_id)

        for name in state.alive:
            log_to_agent(
                agent_dirs[name], f"========== ROUND {state.round_id} =========="
            )

        # Night phase
        logger.info("--- Night {} ---", state.round_id)
        killed, poisoned = await night_phase(
            state,
            agent_dirs,
            agents,
            facilitator,
            mafia_rounds,
            session_name,
            use_llm_consensus=use_llm_consensus,
        )

        if killed:
            logger.info("Mafia killed: {}", killed)
        if poisoned:
            logger.info("Doctor poisoned: {}", poisoned)

        # Day phase
        logger.info("--- Day {} ---", state.round_id)
        eliminated, day_transcript_lines = await day_phase(
            state,
            agent_dirs,
            agents,
            facilitator,
            day_rounds,
            killed,
            poisoned,
            session_name,
            use_llm_consensus=use_llm_consensus,
        )

        if eliminated:
            logger.info("Voted out: {} (role: {})", eliminated, state.roles[eliminated])

        # Check win condition
        winner = state.check_win()
        if winner:
            return winner

        # Diary phase
        logger.info("--- Diary phase ---")
        await diary_phase(state, agent_dirs, agents, day_transcript_lines)

        logger.info(
            "Alive: {}",
            ", ".join(f"{n} ({state.roles[n]})" for n in sorted(state.alive)),
        )


async def main():
    load_dotenv()
    args = parse_args()

    logger.remove()
    logger.add(sys.stderr, level=args.log_level)

    # Validate agent directories
    agent_dirs: dict[str, str] = {}
    for d in args.agent_dirs:
        path = Path(d).resolve()
        if not path.is_dir():
            logger.error("Agent directory not found: {}", d)
            sys.exit(1)
        if not (path / "PERSONALITY.md").exists():
            logger.error("Missing PERSONALITY.md in {}", d)
            sys.exit(1)
        if not (path / "MODEL.txt").exists():
            logger.error("Missing MODEL.txt in {}", d)
            sys.exit(1)
        name = path.name
        agent_dirs[name] = str(path)

    if len(agent_dirs) < 5:
        logger.error("Need at least 5 agents to play Mafia.")
        sys.exit(1)

    # Create data directories for each agent and distribute RULES.md
    rules_src = Path(__file__).resolve().parent / "RULES.md"
    for name, agent_dir in agent_dirs.items():
        data_path = Path(agent_dir) / "data"
        data_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rules_src, data_path / "RULES.md")

    # Initialize game state
    state = GameState(
        players=list(agent_dirs.keys()),
        data_dir=str(Path(args.data_dir).resolve()),
    )
    state.assign_roles()

    logger.info("=== MAFIA GAME ===")
    logger.info("Players: {}", ", ".join(state.players))
    logger.info(
        "Roles: {}",
        ", ".join(f"{n}: {r}" for n, r in sorted(state.roles.items())),
    )

    # Setup tmux
    if not args.no_tmux:
        create_session(args.session_name, agent_dirs)
        logger.info(
            "Tmux session '{}' created. Attach with: tmux attach -t {}",
            args.session_name,
            args.session_name,
        )

    # Log each player's assigned role to their activity.log
    for name, agent_dir in agent_dirs.items():
        role = state.roles[name]
        log_to_agent(agent_dir, f"=== Role assigned: {role.upper()} ===")

    # Build facilitator
    facilitator = build_facilitator(args.facilitator_model)

    # Build persistent agents (one per player, for the entire game)
    agents = build_all_agents(state, agent_dirs)

    # Day 0: Mayor election
    await mayor_election_phase(
        state=state,
        agent_dirs=agent_dirs,
        agents=agents,
        facilitator=facilitator,
        mayor_rounds=args.mayor_rounds,
        session_name=args.session_name,
        use_llm_consensus=args.llm_consensus,
    )

    # Day 0: Diary
    logger.info("--- Day 0 Diary phase ---")
    await mayor_election_diary_phase(state, agent_dirs, agents)

    # Run game
    winner = await game_loop(
        state=state,
        agent_dirs=agent_dirs,
        agents=agents,
        facilitator=facilitator,
        mafia_rounds=args.mafia_rounds,
        day_rounds=args.day_rounds,
        session_name=args.session_name,
        use_llm_consensus=args.llm_consensus,
    )

    # Print results
    logger.info("=== GAME OVER ===")
    logger.info("Winner: {}", "Village" if winner == "village" else "Mafia")
    logger.info("Final roles:")
    for name in state.players:
        status = "ALIVE" if name in state.alive else "DEAD"
        logger.info("  {}: {} ({})", name, state.roles[name], status)

    for name in state.alive:
        log_to_agent(
            agent_dirs[name],
            f"=== GAME OVER - {'Village' if winner == 'village' else 'Mafia'} wins! ===",
        )

    # Post-game reflection: agents summarize, update knowledge, and write lessons learned
    await postgame_phase(state, agent_dirs, agents, winner)


if __name__ == "__main__":
    asyncio.run(main())
