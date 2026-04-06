from dataclasses import dataclass, field
from typing import Dict, List, Optional

VALID_STAGES: List[str] = ["planner", "coder", "reviewer", "tester"]

DEFAULT_SAFETY_PROMPT: str = (
    "SAFETY RULES (MANDATORY):\n"
    "1. NEVER delete any file without first creating a backup copy in a .backup directory.\n"
    "2. NEVER access or modify files outside the current working directory.\n"
    "3. NEVER ask questions to the user. Use project context and task description.\n"
    "4. NEVER run destructive git commands (reset --hard, clean -f, push --force).\n"
    "5. NEVER install system-level packages or modify system configuration.\n"
    "6. All commit messages MUST start with the branch name followed by a space and the message, "
    "e.g., 'BDT-0001 Add authentication module'.\n"
    "7. All commit messages MUST end with a blank line followed by 'CREATED BY Claude Automation Tool' "
    "as the last line."
)


@dataclass
class StageConfig:
    """Configuration for a single pipeline stage."""

    allowed_tools: str
    permission_mode: str
    system_prompt: str
    budget_usd: float = 1.0
    timeout_seconds: int = 1800


@dataclass
class PipelineConfig:
    """Top-level configuration for the automation pipeline."""

    tasks_dir: str = "./tasks"
    tasks_done_dir: str = "./tasks_done"
    logs_dir: str = "./logs"
    default_model: str = "claude-sonnet-4-5-20250514"
    schedule_cron: str = "0 2 * * *"
    global_budget_cap_usd: float = 10.0
    max_output_chars: int = 30000
    keep_worktrees: bool = True
    safety_prompt: str = DEFAULT_SAFETY_PROMPT
    stages: Dict[str, StageConfig] = field(default_factory=dict)
    retry_window_hours: float = 12.0
    retry_interval_minutes: int = 10


@dataclass
class Task:
    """Represents a single automation task loaded from a markdown file."""

    title: str
    project: str
    branch: str
    model: str
    budget_per_stage: float
    priority: int
    stages: List[str]
    description: str
    base_branch: Optional[str] = None
    depends_on: Optional[str] = None
    source_path: Optional[str] = None


@dataclass
class StageResult:
    """Result produced by running a single pipeline stage."""

    stage: str
    success: bool
    output: str
    error: str
    duration_seconds: float
    return_code: int
    budget_depleted: bool


@dataclass
class TaskResult:
    """Aggregated result for a full task run across all stages."""

    task: Task
    stage_results: List[StageResult]
    status: str
    branch_name: str
    paused_at_stage: Optional[str]
    accumulated_context: Dict[str, str]


def default_pipeline_config() -> PipelineConfig:
    """Return a PipelineConfig populated with sensible defaults for all stages."""
    stages = {
        "planner": StageConfig(
            allowed_tools="Read,Glob,Grep,Bash(git log:*),Bash(find:*),Bash(ls:*)",
            permission_mode="plan",
            system_prompt=(
                "You are a software architect. Read the task description and explore the project codebase. "
                "Produce a detailed step-by-step implementation plan. "
                "List files to create/modify and changes required. "
                "Do NOT make any code changes."
            ),
        ),
        "coder": StageConfig(
            allowed_tools="Read,Glob,Grep,Edit,Write,Bash",
            permission_mode="acceptEdits",
            system_prompt=(
                "You are an expert software engineer. Implement the task according to the provided plan. "
                "Follow the project's coding conventions. Make all necessary code changes. "
                "Do NOT ask questions. When done, summarize all changes made."
            ),
        ),
        "reviewer": StageConfig(
            allowed_tools="Read,Glob,Grep,Edit,Write,Bash",
            permission_mode="acceptEdits",
            system_prompt=(
                "You are a senior code reviewer. Review the code changes (git diff provided). "
                "Check for bugs, security issues, style violations, missing error handling, "
                "and deviation from requirements. "
                "Fix issues directly. Summarize findings and fixes."
            ),
        ),
        "tester": StageConfig(
            allowed_tools="Read,Glob,Grep,Edit,Write,Bash",
            permission_mode="acceptEdits",
            system_prompt=(
                "You are a QA engineer. Run the project's test suite. "
                "If tests fail due to recent changes, fix the code. "
                "If no tests exist, create appropriate tests. "
                "If the project cannot be tested programmatically "
                "(e.g., iOS/Xcode projects without a working test target), "
                "skip test execution and instead review the code for correctness. "
                "Summarize test results."
            ),
        ),
    }
    return PipelineConfig(stages=stages)
