"""OpenAI-powered log analyzer."""

import json
from dataclasses import dataclass

from openai import AsyncOpenAI

from .buffer import IssueBatch, BufferedIssue


@dataclass
class AnalysisResult:
    """Result of analyzing a batch of issues."""

    summary: str
    severity: str  # "critical", "high", "medium", "low"
    root_cause: str | None
    suggested_actions: list[str]
    affected_components: list[str]
    raw_response: str


@dataclass
class QueryResult:
    """Result of an interactive query."""

    answer: str
    health_status: str  # "healthy", "degraded", "unhealthy"
    issues_found: int
    recommendations: list[str]


class LogAnalyzer:
    """Analyze logs using OpenAI."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
    ):
        """
        Initialize the analyzer.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model to use for analysis
            base_url: Optional custom API base URL
        """
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def analyze_batch(self, batch: IssueBatch) -> AnalysisResult:
        """Analyze a batch of log issues."""
        prompt = f"""Analyze the following log issues and provide a structured analysis.

{batch.format_for_analysis()}

Respond in JSON format with these fields:
- summary: A brief (1-2 sentence) summary of what's happening
- severity: One of "critical", "high", "medium", "low"
- root_cause: Your best assessment of the root cause (or null if unclear)
- suggested_actions: List of recommended actions to investigate or fix
- affected_components: List of system components that appear affected

Be concise and actionable."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a log analysis expert. Analyze logs and identify issues, root causes, and solutions. Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        raw = response.choices[0].message.content or "{}"

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "summary": "Failed to parse analysis",
                "severity": "medium",
                "root_cause": None,
                "suggested_actions": [],
                "affected_components": [],
            }

        return AnalysisResult(
            summary=data.get("summary", "No summary available"),
            severity=data.get("severity", "medium"),
            root_cause=data.get("root_cause"),
            suggested_actions=data.get("suggested_actions", []),
            affected_components=data.get("affected_components", []),
            raw_response=raw,
        )

    async def answer_query(
        self,
        query: str,
        recent_issues: list[BufferedIssue],
        recent_log_sample: list[str],
        summary: dict,
    ) -> QueryResult:
        """Answer an interactive query about the logs."""
        # Format recent issues for context
        issues_text = ""
        if recent_issues:
            issues_text = "\n\nRecent issues detected:\n"
            for i, issue in enumerate(recent_issues[-10:], 1):  # Last 10 issues
                issues_text += f"{i}. [{issue.filter_result.severity}] {issue.trigger_line.content}\n"

        # Sample of recent logs
        logs_text = ""
        if recent_log_sample:
            logs_text = "\n\nSample of recent logs:\n"
            logs_text += "\n".join(recent_log_sample[-50:])  # Last 50 lines

        prompt = f"""Based on the log monitoring data below, answer the user's question.

Summary:
- Time range: Last {summary['time_range_minutes']} minutes
- Total log lines: {summary['total_log_lines']}
- Errors detected: {summary['error_count']}
- Warnings detected: {summary['warning_count']}
{issues_text}
{logs_text}

User question: {query}

Respond in JSON format with:
- answer: Direct answer to the question
- health_status: "healthy", "degraded", or "unhealthy"
- issues_found: Number of significant issues found
- recommendations: List of recommendations (if any)

Be concise and direct."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a log monitoring assistant. Answer questions about system health based on log data. Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        raw = response.choices[0].message.content or "{}"

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "answer": "Unable to process query",
                "health_status": "unknown",
                "issues_found": 0,
                "recommendations": [],
            }

        return QueryResult(
            answer=data.get("answer", "No answer available"),
            health_status=data.get("health_status", "unknown"),
            issues_found=data.get("issues_found", 0),
            recommendations=data.get("recommendations", []),
        )
