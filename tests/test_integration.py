from pathlib import Path
import subprocess
import sys
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import default_pipeline_config, StageResult, Task, TaskResult
from pipeline import run_all_tasks
from reporting import generate_report
from task_parser import discover_tasks


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@test.com"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "README.md").write_text("# Test")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "initial"], check=True)
    subprocess.run(["git", "-C", str(repo), "branch", "-M", "main"], check=True)
    return repo


def _make_success_result(stage: str = "", output: str = "done") -> StageResult:
    return StageResult(
        stage=stage,
        success=True,
        output=output,
        error="",
        duration_seconds=1.0,
        return_code=0,
        budget_depleted=False,
    )


def _make_budget_result(stage: str = "") -> StageResult:
    return StageResult(
        stage=stage,
        success=True,
        output="partial",
        error="",
        duration_seconds=1.0,
        return_code=0,
        budget_depleted=True,
    )


def _make_task_md(
    title: str,
    project: str,
    priority: int = 10,
    stages: Optional[List[str]] = None,
) -> str:
    lines = [
        "---",
        f"title: {title}",
        f"project: {project}",
        f"priority: {priority}",
    ]
    if stages is not None:
        lines.append("stages:")
        for s in stages:
            lines.append(f"  - {s}")
    lines.append("---")
    lines.append(f"Implement {title}.")
    return "\n".join(lines) + "\n"


@patch("pipeline.cleanup_worktree")
@patch("pipeline.get_diff", return_value="")
@patch("pipeline.commit_worktree", return_value=True)
@patch("pipeline.create_worktree")
@patch("pipeline.run_agent")
def test_end_to_end_with_mocked_claude(
    mock_agent: MagicMock,
    mock_create: MagicMock,
    mock_commit: MagicMock,
    mock_diff: MagicMock,
    mock_cleanup: MagicMock,
    temp_repo: Path,
    tmp_path: Path,
) -> None:
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    mock_create.return_value = worktree_path

    mock_agent.side_effect = [
        _make_success_result(output="plan output"),
        _make_success_result(output="code output"),
        _make_success_result(output="review output"),
        _make_success_result(output="test output"),
    ]

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "task1.md").write_text(_make_task_md("Auth Feature", str(temp_repo)))

    tasks = discover_tasks(tasks_dir)
    assert len(tasks) == 1

    config = default_pipeline_config()
    results = run_all_tasks(tasks, config)

    assert len(results) == 1
    assert results[0].status == "success"
    assert mock_agent.call_count == 4

    logs_dir = tmp_path / "logs"
    summary_path = generate_report(results, "2026-03-21_000000", logs_dir)
    assert summary_path.exists()
    content = summary_path.read_text()
    assert "Auth Feature" in content


@patch("pipeline.cleanup_worktree")
@patch("pipeline.get_diff", return_value="")
@patch("pipeline.commit_worktree", return_value=True)
@patch("pipeline.create_worktree")
@patch("pipeline.run_agent")
def test_end_to_end_custom_stages(
    mock_agent: MagicMock,
    mock_create: MagicMock,
    mock_commit: MagicMock,
    mock_diff: MagicMock,
    mock_cleanup: MagicMock,
    temp_repo: Path,
    tmp_path: Path,
) -> None:
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    mock_create.return_value = worktree_path

    mock_agent.return_value = _make_success_result(output="code output")

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "task1.md").write_text(
        _make_task_md("Quick Fix", str(temp_repo), stages=["coder"])
    )

    tasks = discover_tasks(tasks_dir)
    config = default_pipeline_config()
    results = run_all_tasks(tasks, config)

    assert len(results) == 1
    assert results[0].status == "success"
    assert mock_agent.call_count == 1


@patch("pipeline.cleanup_worktree")
@patch("pipeline.get_diff", return_value="")
@patch("pipeline.commit_worktree", return_value=True)
@patch("pipeline.create_worktree")
@patch("pipeline.run_agent")
@patch("pipeline.time")
def test_end_to_end_retry_on_budget(
    mock_time: MagicMock,
    mock_agent: MagicMock,
    mock_create: MagicMock,
    mock_commit: MagicMock,
    mock_diff: MagicMock,
    mock_cleanup: MagicMock,
    temp_repo: Path,
    tmp_path: Path,
) -> None:
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    mock_create.return_value = worktree_path

    mock_agent.side_effect = [
        _make_budget_result(),
        _make_success_result(output="done"),
    ]

    mock_time.monotonic.side_effect = [0.0, 0.0, 100.0]
    mock_time.sleep = MagicMock()

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "task1.md").write_text(
        _make_task_md("Budget Task", str(temp_repo), stages=["planner"])
    )

    tasks = discover_tasks(tasks_dir)
    config = default_pipeline_config()
    config.retry_interval_minutes = 0
    config.retry_window_hours = 1.0

    results = run_all_tasks(tasks, config)

    assert len(results) == 1
    assert results[0].status == "success"
    assert mock_agent.call_count == 2


@patch("pipeline.cleanup_worktree")
@patch("pipeline.get_diff", return_value="")
@patch("pipeline.commit_worktree", return_value=True)
@patch("pipeline.create_worktree")
@patch("pipeline.run_agent")
def test_task_discovery_and_pipeline(
    mock_agent: MagicMock,
    mock_create: MagicMock,
    mock_commit: MagicMock,
    mock_diff: MagicMock,
    mock_cleanup: MagicMock,
    temp_repo: Path,
    tmp_path: Path,
) -> None:
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    mock_create.return_value = worktree_path

    mock_agent.return_value = _make_success_result(output="done")

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "high.md").write_text(
        _make_task_md(
            "High Priority Task", str(temp_repo), priority=1, stages=["coder"]
        )
    )
    (tasks_dir / "low.md").write_text(
        _make_task_md(
            "Low Priority Task", str(temp_repo), priority=20, stages=["coder"]
        )
    )

    tasks = discover_tasks(tasks_dir)
    assert len(tasks) == 2
    assert tasks[0].priority == 1
    assert tasks[1].priority == 20

    config = default_pipeline_config()
    results = run_all_tasks(tasks, config)

    assert len(results) == 2
    assert results[0].task.title == "High Priority Task"
    assert results[1].task.title == "Low Priority Task"
    assert all(r.status == "success" for r in results)


def test_report_generation_end_to_end(tmp_path: Path) -> None:
    success_task = Task(
        title="Success Task",
        project="/tmp/repo",
        branch="auto/success-task",
        model="claude-sonnet-4-5-20250514",
        budget_per_stage=1.0,
        priority=10,
        stages=["planner", "coder"],
        description="A successful task",
    )
    success_result = TaskResult(
        task=success_task,
        stage_results=[
            StageResult(
                stage="planner",
                success=True,
                output="plan",
                error="",
                duration_seconds=2.0,
                return_code=0,
                budget_depleted=False,
            ),
            StageResult(
                stage="coder",
                success=True,
                output="code",
                error="",
                duration_seconds=5.0,
                return_code=0,
                budget_depleted=False,
            ),
        ],
        status="success",
        branch_name="auto/success-task",
        paused_at_stage=None,
        accumulated_context={"planner": "plan", "coder": "code"},
    )

    failed_task = Task(
        title="Failed Task",
        project="/tmp/repo",
        branch="auto/failed-task",
        model="claude-sonnet-4-5-20250514",
        budget_per_stage=1.0,
        priority=10,
        stages=["planner", "coder"],
        description="A failing task",
    )
    failed_result = TaskResult(
        task=failed_task,
        stage_results=[
            StageResult(
                stage="planner",
                success=True,
                output="plan",
                error="",
                duration_seconds=1.5,
                return_code=0,
                budget_depleted=False,
            ),
            StageResult(
                stage="coder",
                success=False,
                output="",
                error="compile error",
                duration_seconds=3.0,
                return_code=1,
                budget_depleted=False,
            ),
        ],
        status="failed_at_coder",
        branch_name="auto/failed-task",
        paused_at_stage=None,
        accumulated_context={"planner": "plan"},
    )

    logs_dir = tmp_path / "logs"
    summary_path = generate_report(
        [success_result, failed_result], "2026-03-21_100000", logs_dir
    )

    assert summary_path.exists()
    content = summary_path.read_text()

    assert "Branches Ready for Review" in content
    assert "auto/success-task" in content

    assert "Failed Tasks" in content
    assert "Failed Task" in content
    assert "failed_at_coder" in content

    assert "| planner | yes |" in content
    assert "| coder | no |" in content
    assert "| coder | yes |" in content
