import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


def load_config(project_root: Path | None = None) -> dict:
    if project_root is None:
        project_root = Path(__file__).parent.parent

    load_dotenv(project_root / ".env")

    config_path = project_root / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Resolve relative paths against project root
    paths = config.get("paths", {})
    for key in paths:
        paths[key] = str(project_root / paths[key])

    # Inject env vars
    config["zlib_email"] = os.getenv("ZLIB_EMAIL", "")
    config["zlib_password"] = os.getenv("ZLIB_PASSWORD", "")
    config["zlib_remix_userid"] = os.getenv("ZLIB_REMIX_USERID", "")
    config["zlib_remix_userkey"] = os.getenv("ZLIB_REMIX_USERKEY", "")

    return config
