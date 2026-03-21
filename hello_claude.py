import logging
import subprocess  # noqa: S404

log_format = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logging.getLogger().handlers[-1].setFormatter(logging.Formatter(log_format))

logger = logging.getLogger(__name__)


def hello_claude() -> None:
    """Send a greeting to claude haiku to keep the session timer alive."""
    cmd = (
        "source /var/services/homes/janbrejcha/.bashrc && claude --model claude-haiku-4-5 -p 'hi claude, how are you?'"
    )
    result = subprocess.run(  # noqa: S603
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        check=False,
    )

    logger.info(result.stdout)
    if result.returncode != 0:
        logger.error(result.stderr)


if __name__ == "__main__":
    hello_claude()
