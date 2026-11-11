"""Jarvis tools: each module exposes TOOLS (schemas) and HANDLERS (functions).

select_tools() sends only the tools a request needs. Fewer tokens per call =
faster replies and no Groq free-tier rate-limit waits.
"""
import re

from . import documents, files, notes, sheets, slides, system, web
from .notes import memory_prompt  # noqa: F401

_MODULES = [web, documents, slides, sheets, notes, files, system]
TOOLS = [t for m in _MODULES for t in m.TOOLS]
HANDLERS = {k: v for m in _MODULES for k, v in m.HANDLERS.items()}
_BY_NAME = {t["function"]["name"]: t for t in TOOLS}
MAX_RESULT_CHARS = 12000

ALWAYS = ["web_search"]
FALLBACK = ["notes", "system"]
GROUPS = {
    "docs": dict(
        pattern=r"\b(docs?|documents?|word|pdf|report|essay|article|letter)\b",
        tools=["create_document"],
        prompt="- create_document: format docx for doc/word, pdf for pdf, both for both. If the format "
               "is not said, ask. Write the full content inside the tool call, then reply with ONE short sentence."),
    "slides": dict(
        pattern=r"\b(slides?|deck|presentation|powerpoint|pptx?)\b",
        tools=["create_presentation"],
        prompt="- create_presentation: exactly the number of slides asked (default 6). First slide layout title, "
               "last closing, vary the layouts. Palette by topic: midnight tech/security, forest health/nature, "
               "coral marketing/creative, terracotta culture/food, ocean business/data, charcoal formal, "
               "teal education, berry design/lifestyle. Slide text short: titles max 7 words, card headings "
               "max 4 words, card text max 18 words. Reply with ONE short sentence after."),
    "sheets": dict(
        pattern=r"\b(spreadsheets?|excel|xlsx|sheet|table|expenses|budget)\b",
        tools=["create_spreadsheet"],
        prompt="- create_spreadsheet: from table data the user gives or that you research. Reply with ONE short sentence after."),
    "notes": dict(
        pattern=r"\b(tasks?|to-?dos?|notes?|remind\w*|remember|forget|delete|done|complete\w*|list|how many|clear)\b",
        tools=["add_note", "list_notes", "add_task", "list_tasks", "complete_task",
               "delete_task", "delete_notes", "remember", "forget"],
        prompt="- Tasks: add_task for any task, to-do, or reminder item; add_note only when the user says note. "
               "NEVER state how many tasks or notes there are, or what they say, from memory: call list_tasks or "
               "list_notes first and use its count. To delete ALL notes, ask yes/no first, then delete_notes "
               "with all=true and confirm=true. Use remember/forget only when explicitly asked."),
    "files": dict(
        pattern=r"\b(files?|resume|cv|summar\w+|read|find|folder|downloads?|desktop|open|show)\b",
        tools=["find_files", "read_file", "open_file", "open_folder"],
        prompt="- Files on the user's computer: use find_files, NEVER web_search. Pass kind (powerpoint/pdf/word/excel) "
               "and the name words; names may be misheard, so be flexible. For 'latest/newest' leave query empty "
               "with the kind. Set kind only if the user said the file type. To summarize: read_file the best match "
               "right away and give a short spoken summary, offering to make a doc. To open a file (open, show me, let me see): open_file "
               "- opens it in its app; reveal=true ONLY if the user says Finder, folder, or where it is, and open_folder for Downloads/Documents/Desktop. Open only when "
               "asked. Say file NAMES only, never read a full path aloud. If nothing matches, say so and ask "
               "for another word from the name."),
    "system": dict(
        pattern=r"\b(open|launch|start|timer|minutes?|seconds?|website|browser|github|youtube|app)\b",
        tools=["open_app", "open_url", "set_timer"],
        prompt="- open_app, open_url, set_timer when asked."),
}


def select_tools(text, carry=()):
    """Return (tool schemas, extra prompt lines, matched groups) for this request.
    carry = groups of the previous turn, so a follow-up like 'yes' still has its tools."""
    low = (text or "").lower()
    matched = {g for g, d in GROUPS.items() if re.search(d["pattern"], low)}
    active = matched | set(carry)
    if not active:
        active = set(FALLBACK)
    names = list(ALWAYS) + [n for g in GROUPS if g in active for n in GROUPS[g]["tools"]]
    prompt = "\n".join(GROUPS[g]["prompt"] for g in GROUPS if g in active)
    return [_BY_NAME[n] for n in names], prompt, matched


def run_tool(name, args):
    fn = HANDLERS.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    print(f"[tool: {name}]")
    try:
        return str(fn(args or {}))[:MAX_RESULT_CHARS]
    except Exception as e:  # tool error LLM ke bole dey, program crash kore na
        return f"Tool {name} failed: {e}"
    
    