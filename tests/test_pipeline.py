from typing import List, Optional
import unittest
from unittest.mock import MagicMock, patch

from config import default_pipeline_config, StageResult, Task
from pipeline import build_stage_prompt, run_all_tasks, run_task


def make_test_task(stages: Optional[List[str]] = None, **kwargs) -> Task:
    defaults = dict(
        title="Test Task",
        project="/tmp/test_project",
        branch="auto/test-task",
        model="claude-sonnet-4-5-20250514",
        budget_per_stage=1.0,
        priority=10,
        stages=stages or ["planner", "coder", "reviewer", "tester"],
        description="Test description",
    )
    defaults.update(kwargs)
    return Task(**defaults)


def make_success_result(stage: str, output: str = "done") -> StageResult:
    return StageResult(
        stage=stage,
        success=True,
        output=output,
        error="",
        duration_seconds=1.0,
        return_code=0,
        budget_depleted=False,
    )


class TestBuildStagePrompt(unittest.TestCase):
    def setUp(self) -> None:
        self.config = default_pipeline_config()
        self.task = make_test_task()

    def test_build_stage_prompt_planner(self) -> None:
        prompt = build_stage_prompt(self.task, "planner", self.config, {})
        self.assertIn("Test description", prompt)
        self.assertIn(self.config.stages["planner"].system_prompt, prompt)

    def test_build_stage_prompt_reviewer_includes_diff(self) -> None:
        prompt = build_stage_prompt(
            self.task, "reviewer", self.config, {}, diff="diff --git a/file.py"
        )
        self.assertIn("diff --git a/file.py", prompt)
        self.assertIn("## Git Diff", prompt)

    def test_build_stage_prompt_with_context(self) -> None:
        context = {"planner": "Step 1: do something"}
        prompt = build_stage_prompt(self.task, "coder", self.config, context)
        self.assertIn("Step 1: do something", prompt)
        self.assertIn("## Prior Stage Context", prompt)
        self.assertIn("### planner Output", prompt)


@patch("pipeline.cleanup_worktree")
@patch("pipeline.get_diff", return_value="")
@patch("pipeline.commit_worktree", return_value=True)
@patch("pipeline.create_worktree", return_value=MagicMock())
@patch("pipeline.run_agent")
class TestRunTask(unittest.TestCase):
    def setUp(self) -> None:
        self.config = default_pipeline_config()
        self.task = make_test_task()

    def test_run_task_all_stages_success(
        self,
        mock_agent: MagicMock,
        mock_create: MagicMock,
        mock_commit: MagicMock,
        mock_diff: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        mock_agent.side_effect = [
            make_success_result("", "plan output"),
            make_success_result("", "code output"),
            make_success_result("", "review output"),
            make_success_result("", "test output"),
        ]
        result = run_task(self.task, self.config)
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.stage_results), 4)
        self.assertEqual(result.stage_results[0].stage, "planner")
        self.assertEqual(result.stage_results[3].stage, "tester")

    def test_run_task_custom_stages(
        self,
        mock_agent: MagicMock,
        mock_create: MagicMock,
        mock_commit: MagicMock,
        mock_diff: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        task = make_test_task(stages=["planner", "coder"])
        mock_agent.side_effect = [
            make_success_result("", "plan"),
            make_success_result("", "code"),
        ]
        result = run_task(task, self.config)
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.stage_results), 2)

    def test_run_task_stage_failure(
        self,
        mock_agent: MagicMock,
        mock_create: MagicMock,
        mock_commit: MagicMock,
        mock_diff: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        mock_agent.side_effect = [
            make_success_result("", "plan"),
            StageResult(
                stage="",
                success=False,
                output="",
                error="failed",
                duration_seconds=1.0,
                return_code=1,
                budget_depleted=False,
            ),
        ]
        result = run_task(self.task, self.config)
        self.assertEqual(result.status, "failed_at_coder")
        self.assertEqual(len(result.stage_results), 2)

    def test_run_task_budget_depleted(
        self,
        mock_agent: MagicMock,
        mock_create: MagicMock,
        mock_commit: MagicMock,
        mock_diff: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        mock_agent.return_value = StageResult(
            stage="",
            success=True,
            output="partial",
            error="",
            duration_seconds=1.0,
            return_code=0,
            budget_depleted=True,
        )
        result = run_task(self.task, self.config)
        self.assertEqual(result.status, "paused")
        self.assertEqual(result.paused_at_stage, "planner")

    def test_run_task_context_passing(
        self,
        mock_agent: MagicMock,
        mock_create: MagicMock,
        mock_commit: MagicMock,
        mock_diff: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        mock_agent.side_effect = [
            make_success_result("", "planner output text"),
            make_success_result("", "coder output"),
            make_success_result("", "reviewer output"),
            make_success_result("", "tester output"),
        ]
        result = run_task(self.task, self.config)
        self.assertEqual(result.status, "success")
        coder_call = mock_agent.call_args_list[1]
        coder_prompt = coder_call[0][1]
        self.assertIn("planner output text", coder_prompt)


@patch("pipeline.cleanup_worktree")
@patch("pipeline.get_diff", return_value="")
@patch("pipeline.commit_worktree", return_value=True)
@patch("pipeline.create_worktree", return_value=MagicMock())
@patch("pipeline.run_agent")
class TestRunAllTasks(unittest.TestCase):
    def setUp(self) -> None:
        self.config = default_pipeline_config()

    def test_run_all_tasks_sorted_by_priority(
        self,
        mock_agent: MagicMock,
        mock_create: MagicMock,
        mock_commit: MagicMock,
        mock_diff: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        task_high = make_test_task(priority=20, title="High Priority")
        task_low = make_test_task(priority=5, title="Low Priority")
        mock_agent.return_value = make_success_result("", "done")
        results = run_all_tasks([task_high, task_low], self.config)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].task.title, "Low Priority")
        self.assertEqual(results[1].task.title, "High Priority")

    @patch("pipeline.time")
    def test_run_all_tasks_retry_on_budget(
        self,
        mock_time: MagicMock,
        mock_agent: MagicMock,
        mock_create: MagicMock,
        mock_commit: MagicMock,
        mock_diff: MagicMock,
        mock_cleanup: MagicMock,
    ) -> None:
        task = make_test_task(stages=["planner"])
        budget_result = StageResult(
            stage="",
            success=True,
            output="partial",
            error="",
            duration_seconds=1.0,
            return_code=0,
            budget_depleted=True,
        )
        success_result = make_success_result("", "done")
        mock_agent.side_effect = [budget_result, success_result]
        mock_time.monotonic.side_effect = [0.0, 0.0, 100.0]
        mock_time.sleep = MagicMock()
        results = run_all_tasks([task], self.config)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "success")
        mock_time.sleep.assert_called()


if __name__ == "__main__":
    unittest.main()
