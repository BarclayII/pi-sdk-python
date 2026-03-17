#!/usr/bin/env python3
"""
CLI for Exa semantic search.
Takes query and output directory, saves full content to markdown files and outputs metadata as JSON.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests


def load_env_file(env_path: str = ".env") -> None:
    """Load environment variables from .env file."""
    if not os.path.exists(env_path):
        return

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ[key] = val


def exa_search(
    query: str,
    result_dir: str,
    num_results: int = 20,
    start_published_date: Optional[str] = None,
    end_published_date: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute Exa API search and save results to markdown files.

    Args:
        query: Search query
        result_dir: Directory to save markdown files with full article content
        num_results: Number of results to return (default 20, max 100)
        start_published_date: ISO 8601 date string for start filter
        end_published_date: ISO 8601 date string for end filter
        api_key: Exa API key (uses EXA_API_KEY env var if not provided)

    Returns:
        Dictionary with search results including file paths

    Raises:
        ValueError: If API key is not available
        requests.RequestException: If API call fails
    """
    if not api_key:
        api_key = os.environ.get("EXA_API_KEY")

    if not api_key:
        raise ValueError("EXA_API_KEY not found in environment or .env file")

    payload = {
        "query": query,
        "numResults": num_results,
        "contents": {
            "text": True,
            "summary": {
                "query": "Summarize this article efficiently. Focus on: What happened? Who is involved? When? Where? Why/How?"
            },
        },
    }

    if start_published_date:
        payload["startPublishedDate"] = start_published_date
    if end_published_date:
        payload["endPublishedDate"] = end_published_date

    response = requests.post(
        "https://api.exa.ai/search",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if not response.ok:
        raise requests.RequestException(
            f"Exa API Error: {response.status_code} {response.reason} — {response.text}"
        )

    data = response.json()

    # Save full results to markdown files
    if data.get("results") and isinstance(data["results"], list):
        output_path = Path(result_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for index, result in enumerate(data["results"]):
            if result.get("text"):
                file_name = f"{index + 1}.md"
                file_path = output_path / file_name

                # Extract content and save to markdown (content only, no metadata)
                text = result.pop("text")
                file_path.write_text(text)

                # Add file path to result metadata for output
                result["content_file"] = str(file_path)

    return data


def format_output(data: dict[str, Any], pretty: bool = False) -> str:
    """Format output as JSON."""
    return json.dumps(data, indent=2 if pretty else None)


def main():
    parser = argparse.ArgumentParser(
        description="Search the web using Exa API (semantic search). Saves full article content to markdown files in result_dir.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "machine learning trends 2024" ./results
  %(prog)s "AI safety" ./results --num-results 10
  %(prog)s "climate change" ./results --start-date "2024-01-01T00:00:00Z"
  %(prog)s "quantum computing" ./results --pretty
        """,
    )

    parser.add_argument(
        "query",
        type=str,
        help="Search query",
    )

    parser.add_argument(
        "result_dir",
        type=str,
        help="Directory to save markdown files with full article content",
    )

    parser.add_argument(
        "--num-results",
        "-n",
        type=int,
        default=20,
        help="Number of results to return (default: 20, max: 100)",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="Only return results published after this date (ISO 8601, e.g., 2024-01-01T00:00:00Z)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="Only return results published before this date (ISO 8601)",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="Exa API key (uses EXA_API_KEY env var if not provided)",
    )

    parser.add_argument(
        "--pretty",
        "-p",
        action="store_true",
        help="Pretty-print JSON output",
    )

    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to .env file (default: .env)",
    )

    args = parser.parse_args()

    # Load environment variables from .env file
    if args.env_file:
        load_env_file(args.env_file)

    try:
        # Validate num_results
        if not 1 <= args.num_results <= 100:
            parser.error("--num-results must be between 1 and 100")

        # Execute search
        result = exa_search(
            query=args.query,
            result_dir=args.result_dir,
            num_results=args.num_results,
            start_published_date=args.start_date,
            end_published_date=args.end_date,
            api_key=args.api_key,
        )

        # Output results
        output = format_output(result, pretty=args.pretty)
        print(output)
        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"API Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
