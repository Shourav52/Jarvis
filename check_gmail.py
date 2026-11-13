"""Gmail login check. Email PATHAY NA, shudhu login thik kina dekhe.

Chalao:  python check_gmail.py
Password ba .env er content kothao print kore na (shudhu length).
"""
import os
import re
import smtplib
import ssl
import sys

from dotenv import load_dotenv

load_dotenv()
addr = (os.getenv("GMAIL_ADDRESS") or "").strip()
raw = os.getenv("GMAIL_APP_PASSWORD") or ""
pw = re.sub(r"\s+", "", raw)

print(f"Address        : {addr or 'NEI (.env e GMAIL_ADDRESS dao)'}")
print(f"Password length: {len(pw)} (space bade; Gmail app password hole 16 hoy)")
if any(ord(c) > 127 for c in raw):
    print("Warning: password e onno rokomer (non-ASCII) character ache. Notun kore type kore dekho.")
if not addr or not pw:
    sys.exit("GMAIL_ADDRESS ba GMAIL_APP_PASSWORD .env te nei.")


def attempt(label, connect):
    try:
        s = connect()
        s.login(addr, pw)
        s.quit()
        print(f"{label}: LOGIN OK")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"{label}: Gmail password nilo na (code {e.smtp_code}). App password ta vul, "
              f"ba 2-Step Verification on nei. Notun app password banao.")
    except smtplib.SMTPServerDisconnected:
        print(f"{label}: Gmail ba tomar network connection bondho kore dilo (login er shomoy).")
    except Exception as e:
        print(f"{label}: {type(e).__name__}: {e}")
    return False


def starttls():
    s = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
    s.ehlo()
    s.starttls(context=ssl.create_default_context())
    s.ehlo()
    return s


ok1 = attempt("Port 465 (SSL)     ", lambda: smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20,
                                                                context=ssl.create_default_context()))
ok2 = attempt("Port 587 (STARTTLS)", starttls)
print()
if ok1 or ok2:
    print("Thik ache! Jarvis theke email pathano jabe.")
else:
    print("Duto-i fail. Ekta ekta kore try koro:")
    print(" 1. Mobile hotspot e (onno network e) abar chalao. Wi-Fi/ISP/VPN SMTP block korte pare.")
    print(" 2. VPN/antivirus bondho kore dekho.")
    print(" 3. myaccount.google.com > Security e 'Recent security activity' e blocked sign-in dekho, 'Yes it was me' dao.")
    print(" 4. App password mucho, notun banao (2-Step Verification on thakte hobe).")
    print(" 5. School/office Google account hole admin app password block korte pare. Personal Gmail try koro.")
    