"""open_app, open_url, set_timer (macOS)."""
import json
import re
import subprocess
import sys
import threading
import webbrowser
from urllib.parse import quote_plus

import requests

TOOLS = [
    {"type": "function", "function": {
        "name": "open_app",
        "description": "Open an application on the user's Mac, e.g. 'Visual Studio Code', 'Safari', 'Spotify'.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "open_url",
        "description": "Open a website the user named (its home page). Never invent deep links or video IDs.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "play_music",
        "description": "Play a song or video: opens the top YouTube result for the search words.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "set_timer",
        "description": "Set a timer or reminder that notifies the user after some minutes (works while Jarvis is running).",
        "parameters": {"type": "object", "properties": {
            "minutes": {"type": "number"}, "label": {"type": "string", "description": "What to remind about"}},
            "required": ["minutes"]}}},
]


def open_app(args):
    name = (args.get("name") or "").strip()
    if sys.platform != "darwin":
        return "Opening apps is only supported on Mac for now."
    if not name:
        return "Which app?"
    print(f"[Opening app: {name}]")
    r = subprocess.run(["open", "-a", name], capture_output=True, text=True)
    return f"Opened {name}." if r.returncode == 0 else f"Could not find an app called {name}."


def open_url(args):
    url = (args.get("url") or "").strip()
    if not url:
        return "Which website?"
    if "://" not in url:
        url = "https://" + url
    if not url.lower().startswith(("http://", "https://")):
        return "I can only open http or https links."
    print(f"[Opening: {url}]")
    webbrowser.open(url)
    return f"Opened {url}."


def play_music(args):
    """YouTube er asol top result kholey. (LLM er banano video ID kokhono na: oita Rick Roll dey.)"""
    q = (args.get("query") or "").strip()
    if not q:
        return "What should I play?"
    video, title = None, ""
    try:
        r = requests.get("https://www.youtube.com/results", params={"search_query": q}, timeout=10,
                         headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"})
        m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})"', r.text)
        if m:
            video = m.group(1)
            t = re.search(r'"videoId":"%s".{0,1500}?"title":\{"runs":\[\{"text":"(.*?)"\}' % video, r.text, re.S)
            if t:
                try:
                    title = json.loads('"' + t.group(1) + '"')
                except ValueError:
                    title = t.group(1)
    except requests.RequestException:
        pass
    url = f"https://www.youtube.com/watch?v={video}" if video else f"https://www.youtube.com/results?search_query={quote_plus(q)}"
    print(f"[Playing: {title or q}]")
    webbrowser.open(url)
    return f"Playing '{title or q}' on YouTube." if video else f"Opened the YouTube search for '{q}'."


def _fire(label):
    msg = label or "Time is up"
    print(f"\n[Timer done: {msg}]")
    if sys.platform == "darwin":
        safe = msg.replace("\\", " ").replace('"', " ")
        subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "Jarvis timer"'])
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"])
        subprocess.run(["say", f"Timer done. {safe}"])


def set_timer(args):
    try:
        minutes = float(args.get("minutes"))
    except (TypeError, ValueError):
        return "How many minutes?"
    minutes = min(max(minutes, 0.1), 24 * 60)
    label = (args.get("label") or "").strip()
    t = threading.Timer(minutes * 60, _fire, args=(label,))
    t.daemon = True
    t.start()
    print(f"[Timer set: {minutes:g} min {label}]")
    return f"Timer set for {minutes:g} minutes. It only works while Jarvis stays running."


HANDLERS = {"open_app": open_app, "open_url": open_url, "play_music": play_music, "set_timer": set_timer}