# Exa Search CLI

A command-line interface for semantic web search using the Exa API.

## Installation

The CLI requires `requests` library. Install it via:

```bash
pip install requests python-dotenv
```

Or using uv:

```bash
uv pip install requests python-dotenv
```

## Setup

1. Get an API key from [Exa API](https://exa.ai)
2. Create a `.env` file in the project root with:

```
EXA_API_KEY=your_api_key_here
```

Or export it as an environment variable:

```bash
export EXA_API_KEY=your_api_key_here
```

## Usage

### Basic search

```bash
python example_skills/exa/exa_cli.py "machine learning trends 2024" ./results
```

### Search with result limit

```bash
python example_skills/exa/exa_cli.py "AI safety" ./results --num-results 10
```

### Search with date filters

```bash
python example_skills/exa/exa_cli.py "climate change" ./results \
  --start-date "2024-01-01T00:00:00Z" \
  --end-date "2024-12-31T23:59:59Z"
```

### Pretty-print JSON output

```bash
python example_skills/exa/exa_cli.py "quantum computing" ./results --pretty
```

### Use custom .env file

```bash
python example_skills/exa/exa_cli.py "your query" ./results --env-file /path/to/.env
```

### Pass API key directly

```bash
python example_skills/exa/exa_cli.py "your query" ./results --api-key YOUR_API_KEY
```

## Output

Results are returned as JSON to stdout and include:

- **results**: Array of search result objects
  - **title**: Result title
  - **url**: Result URL
  - **publishedDate**: Publication date
  - **author**: Author information (if available)
  - **content_file**: Path to the markdown file containing full article content
  - Other metadata fields from the API

Full article content is saved to the specified result directory as numbered markdown files (1.md, 2.md, etc.):

```
./results/
├── 1.md
├── 2.md
├── 3.md
└── ...
```

Each markdown file contains only the article text content (no title or metadata).

## API Arguments Reference

| Argument        | Short | Type   | Description                                 |
| --------------- | ----- | ------ | ------------------------------------------- |
| `query`         | -     | string | Search query (required)                     |
| `result_dir`    | -     | string | Directory to save markdown files (required) |
| `--num-results` | `-n`  | int    | Number of results (1-100, default 20)       |
| `--start-date`  | -     | string | Start date filter (ISO 8601)                |
| `--end-date`    | -     | string | End date filter (ISO 8601)                  |
| `--api-key`     | -     | string | Exa API key (overrides EXA_API_KEY env)     |
| `--pretty`      | `-p`  | flag   | Pretty-print JSON output                    |
| `--env-file`    | -     | string | Path to .env file (default: .env)           |

## Examples

### Search and save results

```bash
python example_skills/exa/exa_cli.py "Python async programming" ./results --num-results 5 --pretty
```

### Recent news search

```bash
python example_skills/exa/exa_cli.py "breaking news" ./results \
  --start-date "2024-03-10T00:00:00Z" \
  --pretty
```

### Export results to file

```bash
python example_skills/exa/exa_cli.py "your query" ./results > results.json
```

## Error Handling

The CLI returns appropriate exit codes:

- `0`: Success
- `1`: Error (invalid arguments, API errors, missing API key)

Error messages are written to stderr with details about what went wrong.

## Integration with Skills

This CLI can be used as a skill that provides web search functionality to AI agents. The structured output makes it easy to parse results programmatically.
