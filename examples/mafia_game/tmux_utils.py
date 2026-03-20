"""Tmux session management for Mafia game observability."""

import os
import subprocess
from datetime import datetime
from pathlib import Path


def create_session(session_name: str, agent_dirs: dict[str, str]) -> None:
    """Create a tmux session with one window per agent + orchestrator.

    Args:
        session_name: Name for the tmux session.
        agent_dirs: Mapping of agent name -> agent directory path.
    """
    # Kill existing session if present
    subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
    )

    # Create session with orchestrator window
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session_name, "-n", "orchestrator"],
        check=True,
    )

    # Create one window per agent, tailing their activity log
    for name, agent_dir in agent_dirs.items():
        log_path = Path(agent_dir) / "activity.log"
        log_path.write_text("")  # Clear/create log file
        subprocess.run(
            ["tmux", "new-window", "-t", session_name, "-n", name],
            check=True,
        )
        subprocess.run(
            [
                "tmux",
                "send-keys",
                "-t",
                f"{session_name}:{name}",
                f"tail -f {log_path}",
                "Enter",
            ],
            check=True,
        )


def stream_to_agent(agent_dir: str, text: str) -> None:
    """Append raw text to agent's activity log without timestamp.

    Used for streaming LLM output character-by-character.

    Args:
        agent_dir: Path to the agent's directory.
        text: Raw text chunk to append.
    """
    log_path = Path(agent_dir) / "activity.log"
    with open(log_path, "a") as f:
        f.write(text)


def log_to_agent(agent_dir: str, message: str) -> None:
    """Append a timestamped message to an agent's activity log.

    Args:
        agent_dir: Path to the agent's directory.
        message: Message to log.
    """
    log_path = Path(agent_dir) / "activity.log"
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(log_path, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def log_to_orchestrator(session_name: str, message: str) -> None:
    """Send a message to the orchestrator tmux window.

    Args:
        session_name: Tmux session name.
        message: Message to display.
    """
    # Write to orchestrator pane
    subprocess.run(
        [
            "tmux",
            "send-keys",
            "-t",
            f"{session_name}:orchestrator",
            f"echo '{message}'",
            "Enter",
        ],
        capture_output=True,
    )


def mark_agent_dead(session_name: str, agent_name: str, agent_dir: str) -> None:
    """Mark an agent's window as dead.

    Args:
        session_name: Tmux session name.
        agent_name: Name of the eliminated agent.
        agent_dir: Path to the agent's directory.
    """
    log_to_agent(agent_dir, f"*** {agent_name} HAS BEEN ELIMINATED ***")
    # Rename the window to show dead status
    subprocess.run(
        [
            "tmux",
            "rename-window",
            "-t",
            f"{session_name}:{agent_name}",
            f"[DEAD] {agent_name}",
        ],
        capture_output=True,
    )
