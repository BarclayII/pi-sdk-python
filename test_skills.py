"""Tests for pi_sdk.skills."""

import tempfile
from pathlib import Path

from pi_sdk.skills import _parse_frontmatter, load_skills


class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        text = "---\nname: my-skill\ndescription: A cool skill\n---\n# Body"
        meta = _parse_frontmatter(text)
        assert meta["name"] == "my-skill"
        assert meta["description"] == "A cool skill"

    def test_no_frontmatter(self):
        assert _parse_frontmatter("# Just markdown") == {}

    def test_empty_string(self):
        assert _parse_frontmatter("") == {}

    def test_unclosed_frontmatter(self):
        assert _parse_frontmatter("---\nname: test\n") == {}

    def test_extra_fields_ignored(self):
        text = "---\nname: s\ndescription: d\nversion: 1\ntags: [a, b]\n---\n"
        meta = _parse_frontmatter(text)
        assert meta["name"] == "s"
        assert meta["description"] == "d"
        assert meta["version"] == 1
        assert meta["tags"] == ["a", "b"]

    def test_invalid_yaml(self):
        text = "---\n: bad: yaml:\n---\n"
        assert _parse_frontmatter(text) == {}

    def test_multiline_description(self):
        text = "---\nname: s\ndescription: |\n  line one\n  line two\n---\n"
        meta = _parse_frontmatter(text)
        assert "line one" in meta["description"]
        assert "line two" in meta["description"]


class TestLoadSkills:
    def test_nonexistent_dir(self):
        assert load_skills("/nonexistent/path") == ""

    def test_empty_dir(self, tmp_path):
        assert load_skills(tmp_path) == ""

    def test_single_skill(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Does things\n---\n# Body\n"
        )

        result = load_skills(tmp_path)
        assert "<skills>" in result
        assert "<name>my-skill</name>" in result
        assert "<description>Does things</description>" in result
        assert f"<path>{skill_dir}</path>" in result

    def test_multiple_skills_sorted(self, tmp_path):
        for name in ["beta-skill", "alpha-skill"]:
            d = tmp_path / name
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: desc-{name}\n---\n"
            )

        result = load_skills(tmp_path)
        alpha_pos = result.index("alpha-skill")
        beta_pos = result.index("beta-skill")
        assert alpha_pos < beta_pos

    def test_skips_missing_name(self, tmp_path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: no name field\n---\n")

        assert load_skills(tmp_path) == ""

    def test_skips_no_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "plain"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just markdown, no frontmatter\n")

        assert load_skills(tmp_path) == ""

    def test_mixed_valid_and_invalid(self, tmp_path):
        good = tmp_path / "good"
        good.mkdir()
        (good / "SKILL.md").write_text(
            "---\nname: good-skill\ndescription: works\n---\n"
        )

        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "SKILL.md").write_text("# no frontmatter\n")

        result = load_skills(tmp_path)
        assert "<name>good-skill</name>" in result
        assert "bad" not in result
