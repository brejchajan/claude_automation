from pathlib import Path
import subprocess  # noqa: S404
from typing import Optional


def branch_exists(repo_path: Path, branch_name: str) -> bool:
    """Check whether a branch exists in the repository.

    Returns:
        bool: True if the branch exists, False otherwise.
    """
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_path), "rev-parse", "--verify", branch_name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def detect_default_branch(repo_path: Path) -> str:
    """Detect the current HEAD branch name of the repository.

    Returns:
        str: Current branch name, or "main" if detection fails.
    """
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return "main"


def create_worktree(repo_path: Path, branch_name: str, base_branch: Optional[str] = None) -> Path:
    """Create a git worktree for the given branch and return its path.

    Returns:
        Path: Filesystem path to the newly created worktree.

    Raises:
        RuntimeError: If the git worktree add command fails.
    """
    if base_branch is None:
        base_branch = detect_default_branch(repo_path)
    worktree_path = repo_path.parent / ".worktrees" / branch_name
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(  # noqa: S603
        [
            "git",
            "-C",
            str(repo_path),
            "worktree",
            "add",
            str(worktree_path),
            "-b",
            branch_name,
            base_branch,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        msg = f"Failed to create worktree '{branch_name}': {result.stderr.strip()}"
        raise RuntimeError(msg)

    return worktree_path


def cleanup_worktree(repo_path: Path, worktree_path: Path) -> None:
    """Remove a git worktree from disk and the repository's worktree list.

    Raises:
        RuntimeError: If the git worktree remove command fails.
    """
    result = subprocess.run(  # noqa: S603
        [
            "git",
            "-C",
            str(repo_path),
            "worktree",
            "remove",
            str(worktree_path),
            "--force",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        msg = f"Failed to remove worktree '{worktree_path}': {result.stderr.strip()}"
        raise RuntimeError(msg)


def commit_worktree(worktree_path: Path, message: str) -> bool:
    """Stage all changes in the worktree and create a commit.

    Returns:
        bool: True if a commit was created, False if there was nothing to commit.

    Raises:
        RuntimeError: If staging or committing fails for an unexpected reason.
    """
    add_result = subprocess.run(  # noqa: S603
        ["git", "-C", str(worktree_path), "add", "-A"],
        capture_output=True,
        text=True,
        check=False,
    )

    if add_result.returncode != 0:
        msg = f"Failed to stage changes in '{worktree_path}': {add_result.stderr.strip()}"
        raise RuntimeError(msg)

    commit_result = subprocess.run(  # noqa: S603
        ["git", "-C", str(worktree_path), "commit", "-m", message],
        capture_output=True,
        text=True,
        check=False,
    )

    if commit_result.returncode == 0:
        return True

    if commit_result.returncode == 1 and "nothing to commit" in commit_result.stdout:
        return False

    msg = f"Failed to commit in '{worktree_path}': {commit_result.stderr.strip()}"
    raise RuntimeError(msg)


def get_diff(worktree_path: Path) -> str:
    """Return the git diff of HEAD in the worktree.

    Returns:
        str: The diff output as a string.

    Raises:
        RuntimeError: If the git diff command fails.
    """
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(worktree_path), "diff", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        msg = f"Failed to get diff in '{worktree_path}': {result.stderr.strip()}"
        raise RuntimeError(msg)

    return result.stdout
