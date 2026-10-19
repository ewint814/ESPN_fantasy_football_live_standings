"""Private visit log. The dashboard does not link here or show these lines."""

import hashlib
import hmac
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, tzinfo
from html import escape

from flask import Flask, Response, request

logger = logging.getLogger(__name__)

MAX_LINES = 400
MAX_PER_MINUTE = 60
TAB_DETAILS = frozenset({"Current Standings", "Live Projections"})


def device_label(user_agent: str) -> str:
    """Short device name. The raw user agent is not stored."""
    ua = (user_agent or "").lower()
    if not ua.strip():
        return "Unknown"
    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "Android"
    if "mobile" in ua:
        return "Mobile"
    return "Desktop"


def passwords_match(expected: str, supplied: str) -> bool:
    """True when the supplied password matches. Empty expected never matches."""
    if not expected or supplied is None:
        return False
    expected_hash = hashlib.sha256(expected.encode()).digest()
    supplied_hash = hashlib.sha256(supplied.encode()).digest()
    return hmac.compare_digest(expected_hash, supplied_hash)


def accepted_event(event: str, detail: str) -> tuple[str, str] | None:
    """Allow a page open or a tab click. Anything else is dropped."""
    event = (event or "").strip()
    detail = (detail or "").strip()
    if event == "open" and detail == "dashboard":
        return ("open", "dashboard")
    if event == "tab" and detail in TAB_DETAILS:
        return ("tab", detail)
    return None


class VisitLog:
    """Append-only visit lines. Failures stay inside this class."""

    def __init__(self, path: str, timezone: tzinfo, max_lines: int = MAX_LINES) -> None:
        self.path = path
        self.timezone = timezone
        self.max_lines = max_lines
        self._lock = threading.Lock()
        self._recent: list[float] = []

    def allow(self) -> bool:
        """Drop bursts so a noisy client cannot fill the log."""
        now = time.monotonic()
        with self._lock:
            self._recent = [stamp for stamp in self._recent if now - stamp < 60]
            if len(self._recent) >= MAX_PER_MINUTE:
                return False
            self._recent.append(now)
            return True

    def record(self, event: str, detail: str, user_agent: str) -> None:
        """Write one line. Never raises."""
        try:
            stamp = datetime.now(self.timezone)
            hour = stamp.strftime("%I").lstrip("0") or "0"
            when = stamp.strftime(f"%Y-%m-%d {hour}:%M:%S %p ET")
            line = f"{when} | {event} | {detail} | {device_label(user_agent)}"
            logger.info("visit %s", line)
            with self._lock:
                existing: list[str] = []
                if os.path.exists(self.path):
                    with open(self.path, encoding="utf-8") as handle:
                        existing = [row.rstrip("\n") for row in handle if row.strip()]
                existing.append(line)
                trimmed = existing[-self.max_lines :]
                with open(self.path, "w", encoding="utf-8") as handle:
                    handle.write("\n".join(trimmed) + "\n")
        except Exception:
            return

    def lines(self) -> list[str]:
        """Newest first. Empty when the file is missing or unreadable."""
        try:
            with self._lock:
                if not os.path.exists(self.path):
                    return []
                with open(self.path, encoding="utf-8") as handle:
                    rows = [row.rstrip("\n") for row in handle if row.strip()]
            rows.reverse()
            return rows
        except Exception:
            return []


def render_log_page(lines: list[str]) -> str:
    """Plain private page. Not the dashboard."""
    if lines:
        body = "\n".join(escape(line) for line in lines)
    else:
        body = "No visits recorded yet."
    note = (
        "Page loads and tab clicks. This file resets when the app redeploys. "
        "The same lines are in the Render logs."
    )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<title>Visit log</title></head><body>"
        f"<p>{note}</p><pre>{body}</pre></body></html>"
    )


def register_visit_routes(
    app: Flask,
    visit_log: VisitLog,
    password_getter: Callable[[], str],
) -> None:
    """POST /visit is a silent beacon. GET /log is password-only."""

    @app.route("/visit", methods=["POST"])
    def visit() -> Response:
        try:
            accepted = accepted_event(request.form.get("event", ""), request.form.get("detail", ""))
            if accepted and visit_log.allow():
                visit_log.record(accepted[0], accepted[1], request.headers.get("User-Agent", ""))
        except Exception:
            pass
        return Response(status=204)

    @app.route("/log")
    def visit_log_page() -> Response:
        password = password_getter() or ""
        if not password:
            return Response(status=404)
        supplied = request.authorization.password if request.authorization else None
        if not passwords_match(password, supplied or ""):
            return Response(
                "Login required",
                401,
                {"WWW-Authenticate": 'Basic realm="Visit log"'},
            )
        return Response(render_log_page(visit_log.lines()), mimetype="text/html")
