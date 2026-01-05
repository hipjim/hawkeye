"""Log buffer for batching and maintaining rolling window."""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .sources.base import LogLine
from .filter import FilterResult


@dataclass
class BufferedIssue:
    """A detected issue with context."""

    trigger_line: LogLine
    filter_result: FilterResult
    context_before: list[LogLine]
    context_after: list[LogLine]
    timestamp: datetime = field(default_factory=datetime.now)

    def format_for_analysis(self) -> str:
        """Format the issue for LLM analysis."""
        lines = []

        if self.context_before:
            lines.append("--- Context (before) ---")
            for line in self.context_before:
                lines.append(f"  {line.content}")

        lines.append(f">>> [{self.filter_result.severity.upper()}] {self.trigger_line.content}")

        if self.context_after:
            lines.append("--- Context (after) ---")
            for line in self.context_after:
                lines.append(f"  {line.content}")

        return "\n".join(lines)


@dataclass
class IssueBatch:
    """A batch of issues to send for analysis."""

    issues: list[BufferedIssue]
    source: str
    start_time: datetime
    end_time: datetime

    def format_for_analysis(self) -> str:
        """Format the entire batch for LLM analysis."""
        parts = [
            f"Log source: {self.source}",
            f"Time range: {self.start_time.isoformat()} to {self.end_time.isoformat()}",
            f"Issues detected: {len(self.issues)}",
            "",
        ]

        for i, issue in enumerate(self.issues, 1):
            parts.append(f"=== Issue {i} ===")
            parts.append(issue.format_for_analysis())
            parts.append("")

        return "\n".join(parts)


class LogBuffer:
    """Buffer for collecting logs and batching issues."""

    def __init__(
        self,
        context_lines: int = 5,
        batch_window_seconds: float = 10.0,
        history_minutes: int = 60,
        max_history_lines: int = 10000,
    ):
        """
        Initialize the log buffer.

        Args:
            context_lines: Number of lines to keep before/after an issue
            batch_window_seconds: Time window for batching issues
            history_minutes: How long to keep log history (for queries)
            max_history_lines: Maximum lines to keep in history
        """
        self.context_lines = context_lines
        self.batch_window_seconds = batch_window_seconds
        self.history_minutes = history_minutes
        self.max_history_lines = max_history_lines

        # Rolling context buffer (recent lines for context)
        self._context_buffer: deque[LogLine] = deque(maxlen=context_lines)

        # Pending issues waiting for context_after
        self._pending_issues: list[tuple[BufferedIssue, int]] = []  # (issue, lines_needed)

        # Current batch of complete issues
        self._current_batch: list[BufferedIssue] = []
        self._batch_start_time: datetime | None = None

        # Full history for queries
        self._history: deque[LogLine] = deque(maxlen=max_history_lines)
        self._issue_history: deque[BufferedIssue] = deque(maxlen=1000)

        # Batch ready callback
        self._batch_ready_event = asyncio.Event()

    def add_line(
        self,
        line: LogLine,
        filter_result: FilterResult,
    ) -> None:
        """Add a log line to the buffer."""
        # Add to history
        self._history.append(line)

        # Process pending issues (add context_after)
        still_pending = []
        for issue, lines_needed in self._pending_issues:
            if lines_needed > 0:
                issue.context_after.append(line)
                lines_needed -= 1
            if lines_needed > 0:
                still_pending.append((issue, lines_needed))
            else:
                # Issue is complete, add to batch
                self._add_to_batch(issue)
        self._pending_issues = still_pending

        # If this line is an issue, create a new buffered issue
        if filter_result.should_analyze:
            issue = BufferedIssue(
                trigger_line=line,
                filter_result=filter_result,
                context_before=list(self._context_buffer),
                context_after=[],
            )
            # Queue for context_after collection
            self._pending_issues.append((issue, self.context_lines))

        # Add to context buffer
        self._context_buffer.append(line)

    def _add_to_batch(self, issue: BufferedIssue) -> None:
        """Add a complete issue to the current batch."""
        if self._batch_start_time is None:
            self._batch_start_time = datetime.now()

        self._current_batch.append(issue)
        self._issue_history.append(issue)

    def get_batch_if_ready(self, source: str) -> IssueBatch | None:
        """
        Get the current batch if the time window has elapsed.

        Returns None if no batch is ready.
        """
        if not self._current_batch:
            return None

        if self._batch_start_time is None:
            return None

        elapsed = (datetime.now() - self._batch_start_time).total_seconds()
        if elapsed < self.batch_window_seconds:
            return None

        # Batch is ready
        batch = IssueBatch(
            issues=self._current_batch,
            source=source,
            start_time=self._batch_start_time,
            end_time=datetime.now(),
        )

        # Reset batch state
        self._current_batch = []
        self._batch_start_time = None

        return batch

    def force_flush(self, source: str) -> IssueBatch | None:
        """Force flush the current batch regardless of time window."""
        # First, complete any pending issues without waiting for more context
        for issue, _ in self._pending_issues:
            self._add_to_batch(issue)
        self._pending_issues = []

        if not self._current_batch:
            return None

        batch = IssueBatch(
            issues=self._current_batch,
            source=source,
            start_time=self._batch_start_time or datetime.now(),
            end_time=datetime.now(),
        )

        self._current_batch = []
        self._batch_start_time = None

        return batch

    def get_recent_logs(self, minutes: int = 30) -> list[LogLine]:
        """Get logs from the last N minutes."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [line for line in self._history if line.timestamp >= cutoff]

    def get_recent_issues(self, minutes: int = 30) -> list[BufferedIssue]:
        """Get issues from the last N minutes."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [issue for issue in self._issue_history if issue.timestamp >= cutoff]

    def get_summary(self, minutes: int = 30) -> dict:
        """Get a summary of recent activity."""
        recent_logs = self.get_recent_logs(minutes)
        recent_issues = self.get_recent_issues(minutes)

        error_count = sum(1 for i in recent_issues if i.filter_result.severity == "error")
        warning_count = sum(1 for i in recent_issues if i.filter_result.severity == "warning")

        return {
            "time_range_minutes": minutes,
            "total_log_lines": len(recent_logs),
            "total_issues": len(recent_issues),
            "error_count": error_count,
            "warning_count": warning_count,
            "issues": recent_issues,
        }
