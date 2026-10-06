# ClearPay: Invoice-to-Payment AP Automation Agent

An AI agent that processes vendor invoices end to end. It reads each invoice (PDF, text or scan), checks it against the original purchase order, and decides **approve / send to manager / flag / reject**. It writes a ledger entry, drafts the emails, and logs every step with its reason. People only handle the exceptions.

**It never makes payments.** It only prepares ledger entries, and no payment code exists in the project.

Built with Python, Flask, SQLite and the Groq API (`openai/gpt-oss-120b` with tool calling).

---

## What's new in the ClearPay interface

- **Approval notifications for the AP team.** When a manager approves or rejects an invoice, every AP user (and the uploader) gets a notification: in the bell (with unread count), as a bottom-right toast within about 15 seconds on any page, on the dashboard ("Latest manager decisions", marked *New*), and on the invoice itself. Opening the invoice marks it read and records "Seen by …" in its timeline.
- **"What happened" timeline** on every invoice: uploaded, checked, sent to a manager, approved by whom and when, AP team notified, seen by whom. All times in IST, 24-hour (`14:32 IST`).
- **AP-focused dashboard:** needs AP review, waiting for a manager, ready for payment, est. money saved (₹), plus "Needs your attention" and "Latest manager decisions". Search by invoice number, vendor, PO or amount; filter by status, vendor and invoice date.
- **Indian rupee formatting everywhere** (₹1,25,000.00; headline figures as ₹5.4L / ₹1.2Cr). Groq's own cost stays in USD because Groq bills in USD.
- **Light, dark and system themes** (Account → Appearance), saved to the account so they follow you to any browser, applied before first paint (no flash).
- **Account pages** from the avatar menu: profile (name, email, department), appearance, security (change password, active sessions with "sign out" / "sign out of all other sessions", security alerts) and sign-in activity (sign-ins, sign-outs, failed attempts, lockouts, with browser, system and network address).
- **Real sessions:** each sign-in is recorded on the server; signing out, ending a session elsewhere, a password change or deactivation takes effect immediately, and the 30-minute idle timeout is enforced on the server too.
- **Admin password reset** (Settings & users) backs the "Forgot password?" link on the sign-in page. Reset-by-email isn't built, and the page says so.
- **Not built, and shown as such:** two-factor authentication, profile photos (initials are used), payments (ClearPay never pays; "Ready for payment" is the last state).
- Branding: original ClearPay logo in `static/brand/` (full logo for light and dark, mark, favicon SVG/PNG, 180 px app icon). Icons: [Lucide](https://lucide.dev) (ISC licence), bundled as `static/icons.svg`. Motion respects `prefers-reduced-motion`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # Windows: copy .env.example .env
#   then put your GROQ_API_KEY and a FLASK_SECRET_KEY in .env
python generate_data.py && python app.py
```

Open http://127.0.0.1:5000 and sign in.

| Username | Role | Can do |
|---|---|---|
| `ap_user`, `ap_user2` | AP team | Upload, review flagged invoices, send to manager, reject flagged, run evaluations |
| `manager` | Manager | Approve or reject pending invoices |
| `admin` | Admin | Everything, plus rules, users and the regression baseline |

The password for all four is `DEMO_PASSWORD` from `.env` (default `ChangeMe!2026`; change it).

**No Groq key?** The app still runs in *offline rule-based mode*. A built-in parser reads the generated test invoices, and a fixed orchestration replaces the LLM. Real-world invoices need Groq.

**Scanned images (optional):** install the [Tesseract](https://github.com/tesseract-ocr/tesseract) binary for OCR of PNG/JPG and scanned PDFs. Without it, those files are flagged as unreadable and a resend request is drafted.

### Try it

1. Sign in as `ap_user` and go to **Upload invoice**. Drag in files from `sample_invoices/` or `redteam_invoices/` and watch each agent step appear live.
2. Open a flagged invoice to see **where it went wrong**: problem cards, invoice vs PO table, the original PDF with red boxes on the bad values, the agent's reasoning, and the drafted emails.
3. Sign in as `manager` and go to **Approvals**. Approve one invoice, and the agent drafts the "approved" email to the AP team.
4. Or copy files into `invoices_inbox/`. The watcher picks them up within a few seconds (`python generate_data.py --fill-inbox 8` does this for you).
5. Go to **Evaluation report** and press **Run evaluation**. Then look at the **Red-team lab**, **What-if replay** and **Decision regression** pages.

---

## How it works

```
 invoices_inbox/ ──watcher──┐
                            ├──► invoice record ──► queue ──► agent worker
 Upload page (AP team) ─────┘                                     │
                                                                  ▼
          ┌──────────────────────── Groq gpt-oss-120b (tool calling) ─────────────────────────┐
          │  chooses the next tool:                                                          │
          │  extract_invoice_data → check_vendor → check_duplicate → validate_math → lookup_po │
          │  → write_ledger_entry | escalate_to_human, draft_email                           │
          └──────────────────────────────────────────────────────────────────────────────────┘
                                                                  │  tool calls (args validated)
                                                                  ▼
                tools.py: every number, comparison and rule runs in Python code
                                                                  │
                                                                  ▼
       finalize(): runs any check the LLM skipped → decide() → ledger → emails → report → audit log
                                                                  │
                                                                  ▼
          Dashboard · Invoice report · Approvals (manager) → "approved" email to AP team
```

**The key design rule:** the LLM *reads* documents and *chooses the order* of tools. Code *does the maths and makes the decision*. Tools use data stored in Python, not numbers the LLM passes in, and `write_ledger_entry` is refused unless the code checks passed. A manipulated model therefore can't approve a bad invoice.

### Decision rules (code, in `tools.decide`)

| Situation | Result |
|---|---|
| Exact PO match, maths correct, total under ₹5,000 | ✅ **Approved** (ledger: ready to pay) |
| Variance from PO under 5%, total over ₹5,000, AI confidence under 0.7, or a possible split invoice | ⏳ **Pending** manager |
| Unknown or look-alike vendor, bank or GSTIN change, missing or unknown PO, wrong maths, big mismatch, item not on PO, re-sent invoice, PO used up, prompt injection, unreadable file | 🚩 **Flagged** with reasons |
| Exact duplicate | ❌ **Rejected** |

The limits live in the `settings` table, and admins change them on the **Settings** page.

### Emails (drafted and saved to the database; sending is mocked)

| Email | When |
|---|---|
| Approval request → manager | An invoice is pending |
| **Approved / rejected notice → AP team** | Right after a manager decides |
| Differences found / missing info / please resend → vendor | The vendor needs to fix something |
| Needs review → AP team | Fraud signals (the vendor is *not* emailed) |
| Check report → any address | Entered on upload, or from the invoice page |

Vendor emails always go to the address **on file**, never one found in the invoice text.

---

## Project structure

```
app.py             Flask routes, permissions, approval flow, account pages, trust & testing pages
notifications.py   In-app notifications: who is told about which invoice event
agent.py           Groq tool-calling loop, argument validation, guardrails, finalize(), worker queue
tools.py           The 8 tools, extraction, maths/GST/PO checks, decision rules, emails, PDF highlights
db.py              SQLite schema, seed data, settings, hash-chained audit log
security.py        Lockout, role checks, CSRF, rate limits, headers, upload checks, injection scanner
watcher.py         Background thread for invoices_inbox/
mailer.py          Real email sending over SMTP (optional), test-mode redirect
generate_data.py   Seed DB + 30 labelled test invoices + 18 red-team attacks
evaluate.py        Accuracy, routing, duplicates, red-team, regression gate
templates/, static/  Bootstrap UI (bundled locally, works offline)
tests/             pytest: business rules + security controls
regression_baseline.json   Approved decisions; CI fails if one breaks
.github/workflows/ci.yml   Tests, evaluation gate, bandit, pip-audit
```

**Database tables:** `vendors`, `purchase_orders`, `po_lines`, `invoices`, `ledger`, `audit_log`, `emails`, `users`, `settings`.

---

## Features that set it apart

- **Red-team lab:** 18 attack invoices (hidden white-text prompt injection, fake "assistant" messages, look-alike vendors like "Acrne Corp", changed bank details and GSTIN, re-sent bills, math traps, one order split into two invoices to dodge the limit). The page shows which were blocked and replays the agent's steps.
- **What-if policy replay:** change the limit, tolerance or confidence threshold and replay past invoices (or the labelled test set) to see which decisions change. It makes no AI calls and writes nothing.
- **Decision regression:** snapshot testing for the agent. After changing the prompt, model or rules, it shows which decisions changed and whether each is a fix or a new bug. `--check-regression` fails CI.
- **"Where it went wrong" report:** plain-English problem cards, invoice vs PO table, and the original PDF with red boxes on the wrong values.
- **Indian GST checks:** GSTIN format, CGST = SGST, and the tax rate compared to the PO.
- **Cost and speed:** tokens, estimated Groq cost and time per invoice.

---

## Security

| Area | Controls |
|---|---|
| Accounts | Hashed passwords (Werkzeug scrypt), lockout after 5 failures for 15 min, same error for wrong user or password, 30-min idle timeout, new session on login, every sign-in logged |
| Access | Role checks on every route on the server; **segregation of duties** (whoever uploaded an invoice can't approve it); admin-only rules and users |
| Web | CSRF token on every POST, parameterised SQL, auto-escaped templates, no inline scripts, CSP / X-Frame-Options / nosniff headers, rate limits on login and upload, friendly error pages, CSV-injection guard on export |
| Uploads | Type checked by real file signature, 10 MB limit, random stored names, private folder (never under `static/`), mismatched content quarantined as unreadable |
| AI | Invoice text marked as untrusted data; code scanner for injection phrases and hidden text; JSON output validated; tool allowlist; every argument checked; ledger guardrail; agent emails built from templates |
| Data | Secrets in `.env` (git-ignored), bank accounts masked, **tamper-evident audit log** (each row hashes the previous; the Audit page shows "Log integrity: verified") |
| Testing | `pytest` access-control and rule tests, red-team suite, `bandit` and `pip-audit` in CI |

**Before production:** serve over HTTPS (and set `SESSION_COOKIE_SECURE=1`), use Postgres instead of SQLite, add 2FA/SSO, encrypt data at rest, move rate limits to Redis, send emails through a real provider with approval, and run behind a WSGI server (gunicorn). This is a hackathon-grade build.

---

## Testing and evaluation

```bash
pip install -r requirements-dev.txt
pytest -q                                   # 37 tests: rules, security, notifications, sessions
python evaluate.py                          # test set + red-team (uses Groq if a key is set)
python evaluate.py --mode offline           # no AI calls
python evaluate.py --save-baseline          # accept current decisions as the baseline
python evaluate.py --check-regression       # exit 1 if a previously correct decision broke
```

Offline results on the bundled data: **30/30 routed correctly, 100% extraction, 3/3 duplicates, 18/18 attacks blocked.** Run it with your Groq key to measure the real model. Its extraction may differ from the offline parser, and that's what the evaluation is for.

## Sending real emails

By default emails are only drafted and marked as sent (`EMAIL_MODE=mock`). To really send them when someone presses **Send**:

1. Gmail: turn on 2-Step Verification, then create an App Password at https://myaccount.google.com/apppasswords.
2. In `.env`: `EMAIL_MODE=smtp`, `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER` = your Gmail,
   `SMTP_PASSWORD` = the 16-character App Password, `MAIL_FROM` = your Gmail.
3. While testing, set `EMAIL_REDIRECT_TO` = your own address: every email goes to you, marked with who it was meant for.
4. Restart the app. As admin, open **Settings**, set the manager, AP team and vendor addresses, and press **Send test email**.
5. Remove `EMAIL_REDIRECT_TO` to go live.

Emails are never sent automatically. Placeholder addresses (`*.example`) are refused with a clear message, failures are
shown on the email and in the audit log, and subjects are forced to one line (no header injection).

## Groq free plan limits

Groq's free plan allows about 8,000 tokens a minute and 200,000 a day for `openai/gpt-oss-120b` (per organisation; the
limits page in the Groq console is authoritative). In full agent mode one invoice used roughly 6,000 to 11,000 tokens,
so a few uploads in a row hit "429 rate limit". Set `LLM_MODE=extract_only` in `.env`: the AI then only reads the invoice
(about 1,000 tokens) and code runs the checks in a fixed order. The agent log shows which limit was hit and how long Groq
asks to wait; short waits are followed automatically, long ones (the daily limit) stop at once and the invoice goes to
a person, marked "The AI didn't answer".

## Troubleshooting

- **"offline rule-based mode" in the sidebar:** `GROQ_API_KEY` is missing from `.env`.
- **Groq errors or rate limits:** the agent retries 3 times, then falls back to rule-based orchestration and logs it. The invoice is never left stuck.
- **"Your form expired":** the CSRF token is tied to your session. Reload the page.
- **Reset everything:** `python generate_data.py` rebuilds the database and test files.
