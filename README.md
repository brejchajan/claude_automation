# Claude Automation

Autonomous pipeline for running Claude Code agents overnight. Define tasks as
`.md` files, and the pipeline runs them through configurable stages (plan, code,
review, test) in isolated git worktrees. Each task produces a feature branch for
human review.

## Setup

```bash
conda create -n claude_pipeline python=3.12 -y
conda activate claude_pipeline
pip install -e .
```

Requires the `claude` CLI to be available in your shell (sourced via `~/.bashrc`).

## Usage

Run all commands from the root of the project you want to automate. Tasks, logs,
and completed task archives are stored relative to the current directory.

### Run immediately

Process all task files in `tasks/`:

```bash
claude-automation --now
```

Run a single task:

```bash
claude-automation --task tasks/my_task.md
```

### Scheduled execution

Start the scheduler (default: 2 AM daily):

```bash
claude-automation
```

Override the schedule with a standard cron expression (`minute hour day month weekday`):

```bash
claude-automation --cron "0 3 * * *"   # run at 3 AM daily
claude-automation --cron "0 2 * * 1"   # run at 2 AM every Monday
```

The scheduler blocks the terminal and triggers the pipeline on each matching time.
To run it as a background service, wrap it in a system cron job or a process manager such as `systemd` or `supervisor`.

## Task file format

Place `.md` files in the `tasks/` directory. Each file uses YAML frontmatter:

```markdown
---
title: My feature                          # required
project: /absolute/path/to/target/repo     # required
branch: FEAT-0001                          # optional, auto-generated from title
base_branch: master                        # optional, auto-detected from repo
model: claude-sonnet-4-6                   # optional, default: claude-sonnet-4-5-20250514
budget_per_stage: 1.0                      # optional, USD per stage
priority: 1                                # optional, lower runs first
stages: [planner, coder, reviewer, tester] # optional, default: all four
---

## Description
What needs to be done.

## Acceptance Criteria
- Criterion 1
- Criterion 2

## Context
Additional project context.
```

### Available stages

| Stage | What it does |
|-------|-------------|
| `planner` | Explores the codebase, produces an implementation plan (read-only) |
| `coder` | Implements the task according to the plan |
| `reviewer` | Reviews the git diff, fixes issues found |
| `tester` | Runs tests, creates missing tests, fixes failures |

Stages can be customized per task. For example, `stages: [planner, coder]` skips
review and testing.

### Target repository requirements

The target repository specified in `project` must:
- Exist on disk
- Be initialized as a git repo
- Have at least one commit

## How it works

1. The pipeline discovers `.md` task files and sorts them by priority.
2. For each task, a **git worktree** is created (the main branch is never touched).
3. Configured stages run sequentially. Each stage invokes `claude -p` with
   appropriate tool permissions and a safety prompt.
4. Output from each stage is passed as context to the next stage.
5. On completion, changes are committed to the feature branch in the worktree.
6. A summary report is written to `logs/`.

### Safety

- A safety prompt is injected into every agent call (no file deletion without
  backup, no access outside the working directory, no user questions, no
  destructive git commands).
- Each stage has a budget limit (`--max-budget-usd`).
- Each stage has a timeout (default: 30 minutes).
- The planner stage is read-only (permission mode `plan`).

### Budget depletion and retries

If a stage fails due to budget depletion, the task is paused. The pipeline
retries paused tasks once per hour for up to 12 hours (configurable). On retry,
execution resumes from the stage that was interrupted.

## Reports

After each run, a report is generated in `logs/<timestamp>/`:

```
logs/2026-03-21_020000/
  summary.md                    # overview table of all tasks
  command-line-calculator/      # per-task directory
    planner_output.json
    coder_output.json
    reviewer_output.json
    tester_output.json
```

## Project structure

```
claude_automation/
  main.py           # CLI entrypoint with APScheduler
  pipeline.py       # Orchestrates stages per task, retry logic
  agents.py         # Subprocess wrapper for claude -p
  worktree.py       # Git worktree create/cleanup/commit/diff
  config.py         # Dataclasses and defaults
  task_parser.py    # Parses .md task files
  reporting.py      # Generates summary reports
  hello_claude.py   # Timer reset utility (see below)
  tasks/            # Task .md files
  tests/            # Unit and integration tests
  logs/             # Generated reports (gitignored)
```

## Tests

```bash
conda activate claude_pipeline
pip install -e ".[dev]"
pytest tests/ -v
```

## hello_claude.py

A standalone utility that sends a short prompt to Claude Haiku to reset the
Claude Code 5-hour inactivity timer. This is intended to be scheduled as a
**cron job** that runs periodically (e.g., every 4 hours) to keep the session
alive:

```cron
0 */4 * * * /opt/anaconda3/envs/claude_pipeline/bin/python /Users/janbrejcha/devel/claude_automation/hello_claude.py
```

This is independent from the pipeline and has no effect on task execution.
