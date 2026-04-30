"""Logging configuration using loguru."""

from pathlib import Path

from loguru import logger


def setup_logging(log_dir: Path) -> None:
    """Configure loguru with rotating file output.

    Args:
        log_dir: Directory for log files.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "n1700_bridge_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | "
            "{name}:{function}:{line} | {extra[part_id]!s:>20} | {message}"
        ),
        level="DEBUG",
        backtrace=True,
        diagnose=True,
    )

    # Configure default extra context
    logger.configure(extra={"part_id": ""})
