"""Job application email: draft -> user er 'yes' -> Gmail SMTP diye pathano (ba Gmail compose khola)."""
import mimetypes
import os
import re
import smtplib
import ssl
import time
import urllib.parse
import webbrowser
from email.message import EmailMessage

from . import common
from .common import copy_to_clipboard, launch
from .sources import resume_path

TOOLS = [
    {"type": "function", "function": {
        "name": "prepare_email",
        "description": "Stage an email draft (shown in the terminal, NOT sent). Use for ANY email. "
                       "Leave 'to' empty unless the user said the address; never invent one.",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string", "description": "Address the user said, or 'me'. Empty if unknown."},
            "subject": {"type": "string"}, "body": {"type": "string"},
            "attach_resume": {"type": "boolean"}}, "required": ["subject", "body"]}}},
    {"type": "function", "function": {
        "name": "send_pending_email",
        "description": "Send the staged email. Only after the user has said yes to it in a LATER message.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "open_email_draft",
        "description": "Open the staged email as a Gmail compose window (when sending from Jarvis is not set up).",
        "parameters": {"type": "object", "properties": {}}}},
]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PLACEHOLDER_RE = re.compile(r"@(example\.(com|org|net)|test\.com|domain\.com|email\.com|mail\.com|"
                            r"yourmail\.com|yourcompany\.com|company\.com)$|^(name|user|you|someone|recipient)@", re.I)
YES_RE = re.compile(r"\b(yes|yeah|yep|yup|send|go ahead|confirm|sure|okay|ok|do it)\b", re.I)
NO_RE = re.compile(r"\b(no|nope|don't|dont|do not|cancel|stop|wait|not yet)\b", re.I)
EXPIRY_SEC = 900
_pending = None


def _clean_address(to):
    """'me' = nijer Gmail. Voice e bola 'name at gmail dot com' ke name@gmail.com banay."""
    to = (to or "").strip()
    if to.lower() in ("me", "myself", "my email", "my own email", "my gmail", "self"):
        return os.getenv("GMAIL_ADDRESS") or ""
    if "@" not in to:
        to = re.sub(r"\s+at\s+", "@", to, flags=re.I)
    to = re.sub(r"\s+dot\s+", ".", to, flags=re.I)
    return to.replace(" ", "").lower().rstrip(".")


def _spoken(text):
    t = re.sub(r"\s+at\s+", "@", (text or "").lower())
    t = re.sub(r"\s+dot\s+", ".", t)
    return re.sub(r"\s+", "", t)


def _said_by_user(to):
    own = (os.getenv("GMAIL_ADDRESS") or "").strip().lower()
    return (own and to == own) or to in _spoken(" ".join(common.USER_TEXTS))


def stage_email(to, subject, body, attach_resume=False):
    """Draft toiri kore rakhe. Pathay na."""
    global _pending
    to = _clean_address(to)
    if to:
        if not EMAIL_RE.match(to) or PLACEHOLDER_RE.search(to):
            return ("That is not a usable email address. Ask the user for the real address, "
                    "or stage the draft without one so they can fill it in Gmail.")
        if not _said_by_user(to):
            return ("I will not use an address the user did not say. Ask the user for the recipient's address "
                    "(or say 'me'), or stage the draft with 'to' empty so they add it in Gmail.")
    attach = None
    if attach_resume:
        attach = resume_path()
        if not attach:
            return "I could not find your resume to attach. Set RESUME_PATH in the .env file."
    _pending = {"to": to, "subject": subject.strip(), "body": body.strip(),
                "attach": attach, "turn": common.TURN, "time": time.time()}
    text = f"To: {to or '(blank: add it in Gmail)'}\nSubject: {subject.strip()}\n" + (f"Attachment: {os.path.basename(attach)}\n" if attach else "") \
           + f"\n{body.strip()}\n"
    print("\n----- EMAIL DRAFT (pathano hoyni) -----\n" + text + "---------------------------------------\n")
    copy_to_clipboard(text)
    addr, pw = _creds()
    ask = ("Read the recipient and subject back and ask the user whether to send it. Do NOT send yet."
           if addr and pw else
           "Sending from Jarvis is not set up, so read the recipient and subject back and ask whether to open "
           "it in Gmail so the user can press Send. Use open_email_draft after their yes; do not call send_pending_email.")
    return (f"Draft ready{' for ' + to if to else ' (no recipient yet)'}, subject '{subject.strip()}'"
            + (f", with {os.path.basename(attach)} attached" if attach else "")
            + f". It is shown in the terminal and copied to the clipboard. {ask}")


def prepare_email(args):
    return stage_email(args.get("to"), args.get("subject") or "", args.get("body") or "",
                       bool(args.get("attach_resume")))


def _creds():
    pw = re.sub(r"\s+", "", os.getenv("GMAIL_APP_PASSWORD") or "")   # Google space diye dekhay, space lage na
    return (os.getenv("GMAIL_ADDRESS") or "").strip(), pw


def _ssl_context():
    """Mac e python.org Python er nijer certificate list thake na (CERTIFICATE_VERIFY_FAILED). certifi use kori."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _smtp_send(addr, pw, msg):
    """465 (SSL) age, connection bondho hole 587 (STARTTLS). Password vul hole retry kore na."""
    ports = [587, 465] if os.getenv("GMAIL_SMTP_PORT") == "587" else [465, 587]
    last, ctx = None, _ssl_context()
    for port in ports:
        try:
            if port == 465:
                s = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30, context=ctx)
            else:
                s = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
                s.starttls(context=ctx)
            with s:
                s.login(addr, pw)
                s.send_message(msg)
            return
        except smtplib.SMTPAuthenticationError:
            raise
        except (smtplib.SMTPServerDisconnected, OSError) as e:
            last = e
    raise last


def send_pending_email(args):
    """Code e-i guard: ager proshne draft hoyeche + ekhon user er message e 'yes' ache + credentials ache."""
    global _pending
    p = _pending
    if not p:
        return "There is no staged email."
    if time.time() - p["time"] > EXPIRY_SEC:
        _pending = None
        return "The staged email expired. Please draft it again."
    if not p["to"]:
        return "The draft has no recipient. Use open_email_draft so the user can add one in Gmail."
    if common.TURN == p["turn"]:
        return "Ask the user to confirm first. I cannot send in the same turn the draft was made."
    said = common.LAST_USER_TEXT or ""
    if NO_RE.search(said) or not YES_RE.search(said):
        return "The user has not clearly said yes to sending. Ask again, or wait."
    addr, pw = _creds()
    if not addr or not pw:
        return ("Sending from Jarvis is not set up (GMAIL_ADDRESS and GMAIL_APP_PASSWORD missing in .env). "
                "Use open_email_draft instead.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = addr, p["to"], p["subject"]
    msg.set_content(p["body"])
    if p["attach"]:
        ctype = mimetypes.guess_type(p["attach"])[0] or "application/octet-stream"
        main, sub = ctype.split("/", 1)
        with open(p["attach"], "rb") as f:
            msg.add_attachment(f.read(), maintype=main, subtype=sub, filename=os.path.basename(p["attach"]))
    try:
        _smtp_send(addr, pw, msg)
    except smtplib.SMTPAuthenticationError:
        return ("Gmail rejected the login. The app password may be wrong. "
                "The draft is still staged; you can use open_email_draft.")
    except Exception as e:
        return (f"Sending failed ({type(e).__name__}). Gmail or the network closed the connection. "
                "The draft is still staged; use open_email_draft instead.")
    _pending = None
    print(f"[Email sent to {p['to']}]")
    return f"Email sent to {p['to']}."


def open_email_draft(args):
    p = _pending
    if not p:
        return "There is no staged email."
    base = "https://mail.google.com/mail/?view=cm&fs=1"
    url = f"{base}&to={urllib.parse.quote(p['to'])}&su={urllib.parse.quote(p['subject'])}" \
          f"&body={urllib.parse.quote(p['body'])}"
    note = ""
    if len(url) > 1800:
        url = f"{base}&to={urllib.parse.quote(p['to'])}&su={urllib.parse.quote(p['subject'])}"
        copy_to_clipboard(p["body"])
        note = " The body is too long for the link, so it is on the clipboard: paste it with Command V."
    webbrowser.open(url)
    if p["attach"]:
        launch(p["attach"], reveal=True)
        note += " Your resume is shown in Finder, drag it into the email."
    print("[Gmail compose opened]")
    return "Gmail compose is open with the draft. Please review and press Send yourself." + note


HANDLERS = {"prepare_email": prepare_email, "send_pending_email": send_pending_email,
            "open_email_draft": open_email_draft}
