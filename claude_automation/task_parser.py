from pathlib import Path
import re
from typing import List, Optional, Union

import yaml

from .config import Task, VALID_STAGES


def _parse_depends_on(value: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [v.strip() for v in value if v.strip()]
    parts = [v.strip() for v in value.split(",") if v.strip()]
    return parts or None


FRONTMATTER_PARTS = 3


def slugify(title: str) -> str:
    """Convert a title string to a URL-friendly slug.

    Returns:
        str: Lowercased, hyphenated slug with special characters removed.
    """
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def parse_task(file_path: Path) -> Task:
    """Parse a markdown task file with YAML frontmatter and return a Task instance.

    Returns:
        Task: Parsed task object populated from frontmatter and body.

    Raises:
        ValueError: If frontmatter is missing, malformed, or required fields are absent.
    """
    content = file_path.read_text(encoding="utf-8")

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) < FRONTMATTER_PARTS:
            msg = f"Invalid frontmatter in {file_path}"
            raise ValueError(msg)
        frontmatter_str = parts[1]
        description = parts[2].strip()
    else:
        msg = f"No frontmatter found in {file_path}"
        raise ValueError(msg)

    try:
        frontmatter = yaml.safe_load(frontmatter_str) or {}
    except yaml.YAMLError as e:
        msg = f"Failed to parse YAML frontmatter in {file_path}: {e}"
        raise ValueError(msg) from e

    if "title" not in frontmatter:
        msg = f"Missing required field 'title' in {file_path}"
        raise ValueError(msg)

    if "project" not in frontmatter:
        msg = f"Missing required field 'project' in {file_path}"
        raise ValueError(msg)

    title = frontmatter["title"]
    project = frontmatter["project"]
    branch = frontmatter.get("branch", f"auto/{slugify(title)}")
    model = frontmatter.get("model", "claude-sonnet-4-5-20250514")
    budget_per_stage = float(frontmatter.get("budget_per_stage", 1.0))
    priority = int(frontmatter.get("priority", 10))
    stages = frontmatter.get("stages", list(VALID_STAGES))

    invalid = [s for s in stages if s not in VALID_STAGES]
    if invalid:
        msg = f"Invalid stage(s) {invalid} in {file_path}. Valid stages: {VALID_STAGES}"
        raise ValueError(msg)

    return Task(
        title=title,
        project=project,
        branch=branch,
        model=model,
        budget_per_stage=budget_per_stage,
        priority=priority,
        stages=stages,
        description=description,
        base_branch=frontmatter.get("base_branch", None),
        depends_on=_parse_depends_on(frontmatter.get("depends_on", None)),
        source_path=str(file_path),
    )


def discover_tasks(tasks_dir: Path) -> List[Task]:
    """Discover and parse all markdown task files in the given directory.

    Returns:
        List[Task]: Tasks sorted by priority ascending.
    """
    tasks = []
    for md_file in tasks_dir.glob("*.md"):
        task = parse_task(md_file)
        tasks.append(task)
    tasks.sort(key=lambda t: t.priority)
    return tasks
