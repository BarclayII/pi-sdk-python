---
name: exa-search
description: Semantic web search using the Exa API. Saves full article content to markdown files and returns structured metadata as JSON. Use when searching the web for information, articles, or URLs on a topic.
---

# Exa Search Skill

Semantic web search using the Exa API. Saves full article content to markdown files and returns structured metadata as JSON.

## Invocation

```
exa-search
```

## Arguments

| Argument      | Type    | Required | Description                                                            |
| ------------- | ------- | -------- | ---------------------------------------------------------------------- |
| `query`       | string  | Yes      | The search query to execute                                            |
| `result_dir`  | string  | Yes      | Directory path where markdown files with article content will be saved |
| `num_results` | integer | No       | Number of results to return (1-100, default: 20)                       |
| `start_date`  | string  | No       | ISO 8601 date string to filter results published after this date       |
| `end_date`    | string  | No       | ISO 8601 date string to filter results published before this date      |
| `api_key`     | string  | No       | Exa API key (uses EXA_API_KEY environment variable if not provided)    |
| `pretty`      | boolean | No       | Pretty-print JSON output (default: false)                              |

## Output

Returns JSON to stdout containing search results with metadata:

```json
{
  "requestId": "string",
  "resolvedSearchType": "string",
  "results": [
    {
      "id": "string",
      "title": "string",
      "url": "string",
      "publishedDate": "ISO 8601 string",
      "author": "string",
      "summary": "string",
      "content_file": "string (path to markdown file)"
    }
  ]
}
```

Full article content is saved to `result_dir` as numbered markdown files (1.md, 2.md, etc.).

## Setup

1. Get API key from https://exa.ai
2. Set `EXA_API_KEY` environment variable or create `.env` file with `EXA_API_KEY=your_key`
3. Install dependencies: `pip install requests python-dotenv`

## Examples

```bash
# Basic search
python example_skills/exa/exa_cli.py "machine learning" ./results

# With result limit
python example_skills/exa/exa_cli.py "AI safety" ./results --num-results 10

# With date filter
python example_skills/exa/exa_cli.py "climate change" ./results \
  --start-date "2024-01-01T00:00:00Z"

# Pretty-print output
python example_skills/exa/exa_cli.py "quantum computing" ./results --pretty
```
