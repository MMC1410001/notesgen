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

# Write .html / .txt / .md for copy-pasting (no model calls)
python3 -m notesgen export --course "<course path>"

# Everything: generate, then build .docx and export every format
python3 -m notesgen run --course "<course path>"
```

## Choosing an output format

`generate` is the only command that costs anything. Every format below is
local string formatting — producing all three for a 183-lecture course takes
under a second and costs **nothing**. Format has no bearing on token usage.

| You want to | Use | How |
|---|---|---|
| Paste into Word / Google Docs **with formatting** | `html/` | Open in browser, Cmd+A, Cmd+C, paste |
| Paste anywhere at all — email, Notes, a ticket, another AI | `txt/` | Open, copy |
| Notion, Obsidian, GitHub | `export-md/` | One file per section |
| Upload files to Google Drive | `docx/` | Drag in, open with Google Docs |

`00 - Complete Course.*` in each folder holds every section in one file.

Useful flags:

| Flag | Effect |
|---|---|
| `--section 11 --section 12` | limit to those sections (repeatable) |
| `--only "11-*/01-*"` | glob over `<section-dir>/<lecture-file>` |
| `--workers 3` | parallel model calls (default 3) |
| `--model sonnet` | model passed to `claude -p` |
| `--force` | regenerate even if already current |
| `--glossary path.yml` | course-specific term corrections |
| `--format html` | export only that format (repeatable) |
| `--no-whole-course` | skip the combined all-sections file |
| `--no-docx` | on `run`, skip the .docx step |
| `--max-words 25000` | split oversized sections into Part 1/2/... |

## Output

```
output/<course>/
    md/                     one .md per lecture, plus _section-overview.md
    docx/                   one .docx per section, plus 00 - Course Index.docx
    html/                   per section + whole course, for pasting
    txt/                    per section + whole course, plain text
    export-md/              per section + whole course, concatenated Markdown
    manifest.json           what has been generated, for resume
```

Each export folder carries a `PASTE.md` describing its workflow, and `docx/`
carries `UPLOAD.md`. Headings map to real heading styles in both `.docx` and
`.html`, so Google Docs' **View → Show outline** pane works either way.

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

## Architecture

One Markdown parser, four renderers. `mdparse.py` turns the generated notes
into typed blocks and inline spans; `assemble.py` decides what goes into each
document and how oversized sections split. The `.docx`, HTML and plain-text
renderers all consume those, so a fix to tables or emphasis lands in every
format at once rather than in one of three copies.

`python3 tests_mdparse.py` covers the parser. The emphasis cases there matter
more than they look: these notes cover a Python course, so `**kwargs`, `x**2`
and `{**d1, **d2}` appear constantly in prose, and a loose bold regex silently
eats them. Markdown's own rule — emphasis markers may not sit beside a space —
is what protects them.

## Requirements

- `claude` CLI on PATH, logged in (uses the Claude Code subscription — no API
  key, no per-token bill). Note the code deliberately avoids `--bare`, which
  would force `ANTHROPIC_API_KEY` auth instead.
- Python 3.10+, `pyyaml`, `python-docx`.
