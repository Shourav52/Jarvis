"""Resume, job description (link / clipboard / text) pawar helper."""
import ipaddress
import os
import re
import socket
import subprocess
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from . import common, files

UA = {"User-Agent": "Mozilla/5.0 (Jarvis assistant)"}


def _generated(path):
    """Jarvis nijer banano file (tailored resume, cover letter) 'asol resume' hishebe nibe na."""
    low = os.path.basename(path).lower()
    docs = os.path.abspath(common.DOCS_DIR) + os.sep
    return os.path.abspath(path).startswith(docs) or "tailored" in low or "cover" in low


def resume_path():
    """RESUME_PATH (.env) ba Desktop/Documents/Downloads theke 'resume' naamer PDF/DOCX."""
    p = os.getenv("RESUME_PATH")
    if p:
        p = os.path.expanduser(p)
        return p if os.path.isfile(p) else None
    for q in ("resume", "cv"):
        found = files._search(q, None)[0]
        found = [f for f in found if os.path.splitext(f[2])[1].lower() in (".pdf", ".docx")
                 and not _generated(f[2])]
        if found:
            return found[0][2]
    return None


def resume_text(limit=6000):
    path = resume_path()
    if not path:
        raise ValueError("I could not find your resume. Put it in Documents or Downloads, "
                         "or set RESUME_PATH in the .env file.")
    text = files._extract(path, os.path.splitext(path)[1].lower()).strip()
    if len(text) < 50:
        raise ValueError("Your resume file has no readable text.")
    return text[:limit], os.path.basename(path)


def read_clipboard(limit=6000):
    if sys.platform != "darwin":
        return ""
    try:
        return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout.strip()[:limit]
    except Exception:
        return ""


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}

    def __init__(self):
        super().__init__()
        self.parts, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in ("p", "br", "li", "div", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth and data.strip():
            self.parts.append(data.strip() + " ")


def _is_public(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def fetch_text(url, limit=6000):
    """Job post page porar jonno. Shudhu public http(s); local network / file:// block."""
    for _ in range(4):                        # max 3 redirect, prottek ta check kore
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname or not _is_public(p.hostname):
            raise ValueError("I can only read public web pages.")
        try:
            r = requests.get(url, timeout=15, headers=UA, allow_redirects=False, stream=True)
        except requests.RequestException as e:
            raise ValueError(f"Could not open that page: {e}")
        if 300 <= r.status_code < 400 and r.headers.get("Location"):
            url = urljoin(url, r.headers["Location"])
            continue
        raw = b""
        for chunk in r.iter_content(65536):
            raw += chunk
            if len(raw) > 1_500_000:
                break
        parser = _Text()
        parser.feed(raw.decode(r.encoding or "utf-8", errors="ignore"))
        text = re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", "".join(parser.parts))).strip()
        if len(text) < 300:
            raise ValueError("That page looks empty or needs a login. Copy the job text and say 'clipboard'.")
        return text[:limit]
    raise ValueError("Too many redirects.")


def job_text(job):
    """job = link, 'clipboard', ba chhoto description."""
    job = (job or "").strip()
    if not job:
        raise ValueError("Which job? Give a link, say 'clipboard' after copying the job text, or describe it.")
    if re.match(r"^https?://", job, re.I):
        return fetch_text(job)
    if "clipboard" in job.lower() or job.lower() in ("copied", "the copied text", "what i copied"):
        t = read_clipboard()
        if not t:
            raise ValueError("The clipboard is empty. Copy the job description first.")
        return t
    return job[:6000]

