"""Fetch a course's transcripts through your own logged-in browser.

This reimplements what the Udemy Transcript Extractor extension does, because
a Chrome extension has no external RPC surface a script can call. The
important property is preserved: the requests run inside a real browser
session that *you* logged into, so no credential is ever extracted, stored, or
passed to this tool.

Endpoints (undocumented, Udemy-internal - they can change without notice):
    /api-2.0/courses/{id}/subscriber-curriculum-items/
    /api-2.0/users/me/subscribed-courses/{id}/lectures/{lecture_id}/
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from .vtt import vtt_to_text

LOGIN_POLL_SECONDS = 2
LOGIN_TIMEOUT_SECONDS = 600

CURRICULUM = (
    "https://www.udemy.com/api-2.0/courses/{course_id}/subscriber-curriculum-items/"
    "?page_size=1000"
    "&fields[lecture]=id,title,object_index,asset"
    "&fields[chapter]=id,title,object_index"
    "&fields[asset]=captions,title,asset_type"
    "&fields[caption]=id,locale_id,url,source"
)
LECTURE = (
    "https://www.udemy.com/api-2.0/users/me/subscribed-courses/{course_id}"
    "/lectures/{lecture_id}/?fields[lecture]=asset&fields[asset]=captions"
    "&fields[caption]=id,locale_id,url,source"
)
ME = "https://www.udemy.com/api-2.0/contexts/me/?header=True"

NO_TRANSCRIPT = "[No transcript available for this lecture]"
HEADER = "Course: {course}\nChapter: {chapter}\nLecture: {lecture}\n" + "-" * 40 + "\n\n"


class FetchError(RuntimeError):
    pass


def _safe(name: str) -> str:
    name = "".join(c for c in name if c not in '/\\:*?"<>|').strip()
    return re.sub(r"\s+", " ", name) or "untitled"


def _pick_caption(captions: list[dict]) -> str | None:
    """Prefer English, then anything - matching the extension's behaviour."""
    if not captions:
        return None
    for cap in captions:
        if str(cap.get("locale_id", "")).lower().startswith("en"):
            return cap.get("url")
    return captions[0].get("url")


def _course_id(page) -> int:
    """Read the course id out of the loaded page.

    Udemy has moved this around over the years, so try the known carriers in
    order rather than betting on one.
    """
    strategies = [
        "document.body?.dataset?.clpCourseId",
        "document.querySelector('[data-clp-course-id]')?.dataset?.clpCourseId",
        "document.querySelector('.ud-component--course-taking--app')"
        "?.dataset?.moduleArgs && JSON.parse(document.querySelector("
        "'.ud-component--course-taking--app').dataset.moduleArgs).courseId",
        "window.UD?.course?.id",
    ]
    for js in strategies:
        try:
            value = page.evaluate(f"() => {js}")
        except Exception:  # noqa: BLE001 - a failing probe just means "try the next"
            continue
        if value:
            return int(value)

    m = re.search(r'"course_id"\s*:\s*(\d+)|data-clp-course-id="(\d+)"', page.content())
    if m:
        return int(m.group(1) or m.group(2))

    raise FetchError(
        "could not determine the course id from the page. Make sure the URL "
        "points at a course you are enrolled in, and that it finished loading."
    )


def _api(page, url: str) -> dict:
    response = page.request.get(url, headers={"Accept": "application/json, text/plain, */*"})
    if not response.ok:
        raise FetchError(f"{url.split('?')[0]} returned HTTP {response.status}")
    return response.json()


def _wait_for_login(page) -> None:
    import time

    deadline = time.time() + LOGIN_TIMEOUT_SECONDS
    announced = False
    while time.time() < deadline:
        try:
            me = _api(page, ME)
            if (me.get("header") or {}).get("user", {}).get("id"):
                return
        except Exception:  # noqa: BLE001 - not logged in yet
            pass
        if not announced:
            print("\n  Waiting for you to sign in to Udemy in the browser window...")
            print("  (this tool never sees or stores your credentials)\n")
            announced = True
        time.sleep(LOGIN_POLL_SECONDS)
    raise FetchError("timed out waiting for Udemy login")


def fetch(url: str, workdir: Path, *, headless: bool = False) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FetchError(
            "fetching by URL needs Playwright:\n"
            "    pip install playwright && playwright install chromium\n"
            "Or download the transcripts with the Udemy Transcript Extractor "
            "extension and pass the .zip to --input instead."
        ) from exc

    profile = workdir / ".browser-profile"
    profile.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        # A persistent profile means you log in once, not once per run.
        context = pw.chromium.launch_persistent_context(str(profile), headless=headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            _wait_for_login(page)
            course_id = _course_id(page)
            print(f"  course id {course_id}")

            items = _api(page, CURRICULUM.format(course_id=course_id)).get("results", [])
            course = page.title().split(" | ")[0].strip() or f"course-{course_id}"
            root = _write_tree(page, course_id, course, items, workdir)
        finally:
            context.close()

    _zip(root, workdir / f"{root.name}-transcripts.zip")
    return root


def _write_tree(page, course_id: int, course: str, items: list[dict], workdir: Path) -> Path:
    root = workdir / _safe(course)
    root.mkdir(parents=True, exist_ok=True)

    chapter_no = 0
    lecture_no = 0
    chapter_dir: Path | None = None
    chapter_title = "Course Content"
    written = missing = 0

    for item in items:
        kind = item.get("_class")
        if kind == "chapter":
            chapter_no += 1
            lecture_no = 0
            chapter_title = item.get("title") or f"Section {chapter_no}"
            chapter_dir = root / f"{chapter_no:02d}-{_safe(chapter_title)}"
            chapter_dir.mkdir(parents=True, exist_ok=True)
            continue

        if kind != "lecture":
            continue  # quizzes, practice tests, assignments

        if chapter_dir is None:  # lectures before any chapter header
            chapter_no = 1
            chapter_dir = root / "01-Course Content"
            chapter_dir.mkdir(parents=True, exist_ok=True)

        lecture_no += 1
        title = item.get("title") or f"Lecture {lecture_no}"
        body = _lecture_text(page, course_id, item)
        if body is None:
            body, kind_note = NO_TRANSCRIPT, True
            missing += 1
        else:
            kind_note = False
            written += 1

        path = chapter_dir / f"{lecture_no:02d}-{_safe(title)}.txt"
        path.write_text(
            HEADER.format(course=course, chapter=chapter_title, lecture=title) + body + "\n",
            encoding="utf-8",
        )
        print(f"    {'--' if kind_note else 'ok'}  {chapter_no:02d}.{lecture_no:02d} {title[:56]}")

    print(f"\n  {written} lecture(s) with transcripts, {missing} without")
    _write_combined(root, course)
    return root


def _lecture_text(page, course_id: int, item: dict) -> str | None:
    asset = item.get("asset") or {}
    captions = asset.get("captions")
    # The curriculum call usually inlines captions; fall back to the per-lecture
    # endpoint when it doesn't.
    if captions is None:
        try:
            detail = _api(page, LECTURE.format(course_id=course_id, lecture_id=item["id"]))
            captions = (detail.get("asset") or {}).get("captions") or []
        except Exception:  # noqa: BLE001
            return None

    url = _pick_caption(captions or [])
    if not url:
        return None
    try:
        response = page.request.get(url)
        if not response.ok:
            return None
        text = vtt_to_text(response.text())
    except Exception:  # noqa: BLE001
        return None
    return text or None


def _write_combined(root: Path, course: str) -> None:
    """The extension also ships a single searchable file; match that."""
    from datetime import datetime, timezone

    parts = [
        f"TRANSCRIPT: {course}",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "=" * 80,
        "",
    ]
    for section in sorted(p for p in root.iterdir() if p.is_dir()):
        parts.append(f"## {section.name.split('-', 1)[-1]}\n")
        for lec in sorted(section.glob("*.txt")):
            body = lec.read_text(encoding="utf-8").split("-" * 40, 1)[-1].strip()
            parts.append(f"### {lec.stem.split('-', 1)[-1]}\n\n{body}\n")
    (root / "_full-transcript.txt").write_text("\n".join(parts), encoding="utf-8")


def _zip(root: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root.parent))
    print(f"  saved {archive}")
