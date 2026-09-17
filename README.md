# Scheduled Check-In Bot

INF601 — Advanced Programming in Python

## Overview

This project is a small piece of scheduled automation that talks to the
Practice Hub REST API (`https://practice.fhsucyber.com`) on my behalf,
run automatically every day by a GitHub Actions workflow. It does two
things each time it runs:

**Task 1 — Collect.** Pages through every post authored by the
instructor, saves the title/body/tags/full raw JSON of each one into
`artifact/collected.json`, and downloads every attached file into
`artifact/files/`.

**Task 2 — Reply.** Finds posts whose title contains the word
"check-in" (case-insensitive, anywhere in the title) and posts a
comment reply on each one — but only if that check-in's reply window is
currently open. If the API returns a 423 (window closed), the bot skips
that post gracefully and tries again on its next scheduled run. Before
replying, it checks the post's existing comments for its own signature
string, so re-running the bot (or having multiple scheduled runs catch
the same open check-in) never posts a duplicate.

The workflow commits `artifact/` back into this repo after every run,
so the collected data and the record of replies are always visible here
without anything needing to be uploaded to Blackboard.

## Project Structure

```
checkinbotOumarMballo/
├── checkin_bot.py              # main script - Task 1 + Task 2
├── practicehub_client.py       # API client (built in Mini Project 1, extended)
├── inspect_api.py              # one-off helper to confirm live API field names
├── requirements.txt
├── README.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── checkin-bot.yml     # schedule + workflow_dispatch trigger
└── artifact/                    # generated + committed by the workflow
    ├── collected.json
    ├── run_log.json
    └── files/
```

## Setup

### 1. Install dependencies locally (optional, for testing)

```bash
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set the required environment variables

| Name | Kind | Value |
|---|---|---|
| `PRACTICE_API_TOKEN` | Secret | your own Practice Hub API token |
| `PRACTICE_API_URL` | Secret or variable | `https://practice.fhsucyber.com` |
| `INSTRUCTOR_ID` | Variable | the instructor's numeric user id |

Locally, export them in your shell before running anything:

```bash
export PRACTICE_API_TOKEN="your-token-here"
export PRACTICE_API_URL="https://practice.fhsucyber.com"
export INSTRUCTOR_ID="7"
```

### 3. Sanity-check your token and one real post

```bash
python inspect_api.py
```

This confirms your token works (via `GET /api/v1/me`) and prints the
raw JSON of one of the instructor's posts, so you can see real
attachment/comment data before the bot runs unattended on a schedule.

### 4. Run the bot manually

```bash
python checkin_bot.py
```

This creates/updates `artifact/collected.json`, downloads attachments
into `artifact/files/`, replies to any open check-ins, and appends a
summary to `artifact/run_log.json`.

### 5. Configure GitHub Actions

In this repo, go to **Settings → Secrets and variables → Actions** and
add the three values from the table above (`PRACTICE_API_TOKEN` and
`PRACTICE_API_URL` as **secrets**, `INSTRUCTOR_ID` as a **variable**).

The workflow at `.github/workflows/checkin-bot.yml` then runs on its
own three times a day (and can also be triggered by hand from the
**Actions** tab via `workflow_dispatch`), and pushes the updated
`artifact/` folder back to this repo after each run.

## AI Usage

Claude (Anthropic) was used to help design and write this project,
including the extensions to `practicehub_client.py` (pagination
iterator, comments, attachment download, the 423 `LockedError`), the
`checkin_bot.py` logic for Task 1 and Task 2, the duplicate-reply
signature check, `inspect_api.py`, and the GitHub Actions workflow
YAML. The original `PracticeHubClient` base class and CRUD methods came
from my own Mini Project 1. I reviewed and understand every line,
including the workflow YAML and the cron schedule's timing rationale,
and verified the API assumptions against the live server using
`inspect_api.py` before relying on them for the graded schedule.
