import logging
import subprocess
from pathlib import Path

log_format = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logging.getLogger().handlers[-1].setFormatter(logging.Formatter(log_format))

def hello_claude():
    result = subprocess.run(
        ["bash", "-c", "source /var/services/homes/janbrejcha/.bashrc && claude --model claude-haiku-4-5 -p 'hi claude, how are you?'"],
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    logging.info(result.stdout)
    if result.returncode != 0:
        print("Error:", result.stderr)


if __name__ == "__main__":
    hello_claude()
