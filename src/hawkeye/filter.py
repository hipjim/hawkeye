"""Pre-filter for detecting potential issues in logs before sending to LLM."""

import re
from dataclasses import dataclass, field


@dataclass
class FilterConfig:
    """Configuration for log filtering."""

    # Error patterns (case-insensitive)
    error_patterns: list[str] = field(
        default_factory=lambda: [
            r"\berror\b",
            r"\bfail(ed|ure|ing)?\b",
            r"\bexception\b",
            r"\bcritical\b",
            r"\bfatal\b",
            r"\bpanic\b",
            r"\bcrash(ed|ing)?\b",
            r"\btimeout\b",
            r"\brefused\b",
            r"\bdenied\b",
            r"\bunauthorized\b",
            r"\bforbidden\b",
            r"\binvalid\b",
            r"\bcorrupt(ed|ion)?\b",
            r"\bout of memory\b",
            r"\boom\b",
            r"\bkill(ed|ing)?\b",
            r"\bsegfault\b",
            r"\bsegmentation fault\b",
            r"\babort(ed|ing)?\b",
            r"\bnot found\b",
            r"\b404\b",
            r"\b50[0-9]\b",  # HTTP 5xx errors
            r"\btraceback\b",
            r"\bstack\s*trace\b",
        ]
    )

    # Warning patterns (case-insensitive)
    warning_patterns: list[str] = field(
        default_factory=lambda: [
            r"\bwarn(ing)?\b",
            r"\bdeprecated\b",
            r"\bretry(ing)?\b",
            r"\breconnect(ing)?\b",
            r"\bslow\b",
            r"\blatency\b",
            r"\bdelayed?\b",
            r"\bbackoff\b",
            r"\bthrottle[d]?\b",
            r"\brate.?limit\b",
            r"\bhigh.?(cpu|memory|load)\b",
            r"\blow.?(disk|space|memory)\b",
        ]
    )

    # Patterns to ignore (reduce noise)
    ignore_patterns: list[str] = field(
        default_factory=lambda: [
            r"^$",  # Empty lines
            r"^\s*#",  # Comments
            r"health.?check",
            r"readiness.?probe",
            r"liveness.?probe",
        ]
    )

    # Minimum severity to report (error, warning, info)
    min_severity: str = "warning"


@dataclass
class FilterResult:
    """Result of filtering a log line."""

    should_analyze: bool
    severity: str  # "error", "warning", "info"
    matched_pattern: str | None = None


class LogFilter:
    """Filter log lines to detect potential issues."""

    def __init__(self, config: FilterConfig | None = None):
        self.config = config or FilterConfig()
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficiency."""
        self._error_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config.error_patterns
        ]
        self._warning_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config.warning_patterns
        ]
        self._ignore_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config.ignore_patterns
        ]

    def check(self, line: str) -> FilterResult:
        """
        Check if a log line indicates a potential issue.

        Returns FilterResult with severity and whether it should be analyzed.
        """
        # Check ignore patterns first
        for pattern in self._ignore_patterns:
            if pattern.search(line):
                return FilterResult(should_analyze=False, severity="ignore")

        # Check error patterns
        for pattern in self._error_patterns:
            match = pattern.search(line)
            if match:
                return FilterResult(
                    should_analyze=True,
                    severity="error",
                    matched_pattern=match.group(),
                )

        # Check warning patterns
        if self.config.min_severity in ("warning", "info"):
            for pattern in self._warning_patterns:
                match = pattern.search(line)
                if match:
                    return FilterResult(
                        should_analyze=True,
                        severity="warning",
                        matched_pattern=match.group(),
                    )

        # No issues detected
        return FilterResult(should_analyze=False, severity="info")

    def is_stack_trace_line(self, line: str) -> bool:
        """Check if a line looks like part of a stack trace."""
        stack_patterns = [
            r"^\s+at\s+",  # Java/JS stack trace
            r"^\s+File\s+\"",  # Python stack trace
            r"^\s+\d+:\s+0x",  # Go stack trace
            r"^\s+\w+\.\w+\(",  # Generic method call
            r"^\s+in\s+\w+\s+at\s+",  # C#/.NET
        ]
        return any(re.match(p, line) for p in stack_patterns)
