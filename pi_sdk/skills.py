"""
Skills loader for pi-sdk-python.

Scans a skills directory for SKILL.md files, parses their frontmatter
for name and description, and generates an XML skill listing for the
system prompt.

Expected directory structure:
    <skills_dir>/
        <skill-name>/
            SKILL.md    # Must have YAML frontmatter with name and description
            ...         # Other files the skill may reference
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Extracts the YAML block between ``---`` delimiters and parses it
    with PyYAML.  Returns an empty dict if no valid frontmatter is found.
    """
    if not text.startswith("---"):
        return {}

    # Find the closing delimiter
    end = text.find("\n---", 3)
    if end == -1:
        return {}

    yaml_text = text[3:end]
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        logger.warning("Failed to parse YAML frontmatter: %s", e)
        return {}

    return parsed if isinstance(parsed, dict) else {}


def load_skills(skills_dir: str | Path) -> str:
    """Load skills from a directory and return an XML listing.

    Scans ``<skills_dir>/*/SKILL.md`` for frontmatter containing
    ``name`` and ``description`` fields. Returns an XML string suitable
    for appending to a system prompt.

    Args:
        skills_dir: Path to the root skills directory.

    Returns:
        An XML string listing discovered skills, or an empty string
        if the directory doesn't exist or contains no valid skills.
    """
    skills_path = Path(skills_dir).resolve()
    if not skills_path.is_dir():
        logger.warning("Skills directory does not exist: %s", skills_path)
        return ""

    skills: list[tuple[str, str, str]] = []  # (name, path, description)

    for skill_md in sorted(skills_path.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read %s: %s", skill_md, e)
            continue

        meta = _parse_frontmatter(text)
        name = meta.get("name", "")
        description = meta.get("description", "")

        if not name:
            logger.warning("SKILL.md missing 'name' field: %s", skill_md)
            continue

        skill_dir_path = str(skill_md.parent)
        skills.append((name, skill_dir_path, description))

    if not skills:
        return ""

    lines = [
        "You have the following skills. "
        "Read the SKILL.md inside a skill's path if its description matches your need.",
        "",
        "<skills>",
    ]
    for name, path, description in skills:
        lines.append("<skill>")
        lines.append(f"  <name>{name}</name>")
        lines.append(f"  <path>{path}</path>")
        lines.append(f"  <description>{description}</description>")
        lines.append("</skill>")
    lines.append("</skills>")

    return "\n".join(lines)
