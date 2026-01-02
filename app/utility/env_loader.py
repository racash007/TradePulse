# File: `app/utility/env_loader.py`
from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def load_project_env(env_filename: str) -> None:
    """
    Load environment variables for the project.

    Priority:
    1. IDE-provided env file via environment variables (e.g. PYCHARM_ENV_FILE or ENV_FILE).
    2. Project root .env located one level up from the `app/` package.

    This function is safe to call multiple times and logs what it loads.
    """
    try:
        # 1) IDE-provided env file (some IDE/run configs export a path)
        ide_env_path: Optional[str] = os.environ.get('PYCHARM_ENV_FILE') or os.environ.get('ENV_FILE')
        if ide_env_path:
            p = Path(ide_env_path)
            if p.exists():
                load_dotenv(dotenv_path=p)
                logger.debug("Loaded env from IDE path: %s", p)
                return
            else:
                logger.debug("IDE env path provided but does not exist: %s", p)

        # 2) Default project-root .env (one level up from this module, i.e. project root)
        env_path = Path(env_filename).resolve()
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            logger.debug("Loaded env from project root: %s", env_path)
        else:
            logger.debug("No .env found at %s", env_path)
    except Exception:
        logger.exception("Failed loading environment file")
