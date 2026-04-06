---
name: create-task
description: Creates a new task file in the tasks/ directory following the project's task format. Use when asked to create a task, add a task, write a new ticket, or plan a new feature/work item.
---

# Skill: Create Task

## Task File Format

Every task lives at `tasks/<PREFIX>-XXXX.md` with YAML frontmatter followed by a Markdown body.
The `<PREFIX>` and directory are project-specific — check existing task files to determine the convention used in this project.

### Frontmatter

```yaml
---
title: Short imperative title describing the deliverable
project: <absolute path to the project root>
branch: <PREFIX>-XXXX
depends_on: <PREFIX>-YYYY        # or "master" if no dependency
model: claude-sonnet-4-6         # default to sonnet; pick opus only for hard tasks (see "Choose the model" below)
budget_per_stage: 100.0
priority: <integer, matches ticket number>
stages: [planner, coder, reviewer]    # see Stages section below
---
```

### Stages

Choose stages based on task type:

| Task type | stages |
|-----------|--------|
| Any script / automation / testable work | `[planner, coder, reviewer, tester]` |
| Pure documentation / planning | `[planner, reviewer]` |
| Non-automatable implementation (e.g. GUI, hardware) | `[planner, coder, reviewer]` |

**Rule: add `tester` to any task whose output can be automatically verified** — this includes virtually all scripts, CLI tools, data pipelines, and validation scripts.

### Body Sections

```markdown
## Description

One or two sentences explaining the goal and scope. Then a numbered list of
concrete requirements — each requirement maps to a specific file, command, or
behaviour.

## Acceptance Criteria

Bulleted list of verifiable outcomes. Each criterion must be checkable (you can
determine pass/fail without ambiguity).

## Context

Depends on <PREFIX>-XXXX (brief reason). Key domain facts, file paths, data
shapes, constant values, or design constraints the implementer needs to know.
Do NOT duplicate information already in the codebase or CLAUDE.md.

## Manual QA

Short, concrete checklist a human can run after the ticket is implemented to
verify it works end-to-end. See "Write the Manual QA section" below for what
to include and what to leave out.
```

## Instructions

### 1. Determine the next task ID

Look at the existing task files in `tasks/` and pick the next sequential ID.
Match the prefix and zero-padding convention already in use.

### 2. Choose stages carefully

- Does the task produce a script, data file, or any output that a script could check? → add `tester`.
- Is it a non-automatable change only (GUI, embedded/hardware)? → omit `tester`.
- When in doubt, add `tester` — it is cheaper to have an unused stage than to ship untested code.

### 2b. Choose the model (don't waste opus on easy tasks)

**Default: `claude-sonnet-4-6`.** Sonnet handles the vast majority of tickets.
Only escalate to `claude-opus-4-6` when the task genuinely needs extra reasoning.

Use **sonnet** when:
- The work is mechanical: schema additions, additive parsing, renames, small refactors.
- The algorithm is fully specified in the ticket and the implementer just has to type it out.
- The task is one new file ≲ 300 LOC with no tricky integration points.
- Self-contained scripts with deterministic I/O and a clear acceptance test.

Use **opus** when:
- The change touches a hot, tangled code path with many side effects where one wrong move silently corrupts data.
- Multiple subsystems must be coordinated in one ticket.
- The design space is open and the implementer must make non-trivial trade-offs not pinned down by the ticket.
- Subtle numerical work: tolerances, calibration math, geometric transforms with multiple coordinate spaces.
- Anything safety-sensitive (auth, persistence migrations, anything destructive on user data).

If you find yourself writing "this should be straightforward" in the Context section, it's a sonnet task.

### 3. Write the Description requirements as numbered steps

Each step should name the concrete artefact produced:
- "Create `scripts/foo.py` that ..."
- "Add module `bar` with interface ..."
- "Run the linter and fix all errors, then re-run the script."

For Python tasks, always include a step like:
> Run the script and verify it produces correct output. Run `ruff check` and
> fix all linting errors, then re-run to confirm everything still works.

### 4. Write Acceptance Criteria as verifiable bullets

Good: "Script produces `output/foo.json` with keys `x`, `y`, `z`."
Bad:  "Script works correctly."

### 5. Write the Context section

- State which earlier task this depends on and why (one sentence).
- Include exact file paths, constants, data shapes, and numeric values the implementer must match.
- If a validation script was written in a prior task, reference it by name.

### 5b. Write the Manual QA section

Every task gets a `## Manual QA` section. Keep it **short and concrete** —
this is for a human to run after the agent finishes, not a substitute for the
acceptance criteria.

Include:
- The exact build / test / run command(s) the human should execute.
- One numbered walkthrough per user-visible scenario the ticket affects.
  Each step says **what to do** and **what to expect**.
- Any output file the human should open and inspect, with the exact key/value to look for.
- For features with backward-compatibility requirements: a "regression check" sub-section
  that walks through the legacy code path.

Skip:
- Anything already covered by automated tests in the `tester` stage.
- Restating the acceptance criteria.
- Vague instructions like "verify it looks right" — say what to look at.

For tickets with no user-visible behaviour change (pure refactors, schema widening,
internal additions), Manual QA is allowed to be very short: just a run command and
"confirm no regressions."

For tickets with multiple paths (optional inputs, mode toggles, fallbacks):
cover **each path** with its own short numbered walkthrough.

### 6. Create the file

Write to `tasks/<PREFIX>-XXXX.md` where XXXX is the zero-padded ID matching the project convention.

## Examples

### Python script task (sonnet, has `tester`)

```markdown
---
title: Export processed dataset to Parquet
project: /path/to/project
branch: PROJ-0012
depends_on: PROJ-0011
model: claude-sonnet-4-6
budget_per_stage: 100.0
priority: 12
stages: [planner, coder, reviewer, tester]
---

## Description

Export the cleaned dataset produced by PROJ-0011 to a partitioned Parquet file.

Requirements:

1. Create `scripts/export_dataset.py` that:
   - Loads the cleaned CSV from `data/cleaned.csv`.
   - Writes a Parquet file to `data/processed/dataset.parquet`.
   - Prints row count and column names after writing.
2. Run `ruff check scripts/export_dataset.py` and fix all issues, then
   re-run the script to confirm it still works.

## Acceptance Criteria

- `data/processed/dataset.parquet` is produced by the script.
- Row count matches the cleaned CSV.
- No ruff linting errors.

## Context

Depends on PROJ-0011 (cleaning script produced `data/cleaned.csv`).
Expected columns: `id`, `timestamp`, `value`. Expected row count: ~50 000.

## Manual QA

1. Run `python scripts/export_dataset.py`. Expect the script to print row count
   and column names and exit with code 0.
2. Open `data/processed/dataset.parquet` in a notebook and confirm `len(df) == len(cleaned_csv)`.
3. Run `ruff check scripts/export_dataset.py`. Expect no errors.
```

### Complex multi-subsystem task (opus, has `tester`)

Opus is justified because the change coordinates data ingestion, model inference,
and output serialisation in one ticket with subtle numeric requirements.

```markdown
---
title: Integrate FooModel inference into the processing pipeline
project: /path/to/project
branch: PROJ-0020
depends_on: PROJ-0019
model: claude-opus-4-6
budget_per_stage: 100.0
priority: 20
stages: [planner, coder, reviewer, tester]
---

## Description

Wire FooModel inference into the existing processing pipeline so that each
batch is annotated with model predictions before being written to disk.

Requirements:

1. Extend `pipeline/processor.py` to load `models/foo.onnx` at startup and
   run inference on each batch (input `[B, C, H, W]` float32, output `[B, N]` float32).
2. Serialise predictions alongside existing batch output in `data/output/<id>.json`.
3. Run `ruff check pipeline/processor.py` and fix all issues, then re-run end-to-end.

## Acceptance Criteria

- Each output JSON contains a `predictions` key with shape `[N]` per sample.
- Max latency increase per batch < 50 ms on CPU.
- No ruff linting errors.

## Context

Depends on PROJ-0019 (`models/foo.onnx` downloaded and validated). Input
normalisation: mean `[0.485, 0.456, 0.406]`, std `[0.229, 0.224, 0.225]`.
Reference preprocessing in `scripts/validate_foo.py`.

## Manual QA

1. Run `python -m pipeline.processor --input data/samples/`. Expect output JSON
   files in `data/output/` each containing a `predictions` list.
2. Open one output file and confirm `len(predictions) == N` (N from model output shape).
3. Re-run on the same input. Expect output to be overwritten, no crash.
```

## Quick Checklist

- [ ] ID is next sequential number, zero-padded to match project convention
- [ ] `depends_on` names the correct prior task (or `master`)
- [ ] `model` is `claude-sonnet-4-6` unless the task meets one of the "use opus" criteria
- [ ] `stages` includes `tester` for any script/automatable task
- [ ] Each Description requirement names a concrete file or command
- [ ] Python tasks include a "run ruff check and fix" step
- [ ] Acceptance Criteria are verifiable (not "works correctly")
- [ ] Context includes exact file paths and numeric constants
- [ ] `## Manual QA` section is present, short, concrete, and covers each user-visible path
