import json
from pathlib import Path
import shlex
import subprocess  # noqa: S404
import time
from typing import List

from config import StageConfig, StageResult


def build_command(stage_config: StageConfig, prompt: str, model: str, safety_prompt: str) -> List[str]:
    """Build the shell command list to invoke the claude CLI agent.

    Returns:
        List[str]: Command list suitable for passing to subprocess.
    """
    cmd_str = (
        f"source ~/.bashrc && claude -p {shlex.quote(prompt)}"
        f" --allowedTools {shlex.quote(stage_config.allowed_tools)}"
        f" --permission-mode {stage_config.permission_mode}"
        f" --output-format json"
        f" --max-budget-usd {stage_config.budget_usd}"
        f" --model {model}"
        f" --append-system-prompt {shlex.quote(safety_prompt)}"
    )
    return ["bash", "-c", cmd_str]


def parse_output(stdout: str) -> str:
    """Parse JSON stdout from the claude CLI and return the result field.

    Returns:
        str: Parsed result string, or raw stdout if JSON parsing fails.
    """
    if not stdout:
        return ""
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
    combined = (stderr or "").lower() + (stdout or "").lower()
    if "budget" in combined or "limit" in combined:
        return True
    try:
        data = json.loads(stdout or "")
        error_field = str(data.get("error", "")).lower()
        if "budget" in error_field or "limit" in error_field:
            return True
    except (json.JSONDecodeError, AttributeError):
        pass
    return False


def run_agent(
    stage_config: StageConfig,
    prompt: str,
    working_dir: Path,
    model: str,
    safety_prompt: str,
) -> StageResult:
    """Run the claude CLI agent for a single pipeline stage and return the result.

    Returns:
        StageResult: Result containing output, success flag, and budget status.
    """
    cmd = build_command(stage_config, prompt, model, safety_prompt)
    start = time.monotonic()
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=stage_config.timeout_seconds,
            check=False,
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
