# notesgen

Turns Udemy course transcripts into structured revision notes as `.docx`
files you upload to Google Docs — so you can watch the course instead of
pausing to write notes.

This handles stages 2–4 of the pipeline. Stage 1 (pulling captions out of
Udemy) happens elsewhere; this tool reads the transcript tree that produces.

## Input layout

```
<course>/
    11-Getting Started With LangGraph/
        01-Introduction To LangGraph.txt
    _full-transcript.txt          <- ignored
```

Each `.txt` starts with a `Course: / Chapter: / Lecture:` header followed by a
dashed rule; everything after it is the transcript body.

## Usage

```bash
# See the course tree and which lectures have broken captions. No model calls.
python3 -m notesgen discover --course "<course path>"

# Generate Markdown notes (per lecture + per section + a course index)
python3 -m notesgen generate --course "<course path>"

# Assemble .docx from the Markdown
python3 -m notesgen build --course "<course path>"

# Both
python3 -m notesgen run --course "<course path>"
```

Useful flags:

| Flag | Effect |
|---|---|
| `--section 11 --section 12` | limit to those sections (repeatable) |
| `--only "11-*/01-*"` | glob over `<section-dir>/<lecture-file>` |
| `--workers 3` | parallel model calls (default 3) |
| `--model sonnet` | model passed to `claude -p` |
| `--force` | regenerate even if already current |
| `--glossary path.yml` | course-specific term corrections |
| `--max-words 25000` | split oversized sections into Part 1/2/... |

## Output

```
output/<course>/
    md/                     one .md per lecture, plus _section-overview.md
    docx/                   one .docx per section, plus 00 - Course Index.docx
    manifest.json           what has been generated, for resume
```

Upload: drag the `docx/` contents into drive.google.com, then open each with
Google Docs. Headings map to Word heading styles, so **View → Show outline**
gives you a working navigation pane. See `docx/UPLOAD.md`.

## What the output looks like

[`docs/example-note.md`](docs/example-note.md) is one lecture's notes as
generated — a single sample. The notes for a full course are not published
here; they are derived from paid course content and stay local (see
`.gitignore`).

## How it works, and the two things that matter

**Term correction (`glossary.yml`).** Udemy's auto-captions mangle product
names consistently — *Landgraf* / *line graph* for LangGraph, *Lankin* for
LangChain, *genetic AI* for agentic AI, *grok* for Groq. One lecture in the
reference course contained 36 such errors. They are repaired by regex before
the model sees the text, so it never has to guess.

There is a safety rule in that file worth respecting: **never add a variant
that is also an ordinary English word.** `Face`/`Phase` → `FAISS` is tempting
and would corrupt every legitimate use of those words across the course.

**Grounding.** Transcripts are audio-only: code the instructor typed on screen
without narrating is simply absent. The prompt forbids reconstructing it and
requires the model to emit

> [!] Code shown on screen, not described in the audio.

Lectures whose captions failed outright (under 200 words) are **never sent to
the model at all** — they get a fixed stub saying so. A confident-looking page
built from 6 words is worse than an honest gap. Sections where every lecture
is a stub skip their rollup too.

Notes therefore reflect *what the course taught*, not what is objectively
true. Where the instructor is loose — calling LangGraph a DAG, for instance,
when its whole point is that it supports cycles — the notes follow the
lecture. That is deliberate: they are revision notes for this course.

## Resume

`manifest.json` keys each unit by a SHA-256 of its source text. Re-running
skips anything unchanged, so a run interrupted by a usage limit picks up where
it stopped — just run the same command again. `--force` overrides.

Failures are per-lecture and never abort the run; re-run to retry only those.

## Requirements

- `claude` CLI on PATH, logged in (uses the Claude Code subscription — no API
  key, no per-token bill). Note the code deliberately avoids `--bare`, which
  would force `ANTHROPIC_API_KEY` auth instead.
- Python 3.10+, `pyyaml`, `python-docx`.
