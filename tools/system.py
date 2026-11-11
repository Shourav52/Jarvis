"""open_app, open_url, set_timer (macOS)."""
import subprocess
import sys
import threading
import webbrowser

TOOLS = [
    {"type": "function", "function": {
        "name": "open_app",
        "description": "Open an application on the user's Mac, e.g. 'Visual Studio Code', 'Safari', 'Spotify'.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "open_url",
        "description": "Open a website in the browser.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
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


HANDLERS = {"open_app": open_app, "open_url": open_url, "set_timer": set_timer}
