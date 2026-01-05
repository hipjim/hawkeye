"""Terminal output and alerts using rich."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .analyzer import AnalysisResult, QueryResult
from .buffer import IssueBatch


console = Console()


SEVERITY_STYLES = {
    "critical": ("bold white on red", "[!!!]"),
    "high": ("bold red", "[!!]"),
    "medium": ("yellow", "[!]"),
    "low": ("blue", "[i]"),
    "error": ("bold red", "[ERR]"),
    "warning": ("yellow", "[WRN]"),
    "info": ("dim", "[INF]"),
}

HEALTH_STYLES = {
    "healthy": ("bold green", "HEALTHY"),
    "degraded": ("bold yellow", "DEGRADED"),
    "unhealthy": ("bold red", "UNHEALTHY"),
    "unknown": ("dim", "UNKNOWN"),
}


def print_startup(source: str) -> None:
    """Print startup message."""
    console.print()
    console.print(
        Panel(
            f"[bold cyan]Hawkeye[/bold cyan] is watching [green]{source}[/green]\n"
            "[dim]Press Ctrl+C to stop[/dim]",
            box=box.ROUNDED,
            border_style="cyan",
        )
    )
    console.print()


def print_log_line(line: str, severity: str = "info") -> None:
    """Print a log line with appropriate styling."""
    style, prefix = SEVERITY_STYLES.get(severity, ("dim", ""))
    if severity in ("error", "warning"):
        console.print(f"{prefix} {line}", style=style)
    else:
        console.print(f"[dim]{line}[/dim]")


def print_issue_detected(line: str, severity: str, pattern: str | None) -> None:
    """Print when an issue is detected."""
    style, prefix = SEVERITY_STYLES.get(severity, ("yellow", "[!]"))
    console.print(f"\n{prefix} Issue detected", style=style)
    console.print(f"  {line}")
    if pattern:
        console.print(f"  [dim]Matched: {pattern}[/dim]")


def print_analysis(result: AnalysisResult) -> None:
    """Print analysis results."""
    style, prefix = SEVERITY_STYLES.get(result.severity, ("yellow", "[!]"))

    console.print()
    panel_content = Text()
    panel_content.append(f"{prefix} ", style=style)
    panel_content.append(result.summary)

    if result.root_cause:
        panel_content.append(f"\n\nRoot cause: ", style="bold")
        panel_content.append(result.root_cause)

    if result.affected_components:
        panel_content.append(f"\n\nAffected: ", style="bold")
        panel_content.append(", ".join(result.affected_components))

    if result.suggested_actions:
        panel_content.append(f"\n\nSuggested actions:", style="bold")
        for action in result.suggested_actions:
            panel_content.append(f"\n  - {action}")

    console.print(
        Panel(
            panel_content,
            title="[bold]Analysis[/bold]",
            border_style=style.split()[-1] if " " in style else style,
            box=box.ROUNDED,
        )
    )
    console.print()


def print_query_result(result: QueryResult) -> None:
    """Print query response."""
    health_style, health_text = HEALTH_STYLES.get(
        result.health_status, ("dim", "UNKNOWN")
    )

    console.print()

    # Health status header
    console.print(f"Status: [{health_style}]{health_text}[/{health_style}]")
    console.print()

    # Answer
    console.print(Panel(result.answer, title="[bold]Answer[/bold]", box=box.ROUNDED))

    if result.issues_found > 0:
        console.print(f"\n[yellow]Issues found: {result.issues_found}[/yellow]")

    if result.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in result.recommendations:
            console.print(f"  - {rec}")

    console.print()


def print_status_summary(summary: dict) -> None:
    """Print a status summary."""
    table = Table(title="Status Summary", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Time Range", f"Last {summary['time_range_minutes']} minutes")
    table.add_row("Log Lines", str(summary["total_log_lines"]))
    table.add_row("Total Issues", str(summary["total_issues"]))

    error_style = "red" if summary["error_count"] > 0 else "green"
    table.add_row("Errors", f"[{error_style}]{summary['error_count']}[/{error_style}]")

    warn_style = "yellow" if summary["warning_count"] > 0 else "green"
    table.add_row("Warnings", f"[{warn_style}]{summary['warning_count']}[/{warn_style}]")

    console.print()
    console.print(table)
    console.print()


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[cyan]{message}[/cyan]")


def print_waiting() -> None:
    """Print waiting indicator."""
    console.print("[dim]Waiting for logs...[/dim]")
