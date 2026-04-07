from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_automation.agents import build_command, detect_budget_depleted, parse_output, run_agent
from claude_automation.config import default_pipeline_config, StageConfig


def _planner_config() -> StageConfig:
    return default_pipeline_config().stages["planner"]


def _coder_config() -> StageConfig:
    return default_pipeline_config().stages["coder"]


SAFETY = "do not do bad things"
MODEL = "claude-test-model"


WORK_DIR = Path("/tmp/worktree")


def _read_script(temp_files):
    script_path = next(f for f in temp_files if f.endswith(".sh"))
    return Path(script_path).read_text(encoding="utf-8")


def _cleanup(temp_files):
    for f in temp_files:
        try:
            Path(f).unlink()
        except OSError:
            pass


def test_build_command_planner():
    cfg = _planner_config()
    cmd, temp_files = build_command(cfg, "plan this", MODEL, SAFETY, WORK_DIR)
    try:
        assert isinstance(cmd, str)
        assert "bash" in cmd
        script = _read_script(temp_files)
        assert "--permission-mode plan" in script
        assert cfg.allowed_tools in script
    finally:
        _cleanup(temp_files)


def test_build_command_includes_cd():
    cfg = _planner_config()
    cmd, temp_files = build_command(cfg, "plan this", MODEL, SAFETY, WORK_DIR)
    try:
        script = _read_script(temp_files)
        assert "cd " in script
        assert "worktree" in script
    finally:
        _cleanup(temp_files)


def test_build_command_coder():
    cfg = _coder_config()
    cmd, temp_files = build_command(cfg, "code this", MODEL, SAFETY, WORK_DIR)
    try:
        script = _read_script(temp_files)
        assert "--permission-mode acceptEdits" in script
        assert cfg.allowed_tools in script
    finally:
        _cleanup(temp_files)


def test_build_command_writes_prompt_to_temp_file():
    cfg = _planner_config()
    prompt = "it's a test with 'quotes' and $(dangerous) chars"
    cmd, temp_files = build_command(cfg, prompt, MODEL, SAFETY, WORK_DIR)
    try:
        prompt_file = next(f for f in temp_files if "prompt" in f)
        assert Path(prompt_file).read_text(encoding="utf-8") == prompt
    finally:
        _cleanup(temp_files)


def test_parse_output_valid_json():
    assert parse_output('{"result": "hello world"}') == "hello world"


def test_parse_output_invalid_json():
    raw = "not json at all"
    assert parse_output(raw) == raw


def test_parse_output_empty():
    assert parse_output("") == ""


def test_detect_budget_depleted_stderr():
    assert detect_budget_depleted("", "budget exceeded", 1) is True


def test_detect_budget_depleted_false():
    assert detect_budget_depleted('{"result": "ok"}', "some normal error", 0) is False


def test_detect_budget_depleted_false_limit_in_stdout():
    assert detect_budget_depleted('{"result": "set the limit to 100"}', "", 0) is False


def test_detect_budget_depleted_rate_limit():
    assert detect_budget_depleted("", "rate limit reached", 1) is True


@patch("claude_automation.agents.subprocess.run")
def test_run_agent_success(mock_run):
    mock_run.return_value = MagicMock(
        stdout='{"result": "all done"}',
        stderr="",
        returncode=0,
    )
    cfg = _coder_config()
    result = run_agent(cfg, "do work", Path("/tmp"), MODEL, SAFETY)
    assert result.success is True
    assert result.output == "all done"
    assert result.return_code == 0
    assert result.budget_depleted is False


@patch("claude_automation.agents.subprocess.run")
def test_run_agent_failure(mock_run):
    mock_run.return_value = MagicMock(
        stdout="",
        stderr="something went wrong",
        returncode=1,
    )
    cfg = _coder_config()
    result = run_agent(cfg, "do work", Path("/tmp"), MODEL, SAFETY)
    assert result.success is False
    assert result.return_code == 1


@patch("claude_automation.agents.subprocess.run")
def test_run_agent_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=10)
    cfg = _coder_config()
    result = run_agent(cfg, "do work", Path("/tmp"), MODEL, SAFETY)
    assert result.success is False
    assert result.error == "timeout"


@patch("claude_automation.agents.subprocess.run")
def test_run_agent_budget_depleted(mock_run):
    mock_run.return_value = MagicMock(
        stdout='{"error": "budget limit reached"}',
        stderr="budget limit reached",
        returncode=1,
    )
    cfg = _coder_config()
    result = run_agent(cfg, "do work", Path("/tmp"), MODEL, SAFETY)
    assert result.budget_depleted is True
