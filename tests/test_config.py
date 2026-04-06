from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_automation.config import default_pipeline_config, DEFAULT_SAFETY_PROMPT, StageConfig, VALID_STAGES


def test_default_pipeline_config_has_all_stages():
    config = default_pipeline_config()
    for stage in VALID_STAGES:
        assert stage in config.stages


def test_default_pipeline_config_stage_types():
    config = default_pipeline_config()
    for stage_name, stage_cfg in config.stages.items():
        assert isinstance(stage_cfg, StageConfig)


def test_stage_config_defaults():
    cfg = StageConfig(
        allowed_tools="Read",
        permission_mode="plan",
        system_prompt="test",
    )
    assert cfg.budget_usd == 1.0
    assert cfg.timeout_seconds == 1800


def test_stage_config_planner_mode():
    config = default_pipeline_config()
    assert config.stages["planner"].permission_mode == "plan"


def test_stage_config_coder_mode():
    config = default_pipeline_config()
    assert config.stages["coder"].permission_mode == "acceptEdits"


def test_valid_stages_contains_expected():
    assert "planner" in VALID_STAGES
    assert "coder" in VALID_STAGES
    assert "reviewer" in VALID_STAGES
    assert "tester" in VALID_STAGES
    assert len(VALID_STAGES) == 4


def test_default_safety_prompt_nonempty():
    assert isinstance(DEFAULT_SAFETY_PROMPT, str)
    assert len(DEFAULT_SAFETY_PROMPT.strip()) > 0


def test_pipeline_config_defaults():
    config = default_pipeline_config()
    assert config.tasks_dir == "./tasks"
    assert config.logs_dir == "./logs"
    assert config.global_budget_cap_usd == 10.0
    assert config.keep_worktrees is True
    assert config.retry_window_hours == 12.0
    assert config.retry_interval_minutes == 10
