import os
import tomllib
from pathlib import Path

from fastapi.templating import Jinja2Templates


def _app_version() -> str:
    env = os.environ.get("SETSEEKER_VERSION")
    if env:
        return env.removeprefix("v")
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    return "dev"


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["app_version"] = _app_version()
