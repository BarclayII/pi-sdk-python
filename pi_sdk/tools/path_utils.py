"""
Path utilities for tool operations.

This module provides functions for handling file paths in tool operations.
"""

import os
from pathlib import Path
from typing import Union


def expand_path(path: Union[str, Path]) -> str:
    """Expand a path, handling ~ and @ prefixes.

    The @ prefix is used to reference files relative to the current working directory.

    Args:
        path: Path to expand

    Returns:
        Expanded path as string
    """
    path_str = str(path)

    # Handle @ prefix (relative to cwd)
    if path_str.startswith("@"):
        return path_str[1:]

    # Handle ~ expansion
    return os.path.expanduser(path_str)


def resolve_to_cwd(path: Union[str, Path], cwd: Union[str, Path]) -> str:
    """Resolve a path relative to a working directory.

    Args:
        path: Path to resolve (can be relative or absolute)
        cwd: Current working directory

    Returns:
        Resolved absolute path as string
    """
    cwd_path = Path(cwd).expanduser().resolve()
    path_str = expand_path(path)

    # If path is already absolute, return it
    if os.path.isabs(path_str):
        return path_str

    # Otherwise, resolve relative to cwd
    return str(cwd_path / path_str)
