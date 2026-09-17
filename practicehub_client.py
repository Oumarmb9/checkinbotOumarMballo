# INF601 - Advanced Programming in Python
# Oumar Mballo
# Scheduled Check-In Bot

"""
practicehub_client.py

Client for the INF601 Practice Hub REST API (https://practice.fhsucyber.com).

This is the same PracticeHubClient built in Mini Project 1, extended with
what the check-in bot needs on top of the CRUD-on-posts functionality:

  - iter_all_posts(): pages through *every* post for a given author,
    instead of a single limit/offset call.
  - list_comments() / create_comment(): read and write comments on a post.
  - LockedError: raised on HTTP 423, the status the API returns when a
    check-in's reply window is closed.
  - download_attachment(): streams an attachment URL to a local file,
    using the same authenticated session (works whether the URL is a
    relative API path or an absolute one).

Endpoint shapes below (comments, attachments) are confirmed against the
official Practice Hub API guide at /docs-guide.
"""

from __future__ import annotations

import os
from urllib.parse import urljoin

import requests


DEFAULT_BASE_URL = "https://practice.fhsucyber.com"

# Confirmed against the live API guide: a post's attachments live under
# the "attachments" key, and each entry has "download_url" + "filename".
ATTACHMENT_KEYS = ("attachments",)


class PracticeHubError(Exception):
    """Base exception for all Practice Hub API errors."""

    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AuthenticationError(PracticeHubError):
    """Raised on HTTP 401 - missing, invalid, or expired token."""


class ForbiddenError(PracticeHubError):
    """Raised on HTTP 403 - trying to edit/delete a post you don't own."""


class NotFoundError(PracticeHubError):
    """Raised on HTTP 404 - the requested post does not exist."""


class ValidationError(PracticeHubError):
    """Raised on HTTP 422 - the request body failed validation."""


class LockedError(PracticeHubError):
    """Raised on HTTP 423 - the check-in's reply window is not open."""


class PracticeHubClient:
    """
    An OOP wrapper around the Practice Hub REST API.

    Parameters
    ----------
    token : str
        The bearer API token for the authenticated user.
    base_url : str, optional
        The root URL of the API. Defaults to the course server.
    timeout : int, optional
        Per-request timeout, in seconds. Defaults to 10.
    """

    def __init__(self, token: str, base_url: str = DEFAULT_BASE_URL, timeout: int = 15):
        if not token:
            raise ValueError("A Practice Hub API token is required.")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """
        Send a request and translate documented error status codes into
        specific exceptions instead of letting the caller see a raw
        traceback or an unhandled HTTPError.
        """
        url = f"{self.base_url}{path}" if path.startswith("/") else path

        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise PracticeHubError(f"Network error while calling {url}: {exc}") from exc

        if response.status_code in (200, 201, 204):
            return response

        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text or "No error detail provided."

        if response.status_code == 401:
            raise AuthenticationError(
                f"401 Unauthorized: {detail} (check that PRACTICE_API_TOKEN is set and valid)",
                status_code=401,
                response=response,
            )
        if response.status_code == 403:
            raise ForbiddenError(
                f"403 Forbidden: {detail}",
                status_code=403,
                response=response,
            )
        if response.status_code == 404:
            raise NotFoundError(f"404 Not Found: {detail}", status_code=404, response=response)
        if response.status_code == 422:
            raise ValidationError(
                f"422 Unprocessable Entity: {detail}", status_code=422, response=response
            )
        if response.status_code == 423:
            raise LockedError(
                f"423 Locked: {detail} (this check-in's reply window is not currently open)",
                status_code=423,
                response=response,
            )

        raise PracticeHubError(
            f"{response.status_code} error calling {method} {path}: {detail}",
            status_code=response.status_code,
            response=response,
        )

    # ------------------------------------------------------------------
    # Posts - create / read / update / delete
    # ------------------------------------------------------------------

    def create_post(self, title: str, body: str = "", tags: list[str] | None = None) -> dict:
        payload = {"title": title, "body": body, "tags": tags or []}
        response = self._request("POST", "/api/v1/posts", json=payload)
        return response.json()

    def list_posts(
        self,
        mine: bool = False,
        author: int | None = None,
        tag: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        params = {"mine": mine, "limit": limit, "offset": offset}
        if author is not None:
            params["author"] = author
        if tag is not None:
            params["tag"] = tag

        response = self._request("GET", "/api/v1/posts", params=params)
        return response.json()

    def iter_all_posts(self, author: int | None = None, tag: str | None = None, page_size: int = 50):
        """
        Yield every post matching the filters, paging through the API's
        limit/offset pagination automatically until a short page (or an
        empty one) signals there's nothing left.
        """
        offset = 0
        while True:
            page = self.list_posts(author=author, tag=tag, limit=page_size, offset=offset)
            if not page:
                return
            for post in page:
                yield post
            if len(page) < page_size:
                return
            offset += page_size

    def get_post(self, post_id: int) -> dict:
        response = self._request("GET", f"/api/v1/posts/{post_id}")
        return response.json()

    def update_post(
        self,
        post_id: int,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        payload = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if tags is not None:
            payload["tags"] = tags

        response = self._request("PATCH", f"/api/v1/posts/{post_id}", json=payload)
        return response.json()

    def delete_post(self, post_id: int) -> bool:
        self._request("DELETE", f"/api/v1/posts/{post_id}")
        return True

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def get_me(self) -> dict:
        """Return the account that owns the current token - {'id', 'name', 'email', ...}."""
        response = self._request("GET", "/api/v1/me")
        return response.json()

    # ------------------------------------------------------------------
    # Comments (used for Task 2 - replying to check-ins)
    # ------------------------------------------------------------------

    def list_comments(self, post_id: int) -> list[dict]:
        """Return every comment on a post."""
        response = self._request("GET", f"/api/v1/posts/{post_id}/comments")
        return response.json()

    def create_comment(self, post_id: int, body: str) -> dict:
        """Post a new comment (reply) on a post."""
        response = self._request(
            "POST", f"/api/v1/posts/{post_id}/comments", json={"body": body}
        )
        return response.json()

    # ------------------------------------------------------------------
    # Attachments (used for Task 1 - downloading every file on a post)
    # ------------------------------------------------------------------

    @staticmethod
    def get_attachment_list(post: dict) -> list[dict]:
        """
        Pull whatever attachment list is present on a post dict, trying
        each key in ATTACHMENT_KEYS in turn. Returns [] if none is found.
        """
        for key in ATTACHMENT_KEYS:
            value = post.get(key)
            if value:
                return value
        return []

    def download_attachment(self, attachment_url: str, dest_path: str) -> None:
        """
        Download one attachment to dest_path. Works whether attachment_url
        is a full URL or a path relative to base_url, and streams the
        response so large files don't need to fit in memory at once.
        """
        url = urljoin(self.base_url + "/", attachment_url.lstrip("/")) \
            if not attachment_url.startswith("http") else attachment_url

        try:
            response = self.session.get(url, timeout=self.timeout, stream=True)
        except requests.exceptions.RequestException as exc:
            raise PracticeHubError(f"Network error downloading {url}: {exc}") from exc

        if response.status_code != 200:
            raise PracticeHubError(
                f"Failed to download attachment ({response.status_code}): {url}",
                status_code=response.status_code,
                response=response,
            )

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
