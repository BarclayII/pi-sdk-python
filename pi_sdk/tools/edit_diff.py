"""
Diff and fuzzy matching utilities for the Edit tool.

This module provides functions for fuzzy text matching and generating diffs.
"""

import difflib
import re
from dataclasses import dataclass
from typing import Literal


# Normalization constants
SMART_QUOTE_MAP = {
    "\u2018": "'",  # '
    "\u2019": "'",  # '
    "\u201c": '"',  # "
    "\u201d": '"',  # "
    "\u2026": "...",  # ...
    "\u2013": "-",  # en dash
    "\u2014": "--",  # em dash
    "\u00a0": " ",  # non-breaking space
}


@dataclass
class FuzzyMatchResult:
    """Result of a fuzzy match operation."""

    found: bool
    match: str
    index: int
    is_fuzzy: bool


@dataclass
class DiffResult:
    """Result of a diff operation."""

    diff: str
    first_changed_line: int


def detect_line_ending(text: str) -> Literal["\n", "\r\n", "\r"]:
    """Detect the line ending style used in text.

    Args:
        text: Text to analyze

    Returns:
        The detected line ending ("\n", "\r\n", or "\r")
    """
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def normalize_to_lf(text: str) -> str:
    """Normalize all line endings to LF (\\n).

    Args:
        text: Text to normalize

    Returns:
        Text with LF line endings
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def restore_line_endings(text: str, ending: Literal["\n", "\r\n", "\r"]) -> str:
    """Restore line endings to the specified style.

    Args:
        text: Text with LF line endings
        ending: Line ending style to restore

    Returns:
        Text with specified line endings
    """
    if ending == "\r\n":
        return text.replace("\n", "\r\n")
    if ending == "\r":
        return text.replace("\n", "\r")
    return text


def _normalize_smart_quotes(text: str) -> str:
    """Normalize smart quotes and special characters.

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    result = text
    for smart_char, replacement in SMART_QUOTE_MAP.items():
        result = result.replace(smart_char, replacement)
    return result


def normalize_for_fuzzy_match(text: str) -> str:
    """Normalize text for fuzzy matching.

    This includes:
    - Normalizing line endings
    - Normalizing smart quotes and dashes
    - Trailing whitespace on each line

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    # Normalize line endings first
    text = normalize_to_lf(text)

    # Split into lines, strip trailing whitespace from each
    lines = text.split("\n")
    lines = [line.rstrip() for line in lines]

    # Normalize smart quotes
    text = "\n".join(lines)
    text = _normalize_smart_quotes(text)

    return text


def fuzzy_find_text(content: str, old_text: str) -> FuzzyMatchResult:
    """Find text in content, trying exact match first, then fuzzy match.

    Args:
        content: Content to search in
        old_text: Text to search for

    Returns:
        FuzzyMatchResult with match information
    """
    # Try exact match first
    index = content.find(old_text)
    if index != -1:
        return FuzzyMatchResult(
            found=True,
            match=old_text,
            index=index,
            is_fuzzy=False,
        )

    # Try fuzzy match (normalize both)
    normalized_content = normalize_for_fuzzy_match(content)
    normalized_old_text = normalize_for_fuzzy_match(old_text)

    index = normalized_content.find(normalized_old_text)
    if index != -1:
        # Find the actual match in original content
        # Get the text around the match position
        match_length = len(normalized_old_text)

        # Calculate line count to find actual position in original
        before_match = normalized_content[:index]
        line_count = before_match.count("\n")

        # Find the corresponding position in original content
        content_lines = content.splitlines(keepends=True)
        current_line = 0
        char_pos = 0

        for i, line in enumerate(content_lines):
            if current_line == line_count:
                # We're at the right line, add the column offset
                # Get column from normalized text
                normalized_before_line = before_match.split("\n")[-1]
                char_pos = (
                    len(line)
                    - len(line.lstrip())
                    + len(line.lstrip()[: len(normalized_before_line)])
                )
                break
            current_line += 1
            char_pos += len(line)

        # Extract the match from original content
        actual_match = content[
            char_pos : char_pos + match_length * 2
        ]  # Get extra to be safe
        # Trim to actual match length approximately
        actual_match = actual_match[: match_length + 100]

        return FuzzyMatchResult(
            found=True,
            match=actual_match,
            index=char_pos,
            is_fuzzy=True,
        )

    return FuzzyMatchResult(
        found=False,
        match="",
        index=-1,
        is_fuzzy=False,
    )


def strip_bom(content: str) -> tuple[str, str]:
    """Strip BOM (Byte Order Mark) from content.

    Args:
        content: Content to strip

    Returns:
        Tuple of (bom, stripped_content)
    """
    bom = ""
    if content.startswith("\ufeff"):
        bom = "\ufeff"
        content = content[1:]
    return bom, content


def generate_diff_string(old: str, new: str) -> DiffResult:
    """Generate a unified diff string between two texts.

    Args:
        old: Original text
        new: New text

    Returns:
        DiffResult with diff string and first changed line
    """
    # Normalize line endings for diff
    old_normalized = normalize_to_lf(old)
    new_normalized = normalize_to_lf(new)

    old_lines = old_normalized.splitlines(keepends=True)
    new_lines = new_normalized.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="original",
        tofile="modified",
        lineterm="",
    )

    diff_lines = list(diff)
    diff_text = "".join(diff_lines)

    # Find first changed line
    first_changed_line = 0
    for line in diff_lines:
        if line.startswith("@@"):
            # Parse hunk header to get first changed line
            match = re.search(r"-(\d+)", line)
            if match:
                first_changed_line = int(match.group(1))
            break

    return DiffResult(diff=diff_text, first_changed_line=first_changed_line)
