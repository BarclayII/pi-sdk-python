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
from console_client import ConsoleClient
from event_bus import EventBus
from events import (
    GameResult,
    GameStart,
    RoleAssigned,
    RoundStart,
    player_channel,
)
from game_state import GameState
from i18n import set_lang
from orchestrator import (
    day_phase,
    diary_phase,
    mayor_election_diary_phase,
    mayor_election_phase,
    night_phase,
    postgame_phase,
)

from loguru import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mafia Game - Multi-Agent LLM")
    parser.add_argument(
        "agent_dirs",
        nargs="+",
        help="Paths to agent directories (each with PERSONALITY.md and MODEL.txt)",
    )
    parser.add_argument(
        "--lang",
        default="en",
        choices=["en", "cn"],
        help="Game language: en (English) or cn (Chinese/中文) (default: en)",
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
        "--facilitator-model",
        default=None,
        help="Model for facilitator agent (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--llm-consensus",
        action="store_true",
        help="Use LLM facilitator for consensus detection in addition to eagerness-based consensus",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level for debug/warnings (default: WARNING)",
    )
    return parser.parse_args()


async def game_loop(
    state: GameState,
    agent_dirs: dict[str, str],
    agents: dict[str, Agent],
    facilitator,
    mafia_rounds: int,
    day_rounds: int,
    bus: EventBus,
    use_llm_consensus: bool = False,
) -> str:
    """Main game loop. Returns winner: 'village' or 'mafia'."""

    while True:
        state.round_id += 1
        bus.emit(RoundStart(round_id=state.round_id))

        killed, poisoned = await night_phase(
            state,
            agent_dirs,
            agents,
            facilitator,
            mafia_rounds,
            bus,
            use_llm_consensus=use_llm_consensus,
        )

        eliminated, day_transcript_lines = await day_phase(
            state,
            agent_dirs,
            agents,
            facilitator,
            day_rounds,
            killed,
            poisoned,
            bus,
            use_llm_consensus=use_llm_consensus,
        )

        winner = state.check_win()
        if winner:
            return winner

        await diary_phase(state, agent_dirs, agents, day_transcript_lines, bus)


async def main():
    load_dotenv()
    args = parse_args()

    set_lang(args.lang)

    logger.remove()
    logger.add(sys.stderr, level=args.log_level)

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

    state = GameState(
        players=list(agent_dirs.keys()),
        data_dir=str(Path(args.data_dir).resolve()),
    )
    state.assign_roles()

    bus = EventBus()
    bus.add_client(ConsoleClient())
    await bus.start()

    try:
        bus.emit(GameStart(players=list(state.players), roles=dict(state.roles)))
        for name, role in sorted(state.roles.items()):
            bus.emit(
                RoleAssigned(
                    channel=player_channel(name),
                    player=name,
                    role=role,
                )
            )

        facilitator = build_facilitator(args.facilitator_model)
        agents = build_all_agents(state, agent_dirs)

        await mayor_election_phase(
            state=state,
            agent_dirs=agent_dirs,
            agents=agents,
            facilitator=facilitator,
            mayor_rounds=args.mayor_rounds,
            bus=bus,
            use_llm_consensus=args.llm_consensus,
        )

        await mayor_election_diary_phase(state, agent_dirs, agents, bus)

        winner = await game_loop(
            state=state,
            agent_dirs=agent_dirs,
            agents=agents,
            facilitator=facilitator,
            mafia_rounds=args.mafia_rounds,
            day_rounds=args.day_rounds,
            bus=bus,
            use_llm_consensus=args.llm_consensus,
        )

        bus.emit(
            GameResult(
                winner=winner,
                final_roles=dict(state.roles),
                alive=sorted(state.alive),
            )
        )

        await postgame_phase(state, agent_dirs, agents, winner, bus)
    finally:
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
