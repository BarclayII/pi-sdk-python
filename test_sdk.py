"""
Simple test to verify the SDK implementation.
"""

import asyncio
import sys
from pi_sdk.tools.truncate import truncate_head, truncate_tail, format_size
from pi_sdk.tools.path_utils import expand_path, resolve_to_cwd
from pi_sdk.tools.edit_diff import (
    detect_line_ending,
    normalize_to_lf,
    fuzzy_find_text,
    normalize_for_fuzzy_match,
    strip_bom,
)
from pi_sdk.tools.base import ToolSchema, ToolParameter


def test_truncate():
    """Test truncation utilities."""
    print("Testing truncate utilities...")

    # Test format_size
    assert format_size(100) == "100B"
    assert format_size(2000) == "2.0KB"
    print("  ✓ format_size works")

    # Test truncate_head
    content = "\n".join([f"Line {i}" for i in range(100)])
    result = truncate_head(content, max_lines=10, max_bytes=1000)
    assert result.line_count == 10
    assert result.was_truncated
    print("  ✓ truncate_head works")

    # Test truncate_tail
    result = truncate_tail(content, max_lines=10, max_bytes=1000)
    assert result.line_count == 10
    assert result.was_truncated
    print("  ✓ truncate_tail works")


def test_path_utils():
    """Test path utilities."""
    print("Testing path utilities...")

    # Test expand_path
    assert expand_path("test.txt") == "test.txt"
    assert expand_path("@test.txt") == "test.txt"
    expanded = expand_path("~")
    assert expanded.startswith("/")  # Should be expanded to absolute path
    print("  ✓ expand_path works")

    # Test resolve_to_cwd
    result = resolve_to_cwd("test.txt", "/tmp")
    assert result == "/tmp/test.txt"
    print("  ✓ resolve_to_cwd works")


def test_edit_diff():
    """Test edit diff utilities."""
    print("Testing edit diff utilities...")

    # Test line ending detection
    assert detect_line_ending("line1\nline2") == "\n"
    assert detect_line_ending("line1\r\nline2") == "\r\n"
    print("  ✓ detect_line_ending works")

    # Test normalization
    assert normalize_to_lf("line1\r\nline2\r") == "line1\nline2\n"
    print("  ✓ normalize_to_lf works")

    # Test fuzzy_find_text
    content = "Hello World\nThis is a test"
    result = fuzzy_find_text(content, "Hello World")
    assert result.found
    assert not result.is_fuzzy
    print("  ✓ fuzzy_find_text works")

    # Test strip_bom
    bom, content = strip_bom("\ufeffHello")
    assert bom == "\ufeff"
    assert content == "Hello"
    print("  ✓ strip_bom works")


def test_tool_schema():
    """Test tool schema."""
    print("Testing tool schema...")

    schema = ToolSchema(
        parameters=[
            ToolParameter(
                name="test",
                type="string",
                description="Test parameter",
            ),
        ]
    )

    json_schema = schema.to_openai_schema()
    assert json_schema["type"] == "object"
    assert "test" in json_schema["properties"]
    assert json_schema["properties"]["test"]["type"] == "string"
    print("  ✓ ToolSchema.to_openai_schema works")


def main():
    """Run all tests."""
    print("Running SDK tests...\n")

    try:
        test_truncate()
        test_path_utils()
        test_edit_diff()
        test_tool_schema()

        print("\n" + "=" * 50)
        print("All tests passed! ✓")
        print("=" * 50)
        return 0

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
