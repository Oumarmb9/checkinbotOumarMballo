# INF601 - Advanced Programming in Python
# Oumar Mballo
# Scheduled Check-In Bot

"""
inspect_api.py

A quick sanity check before trusting checkin_bot.py against the real
schedule: confirms your token works, then prints the raw JSON of one of
the instructor's posts (and one comment, if any exist) so you can see
real data instead of just trusting assumptions.

Set the same environment variables you'll use for the real bot before
running this (see README.md), then:

    python inspect_api.py
"""

import json
import os
import sys

from practicehub_client import PracticeHubClient, DEFAULT_BASE_URL, PracticeHubError


def main() -> None:
    token = os.environ.get("PRACTICE_API_TOKEN")
    base_url = os.environ.get("PRACTICE_API_URL", DEFAULT_BASE_URL)
    instructor_id = os.environ.get("INSTRUCTOR_ID")

    if not token or not instructor_id:
        sys.exit(
            "Set PRACTICE_API_TOKEN and INSTRUCTOR_ID environment variables first."
        )

    client = PracticeHubClient(token=token, base_url=base_url)

    print("Checking that the token works via GET /api/v1/me ...")
    try:
        me = client.get_me()
        print(f"  Authenticated as: {me.get('name')} (id {me.get('id')})\n")
    except PracticeHubError as exc:
        sys.exit(f"Token check failed: {exc}")

    print(f"Fetching first page of posts by author {instructor_id} ...\n")
    posts = client.list_posts(author=int(instructor_id), limit=5, offset=0)

    if not posts:
        sys.exit("No posts came back for that author id - double check INSTRUCTOR_ID.")

    print(f"Got {len(posts)} post(s). Full JSON of the first one:\n")
    print(json.dumps(posts[0], indent=2))

    attachments = PracticeHubClient.get_attachment_list(posts[0])
    print(f"\nThis post has {len(attachments)} attachment(s).")
    if attachments:
        print("First attachment entry:")
        print(json.dumps(attachments[0], indent=2))

    print("\nTrying to list comments on this post ...")
    try:
        comments = client.list_comments(posts[0]["id"])
        print(f"Got {len(comments)} comment(s).")
        if comments:
            print("First comment JSON:")
            print(json.dumps(comments[0], indent=2))
    except PracticeHubError as exc:
        print(f"list_comments() failed: {exc}")
        print(
            "If this 404s, the comments endpoint path in "
            "practicehub_client.py needs adjusting."
        )


if __name__ == "__main__":
    main()
