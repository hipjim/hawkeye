# Hawkeye

AI-powered log watcher that alerts you when something goes wrong.

Hawkeye watches your logs in real-time, detects issues using smart pattern matching, and uses OpenAI to analyze problems and suggest fixes. It only calls the LLM when something looks suspicious, keeping costs low.

## Features

- **Smart filtering** - Only calls OpenAI when issues are detected (errors, exceptions, 5xx, timeouts, etc.)
- **Multiple sources** - Watch log files, stdin (piped logs), or Docker containers
- **Batching** - Groups related issues before analysis to reduce API calls and provide better context
- **Interactive queries** - Ask questions like "any issues in the last hour?" or "is the system healthy?"
- **Rich terminal UI** - Color-coded alerts and formatted analysis results

## Installation

```bash
pip install hawkeye-log
```

Or install from source:

```bash
git clone https://github.com/yourusername/hawkeye.git
cd hawkeye
pip install -e .
```

## Quick Start

```bash
# Set your OpenAI API key
export OPENAI_API_KEY=your-key-here

# Watch a log file
heye watch /var/log/app.log

# Watch without LLM analysis (pattern matching only)
heye watch /var/log/app.log --no-analysis
```

## Usage

### Watch logs

```bash
# Watch a file
heye watch /var/log/app.log

# Watch stdin (pipe from another command)
tail -f /var/log/syslog | heye watch -
kubectl logs -f my-pod | heye watch -

# Watch a Docker container
heye watch docker:container-name

# Quiet mode - only show issues, not all log lines
heye watch /var/log/app.log --quiet

# Skip LLM analysis, only do pattern matching
heye watch /var/log/app.log --no-analysis
```

### Ask questions

```bash
# Ask about a log file
heye ask "any critical issues in the last hour?" --file /var/log/app.log

# Ask about recent issues
heye ask "is the database connection stable?" --file /var/log/app.log

# Look back further
heye ask "any patterns in the errors?" --file /var/log/app.log --minutes 60
```

### Status summary

```bash
# Get a quick summary of issues
heye status --file /var/log/app.log
```

## Options

### `heye watch`

| Option | Description |
|--------|-------------|
| `--quiet, -q` | Only show issues, not all log lines |
| `--no-analysis` | Skip LLM analysis, only pattern match |
| `--context, -c` | Lines of context around issues (default: 5) |
| `--batch-window, -b` | Seconds to batch issues before analysis (default: 10) |
| `--model, -m` | OpenAI model to use (default: gpt-4o-mini) |
| `--api-key` | OpenAI API key (or set `OPENAI_API_KEY`) |
| `--base-url` | Custom API base URL (for API-compatible services) |

### `heye ask`

| Option | Description |
|--------|-------------|
| `--file, -f` | Log file to analyze |
| `--minutes, -m` | Look back this many minutes (default: 30) |
| `--model` | OpenAI model to use (default: gpt-4o-mini) |

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Log Source    │────▶│   Pre-filter    │────▶│     Buffer      │
│ file/stdin/docker│     │ pattern matching │     │  batch issues   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Terminal UI    │◀────│    Analysis     │◀────│  OpenAI API     │
│  rich alerts    │     │  (if issues)    │     │  (only when needed)
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

1. **Log Source** - Reads logs from files (tail -f style), stdin, or Docker containers
2. **Pre-filter** - Pattern matches for errors, warnings, exceptions, HTTP 5xx, etc.
3. **Buffer** - Collects issues with context lines, batches them over a time window
4. **OpenAI API** - Only called when issues are detected, analyzes batches for root cause
5. **Terminal UI** - Displays color-coded alerts and formatted analysis

## Detected Patterns

Hawkeye looks for these patterns (case-insensitive):

**Errors:**
- `error`, `fail`, `exception`, `critical`, `fatal`
- `panic`, `crash`, `timeout`, `refused`, `denied`
- `unauthorized`, `forbidden`, `invalid`, `corrupt`
- `out of memory`, `oom`, `segfault`, `abort`
- HTTP 5xx status codes, stack traces

**Warnings:**
- `warn`, `warning`, `deprecated`, `retry`
- `slow`, `latency`, `delayed`, `throttle`
- `high cpu`, `high memory`, `low disk`

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `OPENAI_BASE_URL` | Custom API base URL (optional) |

### Using with other LLM providers

Hawkeye works with any OpenAI-compatible API:

```bash
# Use with a local LLM
heye watch /var/log/app.log --base-url http://localhost:8000/v1

# Use with Azure OpenAI
export OPENAI_API_KEY=your-azure-key
export OPENAI_BASE_URL=https://your-resource.openai.azure.com
heye watch /var/log/app.log
```

## Examples

### Watching Kubernetes pods

```bash
kubectl logs -f deployment/my-app | heye watch -
```

### Watching multiple Docker containers

```bash
docker compose logs -f | heye watch -
```

### CI/CD integration

```bash
# Run tests and analyze failures
pytest 2>&1 | heye watch - --no-analysis

# Check build logs
heye ask "what caused the build to fail?" --file build.log
```

## License

MIT

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
