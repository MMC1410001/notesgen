"""Assemble generated Markdown into the .docx files you upload to Drive."""

from __future__ import annotations

from pathlib import Path

from .discover import Section
from .docx_build import build_section_doc
from .generate import md_path, rollup_path

# Google Docs gets sluggish on very long documents. Section 03 of the
# reference course is 40 lectures, so oversized sections are split.
MAX_WORDS_PER_DOC = 25_000

UPLOAD_NOTE = """\
# Uploading these notes to Google Docs

1. Open <https://drive.google.com> and create a folder for the course.
2. Drag every `.docx` file in this folder into it.
3. Double-click a file, then **File > Save as Google Docs** (or right-click >
   *Open with* > *Google Docs*). The heading hierarchy becomes the outline
   pane: **View > Show outline**.

Read `00 - Course Index.docx` first; it links the sections together.

Files marked with `[!]` inside the notes flag places where the lecture's
audio did not cover what was on screen, or where captions were missing
entirely. Those gaps are deliberate - nothing there was inferred.
"""


def _safe(name: str) -> str:
    return "".join(c for c in name if c not in '/\\:*?"<>|').strip()


def _chunk(parts: list[str], max_words: int) -> list[list[str]]:
    """Split a section's parts into documents of at most max_words each."""
    total = sum(len(p.split()) for p in parts)
    if total <= max_words or len(parts) < 2:
        return [parts]

    chunks: list[list[str]] = [[]]
    running = 0
    for part in parts:
        words = len(part.split())
        if running and running + words > max_words:
            chunks.append([])
            running = 0
        chunks[-1].append(part)
        running += words
    return [c for c in chunks if c]


def build(
    course: str,
    sections: list[Section],
    md_root: Path,
    docx_root: Path,
    *,
    max_words: int = MAX_WORDS_PER_DOC,
) -> list[Path]:
    docx_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    index_md = md_root / "_course-index.md"
    if index_md.exists():
        written.append(
            build_section_doc(
                course,
                "Master index",
                [index_md.read_text(encoding="utf-8")],
                docx_root / "00 - Course Index.docx",
            )
        )

    for section in sections:
        parts: list[str] = []

        overview = rollup_path(md_root, section)
        if overview.exists():
            parts.append(overview.read_text(encoding="utf-8"))

        for lec in section.lectures:
            p = md_path(md_root, lec)
            if p.exists():
                parts.append(p.read_text(encoding="utf-8"))

        if not parts:
            continue

        title = f"Section {section.idx}: {section.title}"
        chunks = _chunk(parts, max_words)
        for n, chunk in enumerate(chunks, start=1):
            suffix = f" (Part {n} of {len(chunks)})" if len(chunks) > 1 else ""
            name = _safe(f"{section.idx} - {section.title}{suffix}") + ".docx"
            written.append(
                build_section_doc(
                    title + suffix,
                    f"{course} - {len(section.lectures)} lectures",
                    chunk,
                    docx_root / name,
                )
            )

    (docx_root / "UPLOAD.md").write_text(UPLOAD_NOTE, encoding="utf-8")
    return written
