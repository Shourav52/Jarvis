"""Shared helpers for all Jarvis tools."""
import os
import re
import subprocess
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "documents")   # banano file gulo ekhane
DATA_DIR = os.path.join(BASE_DIR, "data")        # notes, tasks, memory ekhane


def output_path(title, ext):
    os.makedirs(DOCS_DIR, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", title or "").strip("_")[:40] or "file"
    return os.path.join(DOCS_DIR, f"{slug}_{datetime.now():%Y%m%d_%H%M%S}.{ext}")


def data_path(name):
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, name)


POST_CREATE = os.getenv("POST_CREATE", "open")   # "open" = file nijei khule dey, "reveal" = Finder e dekhay, "none"


def launch(path, reveal=False):
    """File ke default app e kholey (PDF -> Preview, pptx -> PowerPoint/Keynote). (ok, error) ferot dey."""
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["open", "-R", path] if reveal else ["open", path],
                               capture_output=True, text=True, timeout=15)
            return r.returncode == 0, r.stderr.strip()
        if sys.platform.startswith("win"):
            os.startfile(os.path.dirname(path) if reveal else path)  # noqa: S606
            return True, ""
        r = subprocess.run(["xdg-open", os.path.dirname(path) if reveal else path],
                           capture_output=True, text=True, timeout=15)
        return r.returncode == 0, r.stderr.strip()
    except Exception as e:
        return False, str(e)


def after_create(path):
    """Notun file banar por: khule dey (default), Finder e dekhay, ba kichu kore na."""
    if POST_CREATE == "none":
        return ""
    ok, err = launch(path, reveal=(POST_CREATE == "reveal"))
    if not ok:
        print(f"(file khola gelo na: {err})")
        return ""
    return " It is now open on the screen." if POST_CREATE == "open" else " Shown in Finder."