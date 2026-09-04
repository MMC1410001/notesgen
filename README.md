# notesgen

Turns Udemy course transcripts into structured revision notes as `.docx`
files you upload to Google Docs — so you can watch the course instead of
pausing to write notes.

## Getting transcripts

Easiest path — the **[Udemy Transcript Extractor](https://chromewebstore.google.com/detail/udemy-transcript-extracto/oimlbilmdnimabebeilpndlndfoepopd)**
Chrome extension. Open a course you're enrolled in, click the extension, choose
*Extract transcripts*; about two minutes later you get a `.zip`. Hand that zip
straight to `--input`. It runs entirely in your browser and reaches Udemy's
internal API through your own logged-in session.

`notesgen` can also fetch a course itself — see [Fetching by URL](#fetching-by-url).

## Input layout

```
<course>/
    11-Getting Started With LangGraph/
        01-Introduction To LangGraph.txt
    _full-transcript.txt          <- ignored
```

Each `.txt` starts with a `Course: / Chapter: / Lecture:` header followed by a
dashed rule; everything after it is the transcript body.

**`--input` accepts any of three things** and figures out which it got:

| You have | Pass |
|---|---|
| The extension's `.zip` | `-i "MyCourse-transcripts.zip"` |
| An extracted folder | `-i "path/to/MyCourse"` |
| Its parent folder | `-i "path/to"` — it descends automatically |
| Only the course URL | `-i "https://www.udemy.com/course/..."` |

## Usage

```bash
# See the course tree and which lectures have broken captions. No model calls.
python3 -m notesgen discover -i "<zip | folder | url>"

# Download transcripts only (unpack a zip, or fetch a URL) and stop
python3 -m notesgen fetch -i "<zip | folder | url>"

# Generate Markdown notes (per lecture + per section + a course index)
python3 -m notesgen generate -i "<zip | folder | url>"

# Add Mermaid diagrams per section (reads existing notes; ~27 calls)
python3 -m notesgen diagram -i "<zip | folder | url>"

# Assemble .docx from the Markdown
python3 -m notesgen build -i "<zip | folder | url>"

# Write .html / .txt / .md for copy-pasting (no model calls)
python3 -m notesgen export -i "<zip | folder | url>"

# Upload to Google Docs
python3 -m notesgen push -i "<zip | folder | url>"

# Everything: generate, diagram, build .docx, export every format
python3 -m notesgen run -i "<zip | folder | url>"
```

(`--course` is still accepted as an alias for `--input`.)

## Choosing a provider

`generate` is the only command that calls a model. Pick the backend with
`--provider`, or set `NOTESGEN_PROVIDER`. With nothing configured it uses the
`claude` CLI when installed, then whichever API key it finds.

| Provider | Auth | Default model | Notes |
|---|---|---|---|
| `claude-cli` | your Claude Code subscription | `sonnet` | **No API key, no per-token bill.** The default. |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5` | `--model claude-opus-5` for the strongest |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` | |
| `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash` | cheapest per token |

Keys come from the environment or a `.env` in the project root — copy
`.env.example` to `.env`. An exported variable always beats the file. Selecting
a provider whose key is missing stops the run immediately and names the
variable to set, rather than failing 183 lectures one at a time.

API providers need their SDK: `pip install anthropic` / `openai` /
`google-genai`. Only the one you use.

## Diagrams

`notesgen diagram` adds system-structure, control-flow and state diagrams to
each section — the AI writes them as **Mermaid**, so labels and arrows are
correct rather than the smeared text a diffusion image model produces on
technical material. The prompt explicitly rejects mind maps, concept bubbles
and course-structure diagrams; a section with nothing worth drawing says so
instead of padding.

It reads the **notes that already exist**, not the transcripts, so adding
diagrams to a finished course costs ~27 calls rather than regenerating every
lecture. Output goes to its own `_diagrams.md` per section, so nothing already
generated is rewritten.

| Format | How diagrams appear |
|---|---|
| `html/` | rendered live by mermaid.js; pastes into Word as a picture |
| `docx/` | rendered to PNG and embedded |
| `txt/`, `export-md/` | diagram source (GitHub and Obsidian render it natively) |

`.docx` embedding needs a renderer: `npm install -g @mermaid-js/mermaid-cli`,
or let `npx` fetch it on first run. Without one the `.docx` shows the diagram
source and says so — it never fails the build. Rendered PNGs are cached by
content hash, so rebuilding is instant.

## Google Docs

```bash
pip install google-api-python-client google-auth-oauthlib
python3 -m notesgen push -i "<zip | folder | url>"
```

Builds one `.docx` for the whole course and uploads it to Drive asking for
conversion to a native Google Doc. Heading styles become the Docs outline
(**View → Show outline**) and the diagram images come along inside the file.
`--split-sections` uploads one Doc per section into a Drive folder instead.

First run prints instructions for creating a one-time OAuth desktop client;
the token is cached in `.gdocs/` (gitignored) so later runs are silent. The
scope requested is `drive.file`, which only grants access to files this tool
itself creates — it cannot see the rest of your Drive. Re-running updates the
same document rather than creating duplicates, so a shared link keeps working.

**On tabs:** the Docs API cannot create them. Both it and Apps Script expose
only `getTab` / `getTabs` / `getActiveTab` / `setActiveTab` — there is no
`addTab` in either — so navigation is the heading outline, not tabs.

## Fetching by URL

```bash
pip install playwright && playwright install chromium
python3 -m notesgen fetch -i "https://www.udemy.com/course/your-course/"
```

A real Chromium window opens on the course page. **You** sign in — including
SSO and 2FA — and the fetch then runs inside that authenticated session,
calling the same undocumented Udemy endpoints the extension uses:

```
/api-2.0/courses/{id}/subscriber-curriculum-items/
/api-2.0/users/me/subscribed-courses/{id}/lectures/{id}/
```

The tool never sees, extracts, or stores your credentials; the session stays in
the browser profile under `input/.browser-profile`, so you sign in once rather
than once per run. Output is written as the same folder layout and `.zip` the
extension produces.

Two things worth knowing: those endpoints are internal and can change without
notice, and Udemy's terms restrict scraping course content. The extension route
is the lower-friction and lower-exposure option; this exists for when you'd
rather not leave the terminal.

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

- Python 3.10+, `pyyaml`, `python-docx`.
- **One** of: the `claude` CLI on PATH and logged in (uses the Claude Code
  subscription — no API key, no per-token bill; the code deliberately avoids
  `--bare`, which would force `ANTHROPIC_API_KEY` auth instead), or an API key
  for Anthropic / OpenAI / Gemini plus that provider's SDK.
- Optional, only for `--input <udemy url>`: `playwright` +
  `playwright install chromium`. Zip and folder input never need it.
