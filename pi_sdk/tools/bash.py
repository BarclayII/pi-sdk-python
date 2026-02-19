"""
Bash tool for executing shell commands.

This module provides the BashTool which executes shell commands.
"""

import asyncio
import os
import signal
import sys
from dataclasses import dataclass, field

from pi_sdk.tools.base import Tool, ToolParameter, ToolResult, ToolSchema
from pi_sdk.tools.truncate import truncate_tail


@dataclass
class BashTool(Tool):
    """Tool for executing shell commands."""

    name: str = "bash"
    description: str = (
        "Execute a shell command. "
        "Returns stdout and stderr. "
        "Use this for running commands, scripts, and build tools."
    )
    schema: ToolSchema = field(
        default_factory=lambda: ToolSchema(
            parameters=[
                ToolParameter(
                    name="command",
                    type="string",
                    description="The shell command to execute",
                ),
                ToolParameter(
                    name="timeout",
                    type="number",
                    description="Timeout in seconds (default: 120)",
                    required=False,
                ),
            ]
        )
    )
    cwd: str = "."

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, object],
    ) -> ToolResult:
        """Execute the bash command.

        Args:
            tool_call_id: ID of the tool call
            args: Tool arguments (command, timeout?)

        Returns:
            ToolResult with command output or error
        """
        command = args.get("command")
        timeout = args.get("timeout", 120.0)

        if not isinstance(command, str):
            return ToolResult(
                content="Error: command must be a string",
                is_error=True,
            )

        if not isinstance(timeout, (int, float)):
            return ToolResult(
                content="Error: timeout must be a number",
                is_error=True,
            )

        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            return ToolResult(
                content="Error: timeout must be a valid number",
                is_error=True,
            )

        try:
            # Create subprocess with process group for proper cleanup
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                # Create new process group for killing the entire tree
                preexec_fn=os.setsid if sys.platform != "win32" else None,
            )

            # Read output with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                # Kill the entire process group
                if sys.platform != "win32":
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
                    await process.wait()

                return ToolResult(
                    content=f"Error: Command timed out after {timeout} seconds",
                    is_error=True,
                )

            # Decode output
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # Combine stdout and stderr
            output = stdout_text
            if stderr_text:
                output += stderr_text if not output else "\n" + stderr_text

            # Add exit code if non-zero
            if process.returncode != 0:
                if output:
                    output += f"\n\nCommand exited with status {process.returncode}"
                else:
                    output = f"Command exited with status {process.returncode}"

            # Truncate if too large
            result = truncate_tail(output)
            return ToolResult(content=result.content)

        except FileNotFoundError:
            return ToolResult(
                content=f"Error: Shell not found or command not executable",
                is_error=True,
            )
        except PermissionError:
            return ToolResult(
                content=f"Error: Permission denied executing command",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                content=f"Error executing command: {e!s}",
                is_error=True,
            )
