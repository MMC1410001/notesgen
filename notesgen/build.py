"""Assemble generated Markdown into the .docx files you upload to Drive."""

from __future__ import annotations

from pathlib import Path

from .assemble import MAX_WORDS_PER_DOC, collect
from .discover import Section
from .docx_build import build_section_doc

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

Prefer to paste rather than upload? See `../html/` - open one in a browser,
select all, copy, and paste straight into Word or Google Docs.
"""


def build(
    course: str,
    sections: list[Section],
    md_root: Path,
    docx_root: Path,
    *,
    max_words: int = MAX_WORDS_PER_DOC,
) -> list[Path]:
    docx_root.mkdir(parents=True, exist_ok=True)
    written = [
        build_section_doc(
            doc.title,
            doc.subtitle,
            doc.parts,
            docx_root / (doc.basename + ".docx"),
        )
        for doc in collect(course, sections, md_root, max_words=max_words)
    ]
    (docx_root / "UPLOAD.md").write_text(UPLOAD_NOTE, encoding="utf-8")
    return written
