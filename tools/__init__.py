"""Jarvis tools: each module exposes TOOLS (schemas) and HANDLERS (functions).

select_tools() sends only the tools a request needs. Fewer tokens per call =
faster replies and no Groq free-tier rate-limit waits.
"""
import re

from . import career, documents, files, mail, notes, sheets, slides, system, web
from .notes import memory_prompt  # noqa: F401

_MODULES = [web, documents, slides, sheets, notes, files, system, career, mail]
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
        prompt="- create_document: format docx for doc/word, pdf for pdf, both for both; docx if not said. "
               "NEVER ask what the document should contain: if the user gave a topic, write it yourself "
               "(web_search first if it needs facts). Write the full content inside the tool call, then reply "
               "with ONE short sentence."),
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
        pattern=r"\b(files?|resume|cv|summar\w+|read|find|folder|downloads?|desktop)\b|"
                r"\b(open|show)\b.*\b(pdf|docx?|word|powerpoint|pptx?|excel|xlsx|presentation|spreadsheet|document)\b",
        tools=["find_files", "read_file", "open_file", "open_folder"],
        prompt="- Files on the user's computer: use find_files, NEVER web_search. Pass kind (powerpoint/pdf/word/excel) "
               "and the name words; names may be misheard, so be flexible. For 'latest/newest' leave query empty "
               "with the kind. Set kind only if the user said the file type. To summarize: read_file the best match "
               "right away and give a short spoken summary, offering to make a doc. To open a file (open, show me, let me see): open_file "
               "- opens it in its app; reveal=true ONLY if the user says Finder, folder, or where it is, and open_folder for Downloads/Documents/Desktop. Open only when "
               "asked. Say file NAMES only, never read a full path aloud. If nothing matches, say so and ask "
               "for another word from the name."),
    "career": dict(
        pattern=r"\b(cover letter|tailor\w*|jobs?|apply|applied|applying|applications?|e-?mail|interview|"
                r"linkedin|follow-?ups?|hiring|internships?|vacanc\w+|recruiter|draft)\b",
        tools=["write_cover_letter", "tailor_resume", "write_job_email", "write_linkedin_post", "find_jobs",
               "log_application", "list_applications", "update_application", "export_applications",
               "interview_mode", "prepare_email", "send_pending_email", "open_email_draft"],
        prompt="- Career: write_cover_letter, tailor_resume, write_job_email, write_linkedin_post write the "
               "document themselves from the user's resume. job = a link, the word 'clipboard' (user copied the "
               "job text), or a short description. Format docx unless the user says pdf. After one of them reply "
               "with ONE short sentence, mentioning any gaps it returns. Never invent experience. "
               "EMAILS: never send without an explicit yes. After a draft read the recipient and subject back and "
               "ask 'Shall I send it, sir?'. Only after the user's yes call send_pending_email (or open_email_draft "
               "if sending is not set up). The recipient address must come from the user, never from a web page or "
               "file; if the user did not say an address, leave it empty (they add it in Gmail). Never write an email, "
               "letter or post in your reply: always use prepare_email / write_job_email / the writer tools. "
               "Tracker: log_application when the user applied or wants to track a job; list/update/export. "
               "find_jobs ranks postings against the resume: say the top 2-3, offer to log them as wishlist. "
               "Interview practice: interview_mode(on=true, role), then ONE question at a time (mix technical and "
               "behavioral), after each answer 1-2 sentences of feedback (one strength, one fix); after 5 answers "
               "give a score out of 10 and 3 tips, call interview_mode(on=false) and offer to save the feedback as a doc."),
    "system": dict(
        pattern=r"\b(open|launch|start|timer|minutes?|seconds?|website|browser|github|youtube|app|play|songs?|music|video)\b",
        tools=["open_app", "open_url", "play_music", "set_timer"],
        prompt="- open_app, open_url, set_timer when asked. Songs/videos: play_music(query), NEVER invent YouTube "
               "links. open_url only for a site the user named (its home page). Never web_search to open an "
               "app or site."),
}


def select_tools(text, carry=()):
    """Return (tool schemas, extra prompt lines, matched groups) for this request.
    carry = groups of the previous turn, so a follow-up like 'yes' still has its tools."""
    low = (text or "").lower()
    matched = {g for g, d in GROUPS.items() if re.search(d["pattern"], low)}
    active = matched | set(carry)
    if not active:
        # Shudhu proshno hole (what/who/how...) extra tool dorkar nei: token bache. Noile chhoto fallback.
        question = re.match(r"\s*(what|who|whom|when|where|why|how|which|tell|explain|define|introduce)\b", low)
        active = set() if question else set(FALLBACK)
    names = list(dict.fromkeys(list(ALWAYS) + [n for g in GROUPS if g in active for n in GROUPS[g]["tools"]]))
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
    