import json
import os
from pathlib import Path
import re
import shlex
import subprocess  # noqa: S404
import sys
import tempfile
import time
from typing import List, Tuple

from .config import StageConfig, StageResult


def _extract_session_id(stdout: str) -> str:
    """Extract the session ID from the stream-json init event in the CLI stdout.

    Returns:
        str: The session_id from the first system/init event, or empty string if not found.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get("type") == "system" and data.get("subtype") == "init":
                session_id = data.get("session_id", "")
                if isinstance(session_id, str):
                    return session_id
        except (json.JSONDecodeError, AttributeError):
            continue
    return ""


def _set_session_title(session_id: str, title: str) -> None:
    """Append a custom-title entry to the session's jsonl file so it appears in /resume.

    Writing --name on the CLI inserts the custom-title as the first line of the file,
    which causes the /resume picker to skip the session. Appending it at the end
    preserves resumability and still sets a display name.
    """
    if not session_id or not title:
        return
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return
    for session_file in projects_dir.rglob(f"{session_id}.jsonl"):
        entry = {"type": "custom-title", "customTitle": title, "sessionId": session_id}
        with session_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return


def _to_posix_path(path: Path) -> str:
    """Return a POSIX-style path string, converting Windows drive letters to /drive/... form."""
    posix = path.as_posix()
    if sys.platform == "win32":
        posix = re.sub(r"^([A-Za-z]):", lambda m: "/" + m.group(1).lower(), posix)
    return posix


def _find_bash() -> str:
    """Locate a real bash executable, preferring Git Bash over WSL on Windows.

    On Windows, the default `bash` on PATH is often WSL's bash.exe (in System32),
    which uses /mnt/c/... mount points instead of /c/... — incompatible with the
    POSIX-style paths we generate. Git Bash (MSYS2) uses /c/... and is what we want.

    Returns:
        str: Absolute path to the bash executable, or "bash" as a last resort.
    """
    if sys.platform != "win32":
        return "bash"
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    excluded_markers = ("system32", "windowsapps", "wbem")
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not path_dir:
            continue
        lowered = path_dir.lower()
        if any(marker in lowered for marker in excluded_markers):
            continue
        candidate_path = Path(path_dir) / "bash.exe"
        if candidate_path.exists():
            return str(candidate_path)

    return "bash"


def build_command(
    stage_config: StageConfig,
    prompt: str,
    model: str,
    safety_prompt: str,
    working_dir: Path,
    session_name: str = "",
) -> Tuple[str, List[str]]:
    """Build the shell command string and the list of temp files to clean up after execution.

    Writes the prompt and safety prompt to temp files to avoid platform-specific
    argv quoting issues (especially on Windows where Python's subprocess re-escapes
    arguments using cmd.exe rules before bash receives them). The returned command
    is a shell string intended to be executed with subprocess.run(..., shell=True),
    which is the only mode that reliably passes paths to bash on Windows.

    Returns:
        Tuple[str, List[str]]: (shell command string, temp file paths to delete).
    """
    prompt_fd, prompt_path = tempfile.mkstemp(suffix=".txt", prefix="claude_prompt_", text=True)
    with os.fdopen(prompt_fd, "w", encoding="utf-8") as f:
        f.write(prompt)
    prompt_path = os.path.realpath(prompt_path)

    safety_fd, safety_path = tempfile.mkstemp(suffix=".txt", prefix="claude_safety_", text=True)
    with os.fdopen(safety_fd, "w", encoding="utf-8") as f:
        f.write(safety_prompt)
    safety_path = os.path.realpath(safety_path)

    posix_dir = _to_posix_path(working_dir)
    posix_prompt = _to_posix_path(Path(prompt_path))
    posix_safety = _to_posix_path(Path(safety_path))

    script_lines = [
        "#!/usr/bin/env bash",
        "set -e",
        f"cd {shlex.quote(posix_dir)}",
        f'PROMPT="$(cat {shlex.quote(posix_prompt)})"',
        f'SAFETY="$(cat {shlex.quote(posix_safety)})"',
        (
            'claude -p "$PROMPT"'
            f" --allowedTools {shlex.quote(stage_config.allowed_tools)}"
            f" --permission-mode {stage_config.permission_mode}"
            " --output-format stream-json --verbose"
            f" --max-budget-usd {stage_config.budget_usd}"
            f" --model {shlex.quote(model)}"
            ' --append-system-prompt "$SAFETY"'
        ),
    ]
    script_content = "\n".join(script_lines) + "\n"

    script_fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="claude_run_", text=True)
    with os.fdopen(script_fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(script_content)
    script_path = os.path.realpath(script_path)

    posix_script = _to_posix_path(Path(script_path))
    bash_exe = _find_bash()
    return f'"{bash_exe}" "{posix_script}"', [prompt_path, safety_path, script_path]


def parse_output(stdout: str) -> str:
    """Parse JSON stdout from the claude CLI and return the result field.

    Handles both single-object JSON (--output-format json) and newline-delimited
    stream-json (--output-format stream-json), where the result is on the line
    with "type":"result".

    Returns:
        str: Parsed result string, or raw stdout if JSON parsing fails.
    """
    if not stdout:
        return ""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get("type") == "result":
                return data.get("result", "")
        except (json.JSONDecodeError, AttributeError):
            continue
    try:
        data = json.loads(stdout)
        return data.get("result", "")
    except (json.JSONDecodeError, AttributeError):
        return stdout


def detect_budget_depleted(stdout: str, stderr: str, return_code: int) -> bool:
    """Return True if the agent output indicates the budget was depleted.

    Returns:
        bool: True if budget depletion is detected, False otherwise.
    """
    budget_phrases = [
        "budget depleted",
        "budget exceeded",
        "budget limit",
        "rate limit",
        "you've hit your limit",
        "you have hit the limit",
    ]
    combined = (stderr or "").lower()
    if any(phrase in combined for phrase in budget_phrases):
        return True
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            error_field = str(data.get("error", "")).lower()
            if any(phrase in error_field for phrase in budget_phrases):
                return True
            if data.get("stop_reason", "") == "stop_sequence":
                result_field = str(data.get("result", "")).lower()
                if any(phrase in result_field for phrase in budget_phrases):
                    return True
        except (json.JSONDecodeError, AttributeError):
            continue
    return False


def run_agent(
    stage_config: StageConfig,
    prompt: str,
    working_dir: Path,
    model: str,
    safety_prompt: str,
    session_name: str = "",
) -> StageResult:
    """Run the claude CLI agent for a single pipeline stage and return the result.

    Returns:
        StageResult: Result containing output, success flag, and budget status.
    """
    cmd, temp_files = build_command(stage_config, prompt, model, safety_prompt, working_dir, session_name)
    start = time.monotonic()
    try:
        try:
            result = subprocess.run(  # noqa: S602
                cmd,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=stage_config.timeout_seconds,
                check=False,
                shell=True,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return StageResult(
                stage="",
                success=False,
                output="",
                error="timeout",
                duration_seconds=duration,
                return_code=-1,
                budget_depleted=False,
            )
        duration = time.monotonic() - start
        if session_name:
            session_id = _extract_session_id(result.stdout)
            _set_session_title(session_id, session_name)
        output = parse_output(result.stdout)
        budget_depleted = detect_budget_depleted(result.stdout, result.stderr, result.returncode)
        return StageResult(
            stage="",
            success=(result.returncode == 0),
            output=output,
            error=result.stderr,
            duration_seconds=duration,
            return_code=result.returncode,
            budget_depleted=budget_depleted,
        )
    finally:
        for temp_file in temp_files:
            try:
                Path(temp_file).unlink()
            except OSError:
                pass
