"""Main log watcher that coordinates all components."""

import asyncio
from pathlib import Path

from .sources.base import LogSource
from .sources.file import FileSource
from .sources.stdin import StdinSource
from .sources.docker import DockerSource
from .filter import LogFilter, FilterConfig
from .buffer import LogBuffer
from .analyzer import LogAnalyzer
from . import output


class LogWatcher:
    """Main log watcher that coordinates sources, filtering, and analysis."""

    def __init__(
        self,
        source: LogSource,
        analyzer: LogAnalyzer | None = None,
        filter_config: FilterConfig | None = None,
        context_lines: int = 5,
        batch_window: float = 10.0,
        quiet: bool = False,
        no_analysis: bool = False,
    ):
        """
        Initialize the log watcher.

        Args:
            source: Log source to watch
            analyzer: OpenAI analyzer (optional if no_analysis=True)
            filter_config: Custom filter configuration
            context_lines: Lines of context around issues
            batch_window: Seconds to batch issues before analysis
            quiet: Only show issues, not all logs
            no_analysis: Skip LLM analysis, only do pattern matching
        """
        self.source = source
        self.analyzer = analyzer
        self.filter = LogFilter(filter_config)
        self.buffer = LogBuffer(
            context_lines=context_lines,
            batch_window_seconds=batch_window,
        )
        self.quiet = quiet
        self.no_analysis = no_analysis
        self._running = False

    @classmethod
    def from_file(cls, path: str | Path, **kwargs) -> "LogWatcher":
        """Create a watcher for a file."""
        source = FileSource(path)
        return cls(source=source, **kwargs)

    @classmethod
    def from_stdin(cls, **kwargs) -> "LogWatcher":
        """Create a watcher for stdin."""
        source = StdinSource()
        return cls(source=source, **kwargs)

    @classmethod
    def from_docker(cls, container: str, tail: int = 0, **kwargs) -> "LogWatcher":
        """Create a watcher for a Docker container."""
        source = DockerSource(container, tail=tail)
        return cls(source=source, **kwargs)

    async def start(self) -> None:
        """Start watching logs."""
        self._running = True
        output.print_startup(self.source.name)

        # Start the batch processor
        batch_task = asyncio.create_task(self._process_batches())

        try:
            async for line in self.source.stream():
                if not self._running:
                    break

                # Filter the line
                result = self.filter.check(line.content)

                # Add to buffer
                self.buffer.add_line(line, result)

                # Output based on settings
                if result.should_analyze:
                    output.print_issue_detected(
                        line.content, result.severity, result.matched_pattern
                    )
                elif not self.quiet:
                    output.print_log_line(line.content, result.severity)

        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            batch_task.cancel()
            await self.source.close()

            # Flush any remaining batch
            final_batch = self.buffer.force_flush(self.source.name)
            if final_batch and self.analyzer and not self.no_analysis:
                analysis = await self.analyzer.analyze_batch(final_batch)
                output.print_analysis(analysis)

    async def _process_batches(self) -> None:
        """Background task to process batches when ready."""
        while self._running:
            await asyncio.sleep(1.0)  # Check every second

            batch = self.buffer.get_batch_if_ready(self.source.name)
            if batch and self.analyzer and not self.no_analysis:
                try:
                    analysis = await self.analyzer.analyze_batch(batch)
                    output.print_analysis(analysis)
                except Exception as e:
                    output.print_error(f"Analysis failed: {e}")

    async def ask(self, query: str, minutes: int = 30) -> None:
        """Answer a query about recent logs."""
        if not self.analyzer:
            output.print_error("Analyzer not configured. Set OPENAI_API_KEY.")
            return

        summary = self.buffer.get_summary(minutes)
        recent_issues = self.buffer.get_recent_issues(minutes)
        recent_logs = self.buffer.get_recent_logs(minutes)
        log_sample = [line.content for line in recent_logs]

        try:
            result = await self.analyzer.answer_query(
                query=query,
                recent_issues=recent_issues,
                recent_log_sample=log_sample,
                summary=summary,
            )
            output.print_query_result(result)
        except Exception as e:
            output.print_error(f"Query failed: {e}")

    def status(self, minutes: int = 30) -> None:
        """Print current status summary."""
        summary = self.buffer.get_summary(minutes)
        output.print_status_summary(summary)

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
