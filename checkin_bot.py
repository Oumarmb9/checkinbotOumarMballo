# INF601 - Advanced Programming in Python
# Oumar Mballo
# Scheduled Check-In Bot

"""
checkin_bot.py

Runs (by hand, or on GitHub Actions' schedule) and does two jobs against
the Practice Hub API for a single configured instructor:

  Task 1 - Collect: pull every post by the instructor, with full body,
  tags, timestamps, and every attached file downloaded, into artifact/.

  Task 2 - Reply: find posts whose title contains "check-in" (any case,
  any surrounding text) and post a reply comment on each - unless the
  window is closed (HTTP 423, handled gracefully) or we've already
  replied to that one (checked via a signature string in our own past
  comments, so re-running the bot never posts duplicates).

Configuration comes entirely from environment variables so the same
script runs the same way locally and inside the GitHub Actions workflow:

    PRACTICE_API_TOKEN   - your Practice Hub bearer token (secret)
    PRACTICE_API_URL     - base URL of the API (defaults to the course server)
    INSTRUCTOR_ID         - the instructor's numeric user id
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from practicehub_client import (
    PracticeHubClient,
    DEFAULT_BASE_URL,
    LockedError,
    PracticeHubError,
)

ARTIFACT_DIR = "artifact"
FILES_DIR = os.path.join(ARTIFACT_DIR, "files")
COLLECTED_PATH = os.path.join(ARTIFACT_DIR, "collected.json")
LOG_PATH = os.path.join(ARTIFACT_DIR, "run_log.json")

# The exact string we look for in a post title to recognize a check-in.
CHECKIN_KEYWORD = "check-in"

# Embedded in every reply so re-runs can tell "have I already answered
# this one?" without needing to know our own user id.
REPLY_SIGNATURE = "[auto-reply:checkin-bot]"


def build_client() -> tuple[PracticeHubClient, int]:
    """Build a client and return it along with the instructor's user id."""
    token = os.environ.get("PRACTICE_API_TOKEN")
    base_url = os.environ.get("PRACTICE_API_URL", DEFAULT_BASE_URL)
    instructor_id = os.environ.get("INSTRUCTOR_ID")

    missing = [
        name
        for name, value in (
            ("PRACTICE_API_TOKEN", token),
            ("INSTRUCTOR_ID", instructor_id),
        )
        if not value
    ]
    if missing:
        sys.exit(f"Missing required environment variable(s): {', '.join(missing)}")

    return PracticeHubClient(token=token, base_url=base_url), int(instructor_id)


# ---------------------------------------------------------------------------
# Task 1 - Collect every instructor post, with attachments downloaded
# ---------------------------------------------------------------------------

def collect_posts(client: PracticeHubClient, instructor_id: int) -> list[dict]:
    """
    Page through every post by the instructor, download each attachment,
    and write it all to artifact/collected.json. Returns the list of raw
    post dicts so Task 2 can reuse it without a second round of API calls.
    """
    os.makedirs(FILES_DIR, exist_ok=True)

    all_posts = []
    collected_records = []

    for post in client.iter_all_posts(author=instructor_id):
        all_posts.append(post)

        attachments = PracticeHubClient.get_attachment_list(post)
        downloaded_files = []

        for attachment in attachments:
            # Confirmed against the live API guide: each attachment has
            # "download_url" and "filename".
            url = attachment.get("download_url")
            filename = attachment.get("filename")

            if not url or not filename:
                print(f"  ! Skipping attachment with unrecognized shape: {attachment}")
                continue

            dest_path = os.path.join(FILES_DIR, f"post_{post['id']}_{filename}")
            try:
                client.download_attachment(url, dest_path)
                downloaded_files.append(dest_path)
                print(f"  Downloaded {dest_path}")
            except PracticeHubError as exc:
                print(f"  ! Failed to download attachment for post {post['id']}: {exc}")

        collected_records.append(
            {
                "id": post.get("id"),
                "title": post.get("title"),
                "body": post.get("body"),
                "tags": post.get("tags"),
                "raw_post": post,  # full fidelity, whatever fields the API sent
                "downloaded_files": downloaded_files,
            }
        )
        print(f"Collected post #{post.get('id')}: {post.get('title')!r}")

    with open(COLLECTED_PATH, "w", encoding="utf-8") as f:
        json.dump(collected_records, f, indent=2, default=str)

    print(f"\nSaved {len(collected_records)} post(s) to {COLLECTED_PATH}")
    return all_posts


# ---------------------------------------------------------------------------
# Task 2 - Reply to each open check-in, exactly once
# ---------------------------------------------------------------------------

def is_checkin(post: dict) -> bool:
    title = post.get("title") or ""
    return CHECKIN_KEYWORD in title.lower()


def already_replied(client: PracticeHubClient, post_id: int) -> bool:
    """Check the post's existing comments for our own signature."""
    try:
        comments = client.list_comments(post_id)
    except PracticeHubError as exc:
        print(f"  ! Could not list comments for post {post_id} ({exc}); assuming not replied.")
        return False

    return any(REPLY_SIGNATURE in (comment.get("body") or "") for comment in comments)


def reply_to_checkins(client: PracticeHubClient, posts: list[dict]) -> dict:
    """
    Reply to each check-in post that's open and hasn't been answered yet.
    Returns a small summary dict for the run log.
    """
    checkins = [p for p in posts if is_checkin(p)]
    print(f"\nFound {len(checkins)} check-in post(s) among {len(posts)} total.")

    replied, skipped_duplicate, skipped_closed, failed = [], [], [], []

    for post in checkins:
        post_id = post["id"]
        title = post.get("title", "")

        if already_replied(client, post_id):
            print(f"  Already replied to #{post_id} ({title!r}) - skipping.")
            skipped_duplicate.append(post_id)
            continue

        reply_body = (
            f"Checked in! {REPLY_SIGNATURE} "
            f"(posted {datetime.now(timezone.utc).isoformat()})"
        )

        try:
            client.create_comment(post_id, reply_body)
            print(f"  Replied to #{post_id} ({title!r}).")
            replied.append(post_id)
        except LockedError:
            print(f"  Window closed for #{post_id} ({title!r}) - will try again next run.")
            skipped_closed.append(post_id)
        except PracticeHubError as exc:
            print(f"  ! Failed to reply to #{post_id} ({title!r}): {exc}")
            failed.append(post_id)

    return {
        "checkins_found": [p["id"] for p in checkins],
        "replied": replied,
        "skipped_duplicate": skipped_duplicate,
        "skipped_closed": skipped_closed,
        "failed": failed,
    }


# ---------------------------------------------------------------------------

def main() -> None:
    client, instructor_id = build_client()
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    print("=== Task 1: Collecting instructor posts ===")
    posts = collect_posts(client, instructor_id)

    print("\n=== Task 2: Replying to open check-ins ===")
    summary = reply_to_checkins(client, posts)

    run_record = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_posts_collected": len(posts),
        **summary,
    }

    log = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = []
    log.append(run_record)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)

    print(f"\nRun summary written to {LOG_PATH}:")
    print(json.dumps(run_record, indent=2))


if __name__ == "__main__":
    main()
