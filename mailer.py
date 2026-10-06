"""
mailer.py - sends emails for real over SMTP (Gmail, Outlook, Brevo, SendGrid, company mail server...).

Settings come from .env:
  EMAIL_MODE=mock | smtp       mock = nothing leaves the app (default)
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
  SMTP_SECURITY=starttls | ssl | none     (none only for a local test server)
  MAIL_FROM, MAIL_FROM_NAME
  EMAIL_REDIRECT_TO            test mode: every email goes to this address instead,
                               with a note saying who it was meant for

Emails are never sent automatically: a person presses "Send" on each draft.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import security


def mode():
    return os.getenv("EMAIL_MODE", "mock").strip().lower()


def missing_settings():
    return [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if not os.getenv(k)]


def is_real():
    return mode() == "smtp" and not missing_settings()


def redirect_to():
    return os.getenv("EMAIL_REDIRECT_TO", "").strip()


def status():
    """Shown on the Settings and Email drafts pages."""
    if mode() != "smtp":
        return {"real": False, "label": "Demo mode: emails are only marked as sent (EMAIL_MODE=mock)."}
    if missing_settings():
        return {"real": False, "label": "EMAIL_MODE=smtp, but these are missing in .env: " + ", ".join(missing_settings())}
    r = redirect_to()
    return {"real": True, "redirect": r,
            "label": (f"Real sending ON via {os.getenv('SMTP_HOST')}. TEST MODE: every email goes to {r}."
                      if r else f"Real sending ON via {os.getenv('SMTP_HOST')}. Emails go to the real recipients.")}


def _one_line(text, limit=250):
    """Header values must be one line (blocks email header injection)."""
    return " ".join(str(text or "").split())[:limit]


def send(to, subject, body):
    """Send one email. Returns (ok, delivered_to, error_message)."""
    if not is_real():
        return True, None, None                       # mock mode: caller just marks it sent
    target = redirect_to() or to
    if not security.valid_email(target):
        return False, None, f"'{target}' isn't a valid email address."
    if target.lower().endswith((".example", ".test", ".invalid", ".localhost")):
        return False, None, (f"'{target}' is a placeholder demo address and can't receive mail. Put a real address "
                             f"in Settings (manager, AP team or vendor), or set EMAIL_REDIRECT_TO in .env for testing.")

    from_addr = os.getenv("MAIL_FROM") or os.getenv("SMTP_USER")
    msg = EmailMessage()
    msg["From"] = f"{_one_line(os.getenv('MAIL_FROM_NAME', 'ClearPay'), 80)} <{from_addr}>"
    msg["To"] = target
    msg["Subject"] = ("[TEST] " if redirect_to() else "") + _one_line(subject)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_addr.split("@")[-1])
    if redirect_to():
        body = (f"[TEST MODE] This email was meant for: {to}\n"
                f"It was redirected to you because EMAIL_REDIRECT_TO is set in .env.\n"
                f"{'-' * 60}\n\n{body}")
    msg.set_content(body)

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    security_mode = os.getenv("SMTP_SECURITY", "ssl" if port == 465 else "starttls").lower()
    tls = ssl.create_default_context()
    try:
        if security_mode == "ssl":
            server = smtplib.SMTP_SSL(host, port, context=tls, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        with server:
            if security_mode == "starttls":
                server.starttls(context=tls)
            if security_mode != "none":            # "none" is only for a local test server without login
                # Google shows App Passwords as "abcd efgh ijkl mnop": spaces are not part of the password
                server.login(os.getenv("SMTP_USER", "").strip(), "".join(os.getenv("SMTP_PASSWORD", "").split()))
            server.send_message(msg)
        return True, target, None
    except smtplib.SMTPAuthenticationError:
        return False, None, ("The mail server refused the login. Check SMTP_USER, and for Gmail use a 16-character "
                             "App Password, not your normal password.")
    except smtplib.SMTPServerDisconnected:
        # Must come before OSError: smtplib's errors are a kind of OSError in Python.
        return False, None, ("The mail server hung up during login. For Gmail this almost always means the App Password "
                             "isn't accepted: create a new one at myaccount.google.com/apppasswords while signed in to "
                             f"{os.getenv('SMTP_USER')}, put the 16 letters (no spaces) in SMTP_PASSWORD, and restart. "
                             "After several failed tries Google may also block logins for 15-30 minutes.")
    except smtplib.SMTPRecipientsRefused:
        return False, None, f"The mail server refused the recipient '{target}'."
    except smtplib.SMTPException as e:
        return False, None, f"Mail server error: {str(e)[:200]}"
    except (TimeoutError, ConnectionError, OSError) as e:
        return False, None, (f"Couldn't reach {host}:{port} ({type(e).__name__}). Check SMTP_HOST/SMTP_PORT, your "
                             f"internet, or whether this network blocks outgoing mail ports (common on college/office Wi-Fi).")
