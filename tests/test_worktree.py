from pathlib import Path
import subprocess

import pytest

from worktree import cleanup_worktree, commit_worktree, create_worktree, get_diff


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


def test_create_worktree(temp_repo: Path) -> None:
    worktree_path = create_worktree(temp_repo, "feature-branch")
    assert worktree_path.exists()
    assert (worktree_path / ".git").exists()


def test_create_worktree_branch_exists(temp_repo: Path) -> None:
    create_worktree(temp_repo, "feature-branch")
    with pytest.raises(RuntimeError):
        create_worktree(temp_repo, "feature-branch")


def test_cleanup_worktree(temp_repo: Path) -> None:
    worktree_path = create_worktree(temp_repo, "cleanup-branch")
    assert worktree_path.exists()
    cleanup_worktree(temp_repo, worktree_path)
    assert not worktree_path.exists()


def test_commit_worktree(temp_repo: Path) -> None:
    worktree_path = create_worktree(temp_repo, "commit-branch")
    (worktree_path / "new_file.txt").write_text("hello")
    result = commit_worktree(worktree_path, "add new file")
    assert result is True
    log = subprocess.run(
        ["git", "-C", str(worktree_path), "log", "--oneline"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "add new file" in log.stdout


def test_commit_worktree_nothing_to_commit(temp_repo: Path) -> None:
    worktree_path = create_worktree(temp_repo, "empty-branch")
    result = commit_worktree(worktree_path, "nothing here")
    assert result is False


def test_get_diff(temp_repo: Path) -> None:
    worktree_path = create_worktree(temp_repo, "diff-branch")
    (worktree_path / "README.md").write_text("# Modified")
    diff = get_diff(worktree_path)
    assert "Modified" in diff


def test_get_diff_no_changes(temp_repo: Path) -> None:
    worktree_path = create_worktree(temp_repo, "nodiff-branch")
    diff = get_diff(worktree_path)
    assert diff == ""
