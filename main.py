import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import default_pipeline_config, PipelineConfig
from pipeline import run_all_tasks
from reporting import generate_report
from task_parser import discover_tasks, parse_task


def run_pipeline(config: PipelineConfig, task_file: Optional[str] = None) -> None:
    """Discover tasks and run the full pipeline, writing a report when done."""
    logs_dir = Path(config.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(logs_dir / "pipeline.log")
    stream_handler = logging.StreamHandler(sys.stdout)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[file_handler, stream_handler],
    )

    logger = logging.getLogger(__name__)

    tasks = [parse_task(Path(task_file))] if task_file is not None else discover_tasks(Path(config.tasks_dir))

    if not tasks:
        logger.warning("No tasks found.")
        return

    logger.info("Starting pipeline with %d tasks", len(tasks))

    results = run_all_tasks(tasks, config)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    report_path = generate_report(results, timestamp, logs_dir)

    logger.info("Pipeline complete. Report: %s", report_path)


def main() -> None:
    """Parse CLI arguments and either run the pipeline immediately or schedule it."""
    parser = argparse.ArgumentParser(description="Claude automation pipeline")
    parser.add_argument("--now", action="store_true", help="Run pipeline immediately")
    parser.add_argument("--task", type=str, default=None, help="Path to a single task .md file")
    parser.add_argument("--cron", type=str, default=None, help="Override schedule cron expression")
    args = parser.parse_args()

    config = default_pipeline_config()

    if args.now or args.task is not None:
        run_pipeline(config, args.task)
    else:
        cron = args.cron if args.cron is not None else config.schedule_cron
        scheduler = BlockingScheduler()
        scheduler.add_job(run_pipeline, CronTrigger.from_crontab(cron), args=(config,))
        scheduler.start()


if __name__ == "__main__":
    main()
