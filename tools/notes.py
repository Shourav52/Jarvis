"""Notes, to-do list and long-term memory (plain files in data/)."""
import json
import os
from datetime import datetime

from .common import data_path

TOOLS = [
    {"type": "function", "function": {
        "name": "add_note",
        "description": "Save a note for the user.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "list_notes",
        "description": "Read back the user's saved notes (latest first), optionally filtered by a word.",
        "parameters": {"type": "object", "properties": {
            "count": {"type": "integer"}, "search": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "add_task",
        "description": "Add a to-do task.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "due": {"type": "string", "description": "Optional due date/time in words"}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "list_tasks",
        "description": "List the user's to-do tasks (open ones unless include_done is true).",
        "parameters": {"type": "object", "properties": {"include_done": {"type": "boolean"}}}}},
    {"type": "function", "function": {
        "name": "complete_task",
        "description": "Mark a task done, by its number or by words from its text.",
        "parameters": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}}},
    {"type": "function", "function": {
        "name": "delete_task",
        "description": "Delete a task, by its number or words from its text.",
        "parameters": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}}},
    {"type": "function", "function": {
        "name": "delete_notes",
        "description": "Delete notes containing some text, or all notes (all=true needs confirm=true after the user said yes).",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}, "all": {"type": "boolean"}, "confirm": {"type": "boolean"}}}}},
    {"type": "function", "function": {
        "name": "remember",
        "description": "Save a long-term fact about the user. Only when the user explicitly asks you to remember something.",
        "parameters": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}}},
    {"type": "function", "function": {
        "name": "forget",
        "description": "Delete remembered facts that contain the given text.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
]


# ---------- notes ----------
def add_note(args):
    text = (args.get("text") or "").strip()
    if not text:
        return "Nothing to save."
    with open(data_path("notes.md"), "a", encoding="utf-8") as f:
        f.write(f"- [{datetime.now():%Y-%m-%d %H:%M}] {text}\n")
    print(f"[Note saved: {text[:50]}]")
    return "Note saved."


def list_notes(args):
    path = data_path("notes.md")
    if not os.path.exists(path):
        return "No notes yet."
    lines = [l.rstrip() for l in open(path, encoding="utf-8") if l.strip()]
    term = (args.get("search") or "").lower()
    if term:
        lines = [l for l in lines if term in l.lower()]
    total = len(lines)
    lines = lines[-int(args.get("count") or 10):][::-1]
    if not lines:
        return "No matching notes."
    return f"Notes found: {total} (showing {len(lines)})\n" + "\n".join(lines)


# ---------- tasks ----------
def _load_tasks():
    path = data_path("tasks.json")
    if not os.path.exists(path):
        return []
    try:
        return json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_tasks(tasks):
    json.dump(tasks, open(data_path("tasks.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def add_task(args):
    text = (args.get("text") or "").strip()
    if not text:
        return "Nothing to add."
    tasks = _load_tasks()
    new_id = max([t["id"] for t in tasks], default=0) + 1
    tasks.append({"id": new_id, "text": text, "due": args.get("due") or "", "done": False,
                  "created": f"{datetime.now():%Y-%m-%d %H:%M}"})
    _save_tasks(tasks)
    print(f"[Task added: {text[:50]}]")
    return f"Task {new_id} added."


def list_tasks(args):
    tasks = _load_tasks()
    if not args.get("include_done"):
        tasks = [t for t in tasks if not t["done"]]
    if not tasks:
        return "No open tasks. Count: 0"
    head = f"Count: {len(tasks)} {'tasks' if args.get('include_done') else 'open tasks'}\n"
    return head + "\n".join(
        f"{t['id']}. {'[done] ' if t['done'] else ''}{t['text']}" + (f" (due: {t['due']})" if t["due"] else "")
        for t in tasks)


def complete_task(args):
    key = str(args.get("task") or "").strip().lower()
    tasks = _load_tasks()
    open_tasks = [t for t in tasks if not t["done"]]
    matches = [t for t in open_tasks if key == str(t["id"]) or (key and key in t["text"].lower())]
    if not matches:
        return "No open task matched that."
    if len(matches) > 1:
        return "More than one task matched: " + "; ".join(f"{t['id']}. {t['text']}" for t in matches)
    matches[0]["done"] = True
    _save_tasks(tasks)
    print(f"[Task done: {matches[0]['text'][:50]}]")
    return f"Marked done: {matches[0]['text']}"


def delete_task(args):
    key = str(args.get("task") or "").strip().lower()
    tasks = _load_tasks()
    matches = [t for t in tasks if key == str(t["id"]) or (key and key in t["text"].lower())]
    if not matches:
        return "No task matched that."
    if len(matches) > 1:
        return "More than one task matched: " + "; ".join(f"{t['id']}. {t['text']}" for t in matches)
    _save_tasks([t for t in tasks if t is not matches[0]])
    print(f"[Task deleted: {matches[0]['text'][:50]}]")
    return f"Deleted task: {matches[0]['text']}"


def delete_notes(args):
    path = data_path("notes.md")
    if not os.path.exists(path):
        return "No notes to delete."
    lines = [l.rstrip() for l in open(path, encoding="utf-8") if l.strip()]
    term = (args.get("text") or "").strip().lower()
    if args.get("all"):
        if not args.get("confirm"):
            return "Ask the user to confirm deleting ALL notes (yes/no) first."
        open(path, "w", encoding="utf-8").close()
        print(f"[All notes deleted: {len(lines)}]")
        return f"Deleted all {len(lines)} notes."
    if not term:
        return "Tell me which note to delete, or confirm deleting all notes."
    keep = [l for l in lines if term not in l.lower()]
    open(path, "w", encoding="utf-8").write("\n".join(keep) + ("\n" if keep else ""))
    print(f"[Notes deleted: {len(lines) - len(keep)}]")
    return f"Deleted {len(lines) - len(keep)} note(s)."


# ---------- memory ----------
MEMORY_LIMIT = 60


def _memory_lines():
    path = data_path("memory.md")
    if not os.path.exists(path):
        return []
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip()]


def remember(args):
    fact = (args.get("fact") or "").strip()
    if not fact:
        return "Nothing to remember."
    lines = _memory_lines()
    if any(fact.lower() == l[2:].lower() for l in lines):
        return "Already remembered."
    lines.append(f"- {fact}")
    open(data_path("memory.md"), "w", encoding="utf-8").write("\n".join(lines[-MEMORY_LIMIT:]) + "\n")
    print(f"[Remembered: {fact[:50]}]")
    return "Remembered."


def forget(args):
    term = (args.get("text") or "").strip().lower()
    if not term:
        return "Tell me what to forget."
    lines = _memory_lines()
    keep = [l for l in lines if term not in l.lower()]
    open(data_path("memory.md"), "w", encoding="utf-8").write("\n".join(keep) + ("\n" if keep else ""))
    return f"Forgot {len(lines) - len(keep)} item(s)."


def memory_prompt():
    """System prompt e jog korar jonno remembered facts."""
    lines = _memory_lines()
    if not lines:
        return ""
    return "Facts the user asked you to remember:\n" + "\n".join(lines)


HANDLERS = {
    "add_note": add_note, "list_notes": list_notes, "add_task": add_task,
    "list_tasks": list_tasks, "complete_task": complete_task,
    "delete_task": delete_task, "delete_notes": delete_notes,
    "remember": remember, "forget": forget,
}