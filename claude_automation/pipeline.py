from __future__ import annotations

from copy import deepcopy
import logging
from pathlib import Path
import time
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable

from .agents import run_agent
from .config import PipelineConfig, StageResult, Task, TaskResult
from .task_parser import discover_tasks
from .worktree import branch_exists, cleanup_worktree, commit_worktree, create_worktree, get_diff, normalize_path

logger = logging.getLogger(__name__)


def build_stage_prompt(
    task: Task,
    stage_name: str,
    config: PipelineConfig,
    accumulated_context: Dict[str, str],
    diff: str = "",
) -> str:
    """Build the full prompt string for the given pipeline stage.

    Returns:
        str: Concatenated prompt including system prompt, task, context, and diff.
    """
    stage_config = config.stages[stage_name]
    parts: List[str] = [stage_config.system_prompt]

    parts.append(f"\n\n## Task\n**Branch:** {task.branch}\n\n{task.description}")

    if accumulated_context:
        context_section = "\n\n## Prior Stage Context"
        for ctx_stage, output in accumulated_context.items():
            truncated = output[: config.max_output_chars]
            context_section += f"\n### {ctx_stage} Output\n{truncated}"
        parts.append(context_section)

    if stage_name == "reviewer" and diff:
        parts.append(f"\n\n## Git Diff\n{diff}")

    return "".join(parts)


def run_task(
    task: Task,
    config: PipelineConfig,
    resume_from: Optional[str] = None,
    existing_context: Optional[Dict[str, str]] = None,
    worktree_path: Optional[Path] = None,
) -> TaskResult:
    """Run all pipeline stages for a single task and return the aggregated result.

    Returns:
        TaskResult: Aggregated result with status, stage results, and context.
    """
    try:
        if worktree_path is None:
            worktree_path = create_worktree(Path(task.project), task.branch, task.base_branch)

        accumulated_context: Dict[str, str] = dict(existing_context or {})
        stage_results: List[StageResult] = []

        stages_to_run = list(task.stages)
        if resume_from is not None:
            try:
                idx = stages_to_run.index(resume_from)
                stages_to_run = stages_to_run[idx:]
            except ValueError:
                pass

        for stage_name in stages_to_run:
            stage_cfg = config.stages[stage_name]
            stage_cfg = deepcopy(stage_cfg)
            stage_cfg.budget_usd = task.budget_per_stage

            diff = ""
            if stage_name == "reviewer":
                diff = get_diff(worktree_path)

            prompt = build_stage_prompt(task, stage_name, config, accumulated_context, diff)

            logger.info("Running stage '%s' for task '%s'", stage_name, task.title)
            session_name = f"{task.branch} [{stage_name}]"
            result = run_agent(stage_cfg, prompt, worktree_path, task.model, config.safety_prompt, session_name)
            result.stage = stage_name
            stage_results.append(result)

            if result.budget_depleted:
                logger.warning(
                    "Budget depleted at stage '%s' for task '%s'",
                    stage_name,
                    task.title,
                )
                return TaskResult(
                    task=task,
                    stage_results=stage_results,
                    status="paused",
                    branch_name=task.branch,
                    paused_at_stage=stage_name,
                    accumulated_context=accumulated_context,
                )

            if not result.success:
                logger.error("Stage '%s' failed for task '%s'", stage_name, task.title)
                return TaskResult(
                    task=task,
                    stage_results=stage_results,
                    status=f"failed_at_{stage_name}",
                    branch_name=task.branch,
                    paused_at_stage=None,
                    accumulated_context=accumulated_context,
                )

            accumulated_context[stage_name] = result.output

        commit_worktree(
            worktree_path,
            f"{task.branch} {task.title}\n\nCREATED BY Claude Automation Tool",
        )

        if not config.keep_worktrees:
            cleanup_worktree(Path(task.project), worktree_path)

        return TaskResult(
            task=task,
            stage_results=stage_results,
            status="success",
            branch_name=task.branch,
            paused_at_stage=None,
            accumulated_context=accumulated_context,
        )

    except RuntimeError as e:
        logger.error("Error running task '%s': %s", task.title, e)
        return TaskResult(
            task=task,
            stage_results=[],
            status=f"error: {e!s}",
            branch_name=task.branch,
            paused_at_stage=None,
            accumulated_context={},
        )


def topological_sort(tasks: List[Task]) -> List[Task]:
    """Sort tasks so that dependencies run before dependents.

    Args:
        tasks: list of tasks, possibly with depends_on references.

    Returns:
        List[Task]: Tasks in dependency-respecting order, with priority as tiebreaker.
    """
    branch_map: Dict[str, Task] = {t.branch: t for t in tasks}
    visited: set[str] = set()
    in_stack: set[str] = set()
    result: List[Task] = []

    def _visit(branch: str) -> None:
        if branch in in_stack:
            msg = f"Circular dependency detected involving '{branch}'"
            raise ValueError(msg)
        if branch in visited:
            return
        in_stack.add(branch)
        task = branch_map[branch]
        if task.depends_on and task.depends_on in branch_map:
            _visit(task.depends_on)
        in_stack.discard(branch)
        visited.add(branch)
        result.append(task)

    for task in sorted(tasks, key=lambda t: t.priority):
        if task.branch not in visited:
            _visit(task.branch)

    return result


def _retry_paused_task(
    paused_result: TaskResult,
    config: PipelineConfig,
    on_cycle_complete: Optional[Callable[[List[TaskResult]], None]],
    all_results: List[TaskResult],
    result_index: int,
) -> TaskResult:
    """Retry a single budget-paused task within the configured retry window.

    Blocks until the task either succeeds, fails, or the retry window expires.

    Returns:
        TaskResult: The final result after retrying.
    """
    start_time = time.monotonic()

    while True:
        time.sleep(config.retry_interval_minutes * 60)

        elapsed_hours = (time.monotonic() - start_time) / 3600.0
        if elapsed_hours >= config.retry_window_hours:
            logger.warning(
                "Retry window exhausted for task '%s'",
                paused_result.task.title,
            )
            final = TaskResult(
                task=paused_result.task,
                stage_results=paused_result.stage_results,
                status="budget_exhausted",
                branch_name=paused_result.branch_name,
                paused_at_stage=paused_result.paused_at_stage,
                accumulated_context=paused_result.accumulated_context,
            )
            all_results[result_index] = final
            if on_cycle_complete is not None:
                on_cycle_complete(all_results)
            return final

        task = paused_result.task
        wt_path = normalize_path(Path(task.project)).parent / ".worktrees" / task.branch
        logger.info(
            "Retrying task '%s' from stage '%s'",
            task.title,
            paused_result.paused_at_stage,
        )
        new_result = run_task(
            task,
            config,
            resume_from=paused_result.paused_at_stage,
            existing_context=paused_result.accumulated_context,
            worktree_path=wt_path,
        )
        all_results[result_index] = new_result
        if on_cycle_complete is not None:
            on_cycle_complete(all_results)

        if new_result.status != "paused":
            return new_result

        paused_result = new_result


def _check_dependency(
    task: Task,
    branch_to_result: Dict[str, TaskResult],
    results: List[TaskResult],
) -> bool:
    """Return True if the task's dependency is satisfied, recording a skip result if not.

    Returns:
        bool: True if the task may proceed, False if it was skipped.
    """
    if not task.depends_on:
        return True

    dep_result = branch_to_result.get(task.depends_on)
    dep_satisfied = dep_result is not None and dep_result.status == "success"
    if not dep_satisfied and dep_result is None:
        dep_satisfied = branch_exists(Path(task.project), task.depends_on)

    if not dep_satisfied:
        logger.warning(
            "Skipping task '%s' — dependency '%s' not met",
            task.title,
            task.depends_on,
        )
        skipped = TaskResult(
            task=task,
            stage_results=[],
            status="skipped_dependency",
            branch_name=task.branch,
            paused_at_stage=None,
            accumulated_context={},
        )
        results.append(skipped)
        branch_to_result[task.branch] = skipped
        return False

    task.base_branch = task.depends_on
    return True


def run_all_tasks(
    tasks: List[Task],
    config: PipelineConfig,
    on_cycle_complete: Optional[Callable[[List[TaskResult]], None]] = None,
    on_task_complete: Optional[Callable[[TaskResult], None]] = None,
    tasks_dir: Optional[Path] = None,
) -> List[TaskResult]:
    """Run all tasks respecting dependencies, retrying budget-paused tasks.

    When a task is paused due to budget depletion, subsequent tasks are held
    until the paused task finishes. If tasks_dir is provided, new task files
    added to the directory are discovered and appended after each task completes.

    Args:
        tasks: initial list of tasks to run.
        config: pipeline configuration.
        on_cycle_complete: optional callback invoked after each retry cycle with current results.
        on_task_complete: optional callback invoked immediately after each task finishes.
        tasks_dir: optional path to the tasks directory for reloading new tasks at runtime.

    Returns:
        List[TaskResult]: Results for every task processed, in execution order.
    """
    pending: List[Task] = list(tasks)
    results: List[TaskResult] = []
    branch_to_result: Dict[str, TaskResult] = {}
    seen_branches: set = {t.branch for t in pending}

    def _load_new_tasks() -> None:
        if tasks_dir is None:
            return
        for t in discover_tasks(tasks_dir):
            if t.branch not in seen_branches:
                pending.append(t)
                seen_branches.add(t.branch)
                logger.info("Discovered new task '%s' (branch=%s)", t.title, t.branch)

    while pending:
        sorted_pending = topological_sort(pending)
        pending.clear()

        for task in sorted_pending:
            if not _check_dependency(task, branch_to_result, results):
                continue

            logger.info("Starting task '%s' (priority=%d)", task.title, task.priority)
            result = run_task(task, config)
            results.append(result)
            branch_to_result[task.branch] = result

            if result.status == "paused":
                logger.info(
                    "Task '%s' paused — holding pipeline until it resumes",
                    task.title,
                )
                result_index = len(results) - 1
                result = _retry_paused_task(result, config, on_cycle_complete, results, result_index)
                branch_to_result[task.branch] = result

            if on_task_complete is not None:
                on_task_complete(result)

            _load_new_tasks()

        if on_cycle_complete is not None:
            on_cycle_complete(results)

    return results
