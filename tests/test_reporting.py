import json
from pathlib import Path
from typing import List

from config import StageResult, Task, TaskResult
from reporting import generate_report, slugify_title


def make_task_result(
    title: str = "Test", status: str = "success", stages_count: int = 2
) -> TaskResult:
    task = Task(
        title=title,
        project="/tmp/p",
        branch=f"auto/{title.lower()}",
        model="m",
        budget_per_stage=1.0,
        priority=10,
        stages=["planner", "coder"],
        description="desc",
    )
    stage_results: List[StageResult] = [
        StageResult(
            stage=f"stage{i}",
            success=(status == "success"),
            output=f"output{i}",
            error="",
            duration_seconds=float(i + 1),
            return_code=0,
            budget_depleted=False,
        )
        for i in range(stages_count)
    ]
    return TaskResult(
        task=task,
        stage_results=stage_results,
        status=status,
        branch_name=task.branch,
        paused_at_stage=None,
        accumulated_context={},
    )


def test_generate_report_success(tmp_path: Path) -> None:
    result = make_task_result(title="My Task", status="success", stages_count=2)
    summary = generate_report([result], "2024-01-01_120000", tmp_path)

    assert summary.exists()
    content = summary.read_text()
    assert "My Task" in content
    assert "auto/my task" in content
    assert "success" in content
    assert "Branches Ready for Review" in content
    assert "auto/my task" in content

    task_dir = tmp_path / "2024-01-01_120000" / slugify_title("My Task")
    assert (task_dir / "stage0_output.json").exists()
    assert (task_dir / "stage1_output.json").exists()

    data = json.loads((task_dir / "stage0_output.json").read_text())
    assert data["stage"] == "stage0"
    assert data["output"] == "output0"


def test_generate_report_failure(tmp_path: Path) -> None:
    result = make_task_result(
        title="Failing Task", status="failed_at_coder", stages_count=1
    )
    summary = generate_report([result], "2024-01-02_120000", tmp_path)

    content = summary.read_text()
    assert "failed_at_coder" in content
    assert "Failed Tasks" in content
    assert "Failing Task" in content


def test_generate_report_mixed(tmp_path: Path) -> None:
    success_result = make_task_result(title="Good Task", status="success")
    failed_result = make_task_result(title="Bad Task", status="failed_at_planner")
    summary = generate_report(
        [success_result, failed_result], "2024-01-03_120000", tmp_path
    )

    content = summary.read_text()
    assert "Good Task" in content
    assert "Bad Task" in content
    assert "success" in content
    assert "failed_at_planner" in content
    assert "Branches Ready for Review" in content
    assert "Failed Tasks" in content


def test_generate_report_creates_dirs(tmp_path: Path) -> None:
    nested_logs = tmp_path / "deep" / "nested" / "logs"
    result = make_task_result(title="Dir Test", status="success")
    summary = generate_report([result], "2024-01-04_120000", nested_logs)

    assert summary.exists()
    assert (nested_logs / "2024-01-04_120000").is_dir()
    assert (nested_logs / "2024-01-04_120000" / slugify_title("Dir Test")).is_dir()
