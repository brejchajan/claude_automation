from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from task_parser import discover_tasks, parse_task, slugify


def test_parse_task_full_frontmatter(tmp_path):
    md = tmp_path / "task.md"
    md.write_text(
        "---\n"
        "title: Add Authentication\n"
        "project: /some/project\n"
        "branch: feature/auth\n"
        "model: claude-opus-4\n"
        "budget_per_stage: 2.5\n"
        "priority: 5\n"
        "stages:\n"
        "  - planner\n"
        "  - coder\n"
        "---\n"
        "Implement JWT authentication.\n"
    )
    task = parse_task(md)
    assert task.title == "Add Authentication"
    assert task.project == "/some/project"
    assert task.branch == "feature/auth"
    assert task.model == "claude-opus-4"
    assert task.budget_per_stage == 2.5
    assert task.priority == 5
    assert task.stages == ["planner", "coder"]
    assert "JWT" in task.description


def test_parse_task_minimal_frontmatter(tmp_path):
    md = tmp_path / "task.md"
    md.write_text("---\ntitle: Fix Bug\nproject: /my/repo\n---\nFix the critical bug.\n")
    task = parse_task(md)
    assert task.title == "Fix Bug"
    assert task.project == "/my/repo"
    assert task.branch == "auto/fix-bug"
    assert task.model == "claude-sonnet-4-5-20250514"
    assert task.budget_per_stage == 1.0
    assert task.priority == 10
    assert len(task.stages) == 4
    assert "Fix the critical bug." in task.description


def test_slugify_basic():
    assert slugify("Add Authentication") == "add-authentication"


def test_slugify_special_chars():
    assert slugify("Fix Bug #123!") == "fix-bug-123"


def test_slugify_multiple_spaces():
    assert slugify("hello   world") == "hello-world"


def test_slugify_leading_trailing():
    assert slugify("  hello world  ") == "hello-world"


def test_parse_task_missing_title(tmp_path):
    md = tmp_path / "task.md"
    md.write_text("---\nproject: /my/repo\n---\nSome description.\n")
    with pytest.raises(ValueError, match="title"):
        parse_task(md)


def test_parse_task_missing_project(tmp_path):
    md = tmp_path / "task.md"
    md.write_text("---\ntitle: My Task\n---\nSome description.\n")
    with pytest.raises(ValueError, match="project"):
        parse_task(md)


def test_parse_task_invalid_stage(tmp_path):
    md = tmp_path / "task.md"
    md.write_text(
        "---\ntitle: My Task\nproject: /my/repo\nstages:\n  - planner\n  - invalid_stage\n---\nDescription.\n"
    )
    with pytest.raises(ValueError, match="Invalid stage"):
        parse_task(md)


def test_discover_tasks_sorted_by_priority(tmp_path):
    (tmp_path / "high.md").write_text("---\ntitle: High Priority\nproject: /repo\npriority: 1\n---\nHigh.\n")
    (tmp_path / "low.md").write_text("---\ntitle: Low Priority\nproject: /repo\npriority: 20\n---\nLow.\n")
    (tmp_path / "mid.md").write_text("---\ntitle: Mid Priority\nproject: /repo\npriority: 5\n---\nMid.\n")
    tasks = discover_tasks(tmp_path)
    assert len(tasks) == 3
    assert tasks[0].priority == 1
    assert tasks[1].priority == 5
    assert tasks[2].priority == 20


def test_discover_tasks_empty_dir(tmp_path):
    tasks = discover_tasks(tmp_path)
    assert tasks == []


def test_parse_task_depends_on(tmp_path):
    md = tmp_path / "task.md"
    md.write_text("---\ntitle: Task B\nproject: /repo\nbranch: BDT-0002\ndepends_on: BDT-0001\n---\nDependent task.\n")
    task = parse_task(md)
    assert task.depends_on == "BDT-0001"


def test_parse_task_no_depends_on(tmp_path):
    md = tmp_path / "task.md"
    md.write_text("---\ntitle: Task A\nproject: /repo\n---\nIndependent task.\n")
    task = parse_task(md)
    assert task.depends_on is None
