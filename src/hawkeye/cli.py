"""CLI interface for Hawkeye."""

import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from . import __version__
from .analyzer import LogAnalyzer
from .watcher import LogWatcher
from .buffer import LogBuffer
from .filter import LogFilter
from . import output


app = typer.Typer(
    name="heye",
    help="Hawkeye - AI-powered log watcher",
    no_args_is_help=True,
)
console = Console()

# Global state for interactive mode
_watcher: LogWatcher | None = None
_buffer: LogBuffer | None = None


def version_callback(value: bool) -> None:
    if value:
        console.print(f"Hawkeye v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-v", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """Hawkeye - AI-powered log watcher that alerts you when something goes wrong."""
    pass


@app.command()
def watch(
    source: Annotated[
        str,
        typer.Argument(help="Log source: file path, '-' for stdin, or 'docker:container'"),
    ],
    docker: Annotated[
        Optional[str],
        typer.Option("--docker", "-d", help="Watch Docker container logs"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Only show issues, not all logs"),
    ] = False,
    no_analysis: Annotated[
        bool,
        typer.Option("--no-analysis", help="Skip LLM analysis, only pattern match"),
    ] = False,
    context: Annotated[
        int,
        typer.Option("--context", "-c", help="Lines of context around issues"),
    ] = 5,
    batch_window: Annotated[
        float,
        typer.Option("--batch-window", "-b", help="Seconds to batch issues"),
    ] = 10.0,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="OpenAI model to use"),
    ] = "gpt-4o-mini",
    api_key: Annotated[
        Optional[str],
        typer.Option("--api-key", envvar="OPENAI_API_KEY", help="OpenAI API key"),
    ] = None,
    base_url: Annotated[
        Optional[str],
        typer.Option("--base-url", envvar="OPENAI_BASE_URL", help="Custom API base URL"),
    ] = None,
) -> None:
    """Watch logs from a file, stdin, or Docker container."""
    global _watcher, _buffer

    # Set up analyzer
    analyzer = None
    if not no_analysis:
        if not api_key:
            output.print_error(
                "OPENAI_API_KEY not set. Use --api-key or set the environment variable.\n"
                "Use --no-analysis to run without LLM analysis."
            )
            raise typer.Exit(1)
        analyzer = LogAnalyzer(api_key=api_key, model=model, base_url=base_url)

    # Determine source type
    try:
        if docker:
            watcher = LogWatcher.from_docker(
                container=docker,
                analyzer=analyzer,
                context_lines=context,
                batch_window=batch_window,
                quiet=quiet,
                no_analysis=no_analysis,
            )
        elif source == "-":
            watcher = LogWatcher.from_stdin(
                analyzer=analyzer,
                context_lines=context,
                batch_window=batch_window,
                quiet=quiet,
                no_analysis=no_analysis,
            )
        elif source.startswith("docker:"):
            container = source[7:]
            watcher = LogWatcher.from_docker(
                container=container,
                analyzer=analyzer,
                context_lines=context,
                batch_window=batch_window,
                quiet=quiet,
                no_analysis=no_analysis,
            )
        else:
            path = Path(source)
            if not path.exists():
                output.print_error(f"File not found: {source}")
                raise typer.Exit(1)
            watcher = LogWatcher.from_file(
                path=path,
                analyzer=analyzer,
                context_lines=context,
                batch_window=batch_window,
                quiet=quiet,
                no_analysis=no_analysis,
            )

        _watcher = watcher
        _buffer = watcher.buffer
        asyncio.run(watcher.start())

    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def ask(
    query: Annotated[
        str,
        typer.Argument(help="Question to ask about the logs"),
    ],
    minutes: Annotated[
        int,
        typer.Option("--minutes", "-m", help="Look back this many minutes"),
    ] = 30,
    log_file: Annotated[
        Optional[str],
        typer.Option("--file", "-f", help="Log file to analyze"),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", help="OpenAI model to use"),
    ] = "gpt-4o-mini",
    api_key: Annotated[
        Optional[str],
        typer.Option("--api-key", envvar="OPENAI_API_KEY", help="OpenAI API key"),
    ] = None,
    base_url: Annotated[
        Optional[str],
        typer.Option("--base-url", envvar="OPENAI_BASE_URL", help="Custom API base URL"),
    ] = None,
) -> None:
    """Ask a question about recent logs."""
    if not api_key:
        output.print_error("OPENAI_API_KEY not set. Use --api-key or set the environment variable.")
        raise typer.Exit(1)

    analyzer = LogAnalyzer(api_key=api_key, model=model, base_url=base_url)
    buffer = LogBuffer()
    log_filter = LogFilter()

    # If a file is specified, read it first
    if log_file:
        path = Path(log_file)
        if not path.exists():
            output.print_error(f"File not found: {log_file}")
            raise typer.Exit(1)

        output.print_info(f"Reading {log_file}...")

        # Read the file and populate buffer
        from .sources.file import FileSource
        from .sources.base import LogLine
        from datetime import datetime

        with open(path, "r") as f:
            for line in f:
                line = line.rstrip("\n")
                log_line = LogLine(
                    content=line,
                    timestamp=datetime.now(),
                    source=str(path),
                )
                result = log_filter.check(line)
                buffer.add_line(log_line, result)

    # If we have an active watcher, use its buffer
    elif _buffer is not None:
        buffer = _buffer
    else:
        output.print_error("No log data. Either specify --file or run 'heye watch' first.")
        raise typer.Exit(1)

    # Get summary and ask
    summary = buffer.get_summary(minutes)
    recent_issues = buffer.get_recent_issues(minutes)
    recent_logs = buffer.get_recent_logs(minutes)
    log_sample = [line.content for line in recent_logs]

    async def do_query():
        result = await analyzer.answer_query(
            query=query,
            recent_issues=recent_issues,
            recent_log_sample=log_sample,
            summary=summary,
        )
        output.print_query_result(result)

    try:
        asyncio.run(do_query())
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def status(
    minutes: Annotated[
        int,
        typer.Option("--minutes", "-m", help="Look back this many minutes"),
    ] = 30,
    log_file: Annotated[
        Optional[str],
        typer.Option("--file", "-f", help="Log file to analyze"),
    ] = None,
) -> None:
    """Show status summary of recent log activity."""
    buffer = LogBuffer()
    log_filter = LogFilter()

    # If a file is specified, read it
    if log_file:
        path = Path(log_file)
        if not path.exists():
            output.print_error(f"File not found: {log_file}")
            raise typer.Exit(1)

        from .sources.base import LogLine
        from datetime import datetime

        with open(path, "r") as f:
            for line in f:
                line = line.rstrip("\n")
                log_line = LogLine(
                    content=line,
                    timestamp=datetime.now(),
                    source=str(path),
                )
                result = log_filter.check(line)
                buffer.add_line(log_line, result)

    elif _buffer is not None:
        buffer = _buffer
    else:
        output.print_error("No log data. Either specify --file or run 'heye watch' first.")
        raise typer.Exit(1)

    summary = buffer.get_summary(minutes)
    output.print_status_summary(summary)


if __name__ == "__main__":
    app()
