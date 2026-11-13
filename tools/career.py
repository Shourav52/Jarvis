"""Career pack: cover letter, tailored resume, job email, LinkedIn post, job search, tracker, interview mode."""
import json
import os
import re
from datetime import date, timedelta

import requests

from . import common, files, mail
from .common import copy_to_clipboard, data_path, llm_write, user_format
from .documents import create_document
from .sheets import create_spreadsheet
from .sources import fetch_text, job_text, resume_path, resume_text

USER_NAME = os.getenv("USER_NAME", "Shorov Saha")
STATUSES = ["wishlist", "applied", "interview", "offer", "rejected", "ghosted"]
ACTIVE = {"applied", "interview"}

TOOLS = [
    {"type": "function", "function": {
        "name": "write_cover_letter",
        "description": "Write a cover letter from the user's resume for a job and save it as a document.",
        "parameters": {"type": "object", "properties": {
            "job": {"type": "string", "description": "Job link, the word 'clipboard', or a short description"},
            "company": {"type": "string"}, "notes": {"type": "string"},
            "format": {"type": "string", "enum": ["docx", "pdf", "both"]}}, "required": ["job"]}}},
    {"type": "function", "function": {
        "name": "tailor_resume",
        "description": "Rewrite the user's resume for a job (only facts from the resume) and save it as a document.",
        "parameters": {"type": "object", "properties": {
            "job": {"type": "string"}, "company": {"type": "string"},
            "format": {"type": "string", "enum": ["docx", "pdf", "both"]}}, "required": ["job"]}}},
    {"type": "function", "function": {
        "name": "write_job_email",
        "description": "Write a job application email and stage it (not sent). The recipient must come from the user.",
        "parameters": {"type": "object", "properties": {
            "job": {"type": "string"}, "to": {"type": "string", "description": "Only an address the user said; else empty"},
            "notes": {"type": "string"}, "attach_resume": {"type": "boolean"}}, "required": ["job"]}}},
    {"type": "function", "function": {
        "name": "write_linkedin_post",
        "description": "Write a LinkedIn post about a project or achievement; shown in the terminal and copied.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string"}, "notes": {"type": "string"},
            "source_file": {"type": "string", "description": "Optional file name words, e.g. a project README"}},
            "required": ["topic"]}}},
    {"type": "function", "function": {
        "name": "find_jobs",
        "description": "Search for job/internship openings and rank them against the user's resume.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Role and skills, e.g. 'react intern'"},
            "location": {"type": "string", "description": "Only if the user said a place; never guess"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "log_application",
        "description": "Track a job application (company, role, status).",
        "parameters": {"type": "object", "properties": {
            "company": {"type": "string"}, "role": {"type": "string"},
            "status": {"type": "string", "enum": STATUSES}, "link": {"type": "string"},
            "notes": {"type": "string"}, "follow_up_days": {"type": "integer"}}, "required": ["company"]}}},
    {"type": "function", "function": {
        "name": "list_applications",
        "description": "List tracked applications, optionally by status.",
        "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": STATUSES}}}}},
    {"type": "function", "function": {
        "name": "update_application",
        "description": "Change the status, notes or follow-up of a tracked application (match by company).",
        "parameters": {"type": "object", "properties": {
            "company": {"type": "string"}, "status": {"type": "string", "enum": STATUSES},
            "notes": {"type": "string"}, "follow_up_days": {"type": "integer"}}, "required": ["company"]}}},
    {"type": "function", "function": {
        "name": "export_applications",
        "description": "Save the application tracker as an Excel file and open it.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "interview_mode",
        "description": "Turn mock-interview mode on/off (gives the user more time to answer).",
        "parameters": {"type": "object", "properties": {
            "on": {"type": "boolean"}, "role": {"type": "string"}}, "required": ["on"]}}},
]

HONESTY = ("Use ONLY facts that appear in the RESUME. Never invent employers, job titles, skills, tools, "
           "degrees, dates or numbers. If the job asks for something the resume does not show, do not claim it.")

COVER_SYSTEM = (
    "You write job application cover letters for {name}. " + HONESTY + " "
    "Write 3 short paragraphs, 180-230 words: (1) why this role/company, with one specific detail from the JOB; "
    "(2) the 2-3 most relevant projects or skills from the RESUME, concrete; (3) a confident close with a call to "
    "action. Plain, warm, specific; no cliches like 'passionate' or 'dynamic'. Start with 'Dear Hiring Manager,' "
    "unless a name is in the JOB, end with 'Sincerely,' and the name. Output only the letter.")

TAILOR_SYSTEM = (
    "You tailor resumes for {name}. " + HONESTY + " Reorder and rephrase to emphasise what the JOB needs; mirror JOB "
    "keywords only where the RESUME truly supports them. Keep it to one page. Output simple markdown: '# Name', one "
    "contact line, '## Summary' (2 lines), '## Skills', '## Projects' (bullets), '## Education', and any other "
    "sections the resume already has. Then a line '---GAPS---' followed by a short list of JOB requirements the "
    "resume does not show (for the user only).")

EMAIL_SYSTEM = (
    "You write short job application emails for {name}. " + HONESTY + " 90-140 words, polite and direct, one "
    "specific reason for this role, 1-2 relevant strengths from the RESUME. {attach} Output exactly: a first line "
    "'Subject: ...', a blank line, then the body ending with the name. No other text.")

POST_SYSTEM = (
    "You write LinkedIn posts for {name}, a software engineering student and MERN/Next.js developer. Use only the "
    "FACTS given; never invent metrics, users or results. 90-150 words, first person, a one-line hook, short "
    "paragraphs: what I built, the tech, one honest lesson, a closing question. 3-5 hashtags, at most 2 emojis. "
    "Mention ONLY technologies and features that appear in FACTS. Plain text: no markdown, no ** or headings. "
    "Output only the post.")

RANK_SYSTEM = (
    "You help {name} find jobs. From the numbered SEARCH RESULTS pick up to 5 that are real job or internship "
    "postings and fit the RESUME best (skip articles, lists, expired-looking pages). Reply with ONLY a JSON array, "
    'best first: [{{"n": <result number>, "why": "<max 15 words>"}}]. Use only result numbers that exist.')


def _fmt(args):
    """User 'PDF' bolle PDF-i, LLM ja-i dhorna kano."""
    return user_format() or (args.get("format") if args.get("format") in ("docx", "pdf", "both") else "docx")


# ------------------------------------------------------------------ writers
def write_cover_letter(args):
    try:
        resume, rname = resume_text()
        job = job_text(args.get("job"))
    except ValueError as e:
        return str(e)
    print("[Cover letter likha hocche...]")
    letter = llm_write(COVER_SYSTEM.format(name=USER_NAME),
                       f"RESUME ({rname}):\n{resume}\n\nJOB:\n{job}\n\nNOTES FROM USER: {args.get('notes') or 'none'}")
    title = f"Cover Letter {args.get('company') or ''}".strip()
    return create_document({"title": title, "content": letter, "format": _fmt(args)}) + f" Written from {rname}."


def tailor_resume(args):
    try:
        resume, rname = resume_text()
        job = job_text(args.get("job"))
    except ValueError as e:
        return str(e)
    print("[Resume tailor hocche...]")
    out = llm_write(TAILOR_SYSTEM.format(name=USER_NAME), f"RESUME ({rname}):\n{resume}\n\nJOB:\n{job}", 2200)
    doc, _, gaps = out.partition("---GAPS---")
    title = f"Resume {args.get('company') or 'tailored'}".strip()
    msg = create_document({"title": title, "content": doc.strip(), "format": _fmt(args)})
    gaps = gaps.strip()
    return msg + (f" Gaps (job needs, resume does not show): {gaps[:500]}" if gaps else "")


def write_job_email(args):
    try:
        resume, rname = resume_text()
        job = job_text(args.get("job"))
    except ValueError as e:
        return str(e)
    attach = bool(args.get("attach_resume", True))
    print("[Email likha hocche...]")
    out = llm_write(EMAIL_SYSTEM.format(name=USER_NAME, attach="Mention that the resume is attached." if attach else ""),
                    f"RESUME ({rname}):\n{resume}\n\nJOB:\n{job}\n\nNOTES FROM USER: {args.get('notes') or 'none'}", 900)
    m = re.match(r"\s*Subject:\s*(.+?)\n+(.*)", out, re.S | re.I)
    subject, body = (m.group(1).strip(), m.group(2).strip()) if m else ("Application", out)
    return mail.stage_email(args.get("to"), subject, body, attach)


def write_linkedin_post(args):
    from .notes import memory_prompt
    facts = (args.get("topic") or "") + "\n" + (args.get("notes") or "")
    if args.get("source_file"):
        found = files._search(args["source_file"], None)[0]
        if found:
            path = found[0][2]
            facts += "\n\nPROJECT FILE:\n" + files._extract(path, os.path.splitext(path)[1].lower())[:3000]
    mem = memory_prompt()
    if len(facts.strip()) + len(mem) < 250:
        return ("I only know the project's name, not what it does, and I will not invent details. Ask the user for "
                "the tech stack, what it does and one thing they learned (they can also say 'remember that my "
                "project is ...' so I keep it).")
    print("[LinkedIn post likha hocche...]")
    post = llm_write(POST_SYSTEM.format(name=USER_NAME), f"FACTS:\n{facts}\n\nKNOWN ABOUT THE USER:\n{mem}", 900, 0.7)
    post = re.sub(r"\*\*|__|`", "", post)
    print("\n----- LINKEDIN POST -----\n" + post + "\n-------------------------\n")
    copy_to_clipboard(post)
    return "The post is written, shown in the terminal and copied to the clipboard. Offer to adjust the tone or length."


# ------------------------------------------------------------------ job search
def find_jobs(args):
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return "Web search is not set up (TAVILY_API_KEY missing)."
    place = (args.get("location") or os.getenv("JOB_LOCATION") or "Bangladesh").strip()
    query = f"{args.get('query', '')} {place} job opening apply".strip()
    print(f"[Jobs khujchi: {query}]")
    domains = ["bdjobs.com", "linkedin.com", "indeed.com", "glassdoor.com", "wellfound.com",
               "remoteok.com", "weworkremotely.com", "internshala.com"]
    results = []
    for body in ({"include_domains": domains, "time_range": "month"}, {"include_domains": domains}, {}):
        try:
            r = requests.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {key}"},
                              json={"query": query, "max_results": 8, **body}, timeout=25)
            if r.status_code == 400 and body:
                continue
            r.raise_for_status()
            results = r.json().get("results", [])[:8]
        except Exception as e:
            return f"Job search failed: {e}"
        if len(results) >= 3:
            break
    if not results:
        return "I found no job postings for that. Try different words."
    listing = "\n".join(f"{i}. {x.get('title', '')} | {(x.get('content') or '')[:220]}"
                        for i, x in enumerate(results, 1))
    try:
        resume, _ = resume_text(3500)
    except ValueError:
        resume = "(resume not found)"
    picks = []
    try:
        raw = llm_write(RANK_SYSTEM.format(name=USER_NAME), f"RESUME:\n{resume}\n\nSEARCH RESULTS:\n{listing}", 700, 0.2)
        for it in json.loads(re.search(r"\[.*\]", raw, re.S).group(0)):
            n = int(it["n"])
            if 1 <= n <= len(results) and n not in [p[0] for p in picks]:
                picks.append((n, str(it.get("why", ""))[:120]))
    except Exception:
        picks = [(i, "") for i in range(1, min(4, len(results) + 1))]
    # Title ar URL shobshomoy asol search result theke (LLM er banano na)
    lines = [f"{results[n - 1].get('title', '')} - {why} - {results[n - 1].get('url', '')}".replace(" -  - ", " - ")
             for n, why in picks[:5]]
    text = "\n".join(lines)
    print(f"\n----- JOB SHORTLIST ({place}) -----\n" + text + "\n-------------------------\n")
    return ("Shortlist (also shown in the terminal; summarise the top 2-3 aloud, no URLs, and offer to log them "
            "as wishlist): " + text)


# ------------------------------------------------------------------ tracker
def _apps():
    p = data_path("applications.json")
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p, encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save(apps):
    json.dump(apps, open(data_path("applications.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def log_application(args):
    company = (args.get("company") or "").strip()
    if not company:
        return "Which company?"
    role = (args.get("role") or "").strip()
    status = args.get("status") if args.get("status") in STATUSES else "applied"
    days = args.get("follow_up_days")
    if days is None:
        days = 7 if status == "applied" else None
    follow = (date.today() + timedelta(days=int(days))).isoformat() if days else ""
    apps = _apps()
    for a in apps:
        if a["company"].lower() == company.lower() and a["role"].lower() == role.lower():
            a.update(status=status, follow_up=follow or a["follow_up"],
                     link=args.get("link") or a["link"], notes=args.get("notes") or a["notes"])
            _save(apps)
            return f"Updated {company}: {status}."
    apps.append({"id": max([a["id"] for a in apps], default=0) + 1, "company": company, "role": role,
                 "status": status, "date": date.today().isoformat(), "follow_up": follow,
                 "link": args.get("link") or "", "notes": args.get("notes") or ""})
    _save(apps)
    print(f"[Application logged: {company}]")
    return f"Logged {company}{' - ' + role if role else ''} as {status}." + (f" Follow-up on {follow}." if follow else "")


def list_applications(args):
    apps = _apps()
    if args.get("status"):
        apps = [a for a in apps if a["status"] == args["status"]]
    if not apps:
        return "No applications tracked yet."
    return f"Count: {len(apps)}\n" + "\n".join(
        f"{a['id']}. {a['company']}{' - ' + a['role'] if a['role'] else ''} [{a['status']}]"
        + (f" follow-up {a['follow_up']}" if a["follow_up"] else "") for a in apps)


def update_application(args):
    key = (args.get("company") or "").lower().strip()
    apps = _apps()
    hits = [a for a in apps if key and key in a["company"].lower()]
    if not hits:
        return "No tracked application matched that company."
    if len(hits) > 1:
        return "More than one matched: " + "; ".join(f"{a['company']} - {a['role']}" for a in hits)
    a = hits[0]
    if args.get("status") in STATUSES:
        a["status"] = args["status"]
        if a["status"] not in ACTIVE:
            a["follow_up"] = ""
    if args.get("notes"):
        a["notes"] = args["notes"]
    if args.get("follow_up_days") is not None:
        a["follow_up"] = (date.today() + timedelta(days=int(args["follow_up_days"]))).isoformat()
    _save(apps)
    return f"Updated {a['company']}: {a['status']}" + (f", follow-up {a['follow_up']}." if a["follow_up"] else ".")


def export_applications(args):
    apps = _apps()
    if not apps:
        return "No applications to export."
    rows = [[a["company"], a["role"], a["status"], a["date"], a["follow_up"], a["link"], a["notes"]] for a in apps]
    return create_spreadsheet({"title": "Job Applications",
                               "headers": ["Company", "Role", "Status", "Applied", "Follow-up", "Link", "Notes"],
                               "rows": rows})


def due_follow_ups():
    today = date.today().isoformat()
    return [a for a in _apps() if a["status"] in ACTIVE and a["follow_up"] and a["follow_up"] <= today]


def pending_brief():
    """Din er prothom 'Hey Jarvis' e ekbar: follow-up due ar open task er sonkha."""
    state_path = data_path("state.json")
    try:
        state = json.load(open(state_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    today = date.today().isoformat()
    if state.get("brief_date") == today:
        return ""
    state["brief_date"] = today
    json.dump(state, open(state_path, "w", encoding="utf-8"))
    parts = []
    due = due_follow_ups()
    if due:
        names = ", ".join(a["company"] for a in due[:3])
        parts.append(f"{len(due)} job follow-up{'s' if len(due) > 1 else ''} due: {names}")
    from .notes import _load_tasks
    open_tasks = [t for t in _load_tasks() if not t["done"]]
    if open_tasks:
        parts.append(f"{len(open_tasks)} open task{'s' if len(open_tasks) > 1 else ''}")
    return ("Sir, you have " + " and ".join(parts) + ".") if parts else ""


# ------------------------------------------------------------------ interview mode
_interview = False


def interview_mode(args):
    global _interview
    _interview = bool(args.get("on"))
    print(f"[Interview mode: {'on' if _interview else 'off'}]")
    return "Interview mode on. Ask the first question now." if _interview else "Interview mode off."


def interview_active():
    return _interview


def set_interview(on):
    global _interview
    _interview = bool(on)


HANDLERS = {
    "write_cover_letter": write_cover_letter, "tailor_resume": tailor_resume,
    "write_job_email": write_job_email, "write_linkedin_post": write_linkedin_post,
    "find_jobs": find_jobs, "log_application": log_application, "list_applications": list_applications,
    "update_application": update_application, "export_applications": export_applications,
    "interview_mode": interview_mode,
}
