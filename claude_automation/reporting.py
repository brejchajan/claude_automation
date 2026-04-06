import json
from pathlib import Path
import re
from typing import List

from .config import TaskResult


def slugify_title(title: str) -> str:
    """Convert a title string to a URL-friendly slug.

    Returns:
        str: Lowercased, hyphenated slug with special characters removed.
    """
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _write_stage_files(task_result: TaskResult, task_dir: Path) -> None:
    """Write per-stage JSON output files into the given task directory."""
    for stage_result in task_result.stage_results:
        stage_file = task_dir / f"{stage_result.stage}_output.json"
        stage_file.write_text(
            json.dumps(
                {
                    "stage": stage_result.stage,
                    "success": stage_result.success,
                    "output": stage_result.output,
                    "error": stage_result.error,
                    "duration_seconds": stage_result.duration_seconds,
                    "return_code": stage_result.return_code,
                    "budget_depleted": stage_result.budget_depleted,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _build_results_table(results: List[TaskResult]) -> str:
    """Build a markdown table row string summarising each task result.

    Returns:
        str: Newline-joined markdown table rows.
    """
    rows = []
    for tr in results:
        total_duration = sum(sr.duration_seconds for sr in tr.stage_results)
        rows.append(f"| {tr.task.title} | {tr.branch_name} | {tr.status} | {total_duration:.1f}s |")
    return "\n".join(rows)


def _build_stage_details(results: List[TaskResult]) -> str:
    """Build a markdown section with per-stage detail tables for all tasks.

    Returns:
        str: Markdown string with one subsection per task.
    """
    stage_sections = []
    for tr in results:
        stage_rows = []
        for sr in tr.stage_results:
            success_str = "yes" if sr.success else "no"
            depleted_str = "yes" if sr.budget_depleted else "no"
            stage_rows.append(f"| {sr.stage} | {success_str} | {sr.duration_seconds:.1f}s | {depleted_str} |")
        stage_rows_str = "\n".join(stage_rows)
        stage_sections.append(
            f"### {tr.task.title}\n\n"
            f"| Stage | Success | Duration | Budget Depleted |\n"
            f"|-------|---------|----------|------------------|\n"
            f"{stage_rows_str}"
        )
    return "\n\n".join(stage_sections)


def generate_report(results: List[TaskResult], run_timestamp: str, logs_dir: Path) -> Path:
    """Write per-stage JSON files and a summary markdown report.

    Returns:
        Path: Path to the written summary markdown file.
    """
    run_dir = logs_dir / run_timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    for task_result in results:
        task_dir = run_dir / slugify_title(task_result.task.title)
        task_dir.mkdir(parents=True, exist_ok=True)
        _write_stage_files(task_result, task_dir)

    results_table = _build_results_table(results)
    stage_details = _build_stage_details(results)

    successful = [tr for tr in results if tr.status == "success"]
    branches_lines = "\n".join(f"- `{tr.branch_name}` in `{tr.task.project}`" for tr in successful)
    if not branches_lines:
        branches_lines = "_None_"

    failed = [tr for tr in results if tr.status != "success"]
    failed_lines = "\n".join(f"- **{tr.task.title}**: {tr.status}" for tr in failed)
    if not failed_lines:
        failed_lines = "_None_"

    summary_content = f"""# Pipeline Run Summary - {run_timestamp}

## Results

| Task | Branch | Status | Duration |
|------|--------|--------|----------|
{results_table}

## Stage Details

{stage_details}

## Branches Ready for Review
{branches_lines}

## Failed Tasks
{failed_lines}
"""

    summary_path = run_dir / "summary.md"
    summary_path.write_text(summary_content, encoding="utf-8")
    return summary_path
