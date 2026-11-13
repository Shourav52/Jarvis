"""Shared helpers for all Jarvis tools."""
import os
import re
import subprocess
import sys
import time
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


# ---- jarvis.py ekhane set kore ----
USER_TEXTS = []        # shesh kichu user message (email recipient ke user bolechhe kina check korte)
LLM = None             # OpenAI-compatible client
LLM_MODEL = ""
TURN = 0               # prottek user proshne +1 (email "yes" approval er jonno)
LAST_USER_TEXT = ""


def note_user_text(text):
    global LAST_USER_TEXT
    LAST_USER_TEXT = text
    USER_TEXTS.append(text)
    del USER_TEXTS[:-6]


def user_format():
    """User er message e 'PDF' / 'doc' / 'both' thakle seta-i final (LLM vul dhorle o)."""
    t = (LAST_USER_TEXT or "").lower()
    pdf = bool(re.search(r"\bpdf\b", t))
    doc = bool(re.search(r"\b(docx?|docs?|word)\b", t))
    if (pdf and doc) or ("both" in t and (pdf or doc)):
        return "both"
    return "pdf" if pdf else "docx" if doc else None


def llm_write(system, user, max_tokens=1800, temperature=0.5):
    """Alada ekta LLM call, shudhu lekhar jonno (cover letter, email ...). Main conversation e token bochay."""
    if LLM is None:
        raise RuntimeError("LLM client set hoyni")
    kw = dict(model=LLM_MODEL, temperature=temperature, max_tokens=max_tokens,
              messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    if LLM_MODEL.startswith("openai/gpt-oss"):
        kw["extra_body"] = {"reasoning_effort": "low", "include_reasoning": False}
    for attempt in range(3):
        try:
            r = LLM.chat.completions.create(**kw)
            break
        except Exception as e:
            msg = str(e)
            if "reasoning" in msg.lower() and "extra_body" in kw:
                kw.pop("extra_body")
                continue
            m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", msg)
            if m and attempt < 2 and ("429" in msg or "rate" in msg.lower()):
                wait = int(m.group(1) or 0) * 60 + float(m.group(2))
                if wait <= 25:
                    print(f"(Groq rate limit: {wait:.0f}s opekkha...)")
                    time.sleep(wait + 0.5)
                    continue
            raise
    text = (r.choices[0].message.content or "").strip()
    return re.sub(r"^```\w*\n|\n```$", "", text).strip()


def copy_to_clipboard(text):
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
        return True
    except Exception:
        return False