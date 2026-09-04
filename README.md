# notesgen

Turn a Udemy course into structured revision notes — so you can watch the
course instead of pausing every minute to write things down.

Point it at a course. It reads the transcripts, writes notes for every lecture,
draws diagrams, and hands you the result as a Google Doc, a Word file, a web
page, or plain text.

**What you get, per lecture:**

- **Summary** — objective, key concepts with definitions, takeaways
- **Cheat-sheet** — the syntax, commands and gotchas worth revisiting
- **Recall** — question/answer pairs for active revision
- **Code walkthrough** — the code the instructor actually talked through

Plus a per-section overview with diagrams, and a course-level index.

A real run: a 26-section, 183-lecture course became 202,000 words of notes and
61 diagrams across 28 documents.

---

## Contents

1. [Before you start](#1-before-you-start)
2. [Install](#2-install)
3. [Get the transcripts](#3-get-the-transcripts)
4. [Choose who writes the notes](#4-choose-who-writes-the-notes)
5. [Generate the notes](#5-generate-the-notes)
6. [Get your notes out](#6-get-your-notes-out)
7. [Google Docs setup, in full](#7-google-docs-setup-in-full)
8. [Command reference](#8-command-reference)
9. [Troubleshooting](#9-troubleshooting)
10. [How it works, and what it will not do](#10-how-it-works-and-what-it-will-not-do)

---

## 1. Before you start

You need:

- **Python 3.10 or newer.** Check with `python3 --version`. If that fails,
  install it from [python.org](https://www.python.org/downloads/).
- **A Udemy course you are enrolled in.** This reads captions from courses on
  your own account; it cannot reach anything you have not bought.
- **Something to write the notes.** Either the
  [Claude Code](https://claude.com/claude-code) CLI (uses your existing
  subscription, no API key, no per-token bill) or an API key from Anthropic,
  OpenAI or Google. Section 4 covers both.

Optional, and only if you want them:

- **Google account** — to publish notes straight into Google Docs (section 7)
- **Node.js** — to render diagrams into Word documents. Diagrams work in the
  web page output without it.

**Time and cost.** A 180-lecture course takes about an hour to process. On the
Claude Code subscription there is no extra charge. On a paid API it is roughly
$2–6 for a whole course depending on the model.

---

## 2. Install

```bash
git clone https://github.com/MMC1410001/notesgen.git
cd notesgen
python3 -m pip install pyyaml python-docx
```

That covers everything core: notes, Word documents, web pages, plain text.

Two features need extra packages. Install only what you want:

```bash
python3 -m notesgen setup                  # show what is and is not installed
python3 -m notesgen setup --extra udemy    # fetch transcripts from a course URL
python3 -m notesgen setup --extra gdocs    # publish to Google Docs
python3 -m notesgen setup --extra api      # use Anthropic / OpenAI / Gemini APIs
```

Check it works:

```bash
python3 -m notesgen --help
```

---

## 3. Get the transcripts

Two ways. **The browser extension is easier and is the recommended route.**

### Option A — the browser extension (recommended)

Install
**[Udemy Transcript Extractor](https://chromewebstore.google.com/detail/udemy-transcript-extracto/oimlbilmdnimabebeilpndlndfoepopd)**
for Chrome.

1. Open a course you are enrolled in.
2. Click the extension icon → **Extract transcripts**.
3. Wait about two minutes for a 200-lecture course. You get a `.zip`.

That zip is what you feed in. Everything runs in your browser; nothing is
uploaded anywhere.

### Option B — let notesgen fetch them

```bash
python3 -m notesgen setup --extra udemy
python3 -m notesgen fetch -i "https://www.udemy.com/course/YOUR-COURSE-SLUG/"
```

A Chrome window opens on the course page. **Sign in the way you normally do** —
password, Google, SSO, 2FA, whatever. Then leave it alone: the download starts
by itself and saves a `.zip` under `input/`.

Your credentials are never seen, typed or stored by this tool. The session
stays in a browser profile under `input/.browser-profile`, so you only sign in
once. Under the hood it calls the same undocumented Udemy endpoints the
extension does, from inside your own logged-in browser.

If Udemy keeps asking whether you are human, see
[Troubleshooting](#9-troubleshooting).

### What `--input` accepts

You never have to unzip anything or find the "right" folder:

| You have | Pass |
|---|---|
| The extension's zip | `-i "MyCourse-transcripts.zip"` |
| An extracted folder | `-i "path/to/MyCourse"` |
| The folder *above* it | `-i "path/to"` — it finds the course inside |
| Only the course URL | `-i "https://www.udemy.com/course/..."` |

Sanity-check before spending anything — this makes no model calls:

```bash
python3 -m notesgen discover -i "MyCourse-transcripts.zip"
```

It prints every section, the lecture count, and flags any lecture whose
captions failed.

---

## 4. Choose who writes the notes

`generate` is the only command that costs anything. Everything else is local.

| Provider | What you need | Cost |
|---|---|---|
| **`claude-cli`** *(default)* | [Claude Code](https://claude.com/claude-code) installed and signed in | Included in your subscription |
| `anthropic` | `ANTHROPIC_API_KEY` from [console.anthropic.com](https://console.anthropic.com/) | Pay per token |
| `openai` | `OPENAI_API_KEY` from [platform.openai.com](https://platform.openai.com/api-keys) | Pay per token |
| `gemini` | `GEMINI_API_KEY` from [aistudio.google.com](https://aistudio.google.com/apikey) | Pay per token, cheapest |

With Claude Code installed you need to do nothing — it is picked automatically.

To use an API instead, copy the example file and fill in one key:

```bash
cp .env.example .env
```

```ini
NOTESGEN_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
```

`.env` is gitignored. Environment variables override it. You can also pick per
run with `--provider gemini`.

If you select a provider whose key is missing, the run stops immediately and
tells you which variable to set — it does not fail 183 lectures one at a time.

---

## 5. Generate the notes

```bash
python3 -m notesgen generate -i "MyCourse-transcripts.zip"
```

This writes one Markdown file per lecture, a section overview for each section,
and a course index. Expect roughly an hour for 180 lectures.

**You can stop it at any time.** Progress is checkpointed after every lecture,
so re-running the same command picks up where it left off and skips everything
already done. If you hit a usage limit, just run it again later.

Add diagrams (optional, about 27 extra calls):

```bash
python3 -m notesgen diagram -i "MyCourse-transcripts.zip"
```

These are system-structure and flow diagrams drawn from your notes — not
decorative clip art. Sections with nothing worth drawing say so instead of
padding.

---

## 6. Get your notes out

```bash
python3 -m notesgen build  -i "MyCourse-transcripts.zip"   # Word (.docx)
python3 -m notesgen export -i "MyCourse-transcripts.zip"   # web page, text, markdown
python3 -m notesgen push   -i "MyCourse-transcripts.zip"   # Google Docs
```

All of these are **free and instant** — local formatting, no model calls. The
output format has no bearing on cost.

| You want to | Use | How |
|---|---|---|
| Read in Google Docs | `push` | see [section 7](#7-google-docs-setup-in-full) |
| Paste into Word **with formatting** | `html/` | open in a browser, Ctrl/Cmd+A, copy, paste |
| Paste anywhere — email, Notion, a chat box | `txt/` | open, copy |
| Notion, Obsidian, GitHub | `export-md/` | one file per section |
| Upload files to Drive yourself | `docx/` | drag in, open with Google Docs |

Everything lands under `output/<course name>/`. Each folder has a short
`PASTE.md` or `UPLOAD.md` explaining what to do with it. `00 - Complete
Course.*` holds the entire course in one file, and `LINKS.md` holds your
Google Docs links once you have published.

**Do it all in one go:**

```bash
python3 -m notesgen run -i "https://www.udemy.com/course/YOUR-COURSE-SLUG/"
```

That fetches, generates, diagrams, builds and exports.

### Diagrams in Word documents

Diagrams render live in the web page output with no setup. To embed them as
images in `.docx` and Google Docs you need a renderer:

```bash
npm install -g @mermaid-js/mermaid-cli
```

Without it, `.docx` shows the diagram source and says so — it never fails the
build. If you have Node but not the package, it is fetched automatically on
first use (that download takes a few minutes once).

---

## 7. Google Docs setup, in full

This is the fiddliest part, and it is entirely Google's doing. It takes about
five minutes, once. If you would rather skip it: run `export` and drag the
`docx/` files into Drive by hand — same result, no setup.

### 7.1 Install the packages

```bash
python3 -m notesgen setup --extra gdocs
```

### 7.2 Create a Google Cloud project

1. Go to **[console.cloud.google.com](https://console.cloud.google.com/)** and
   sign in.
2. Click the project dropdown in the top bar → **New Project**.
3. Name it anything (`notesgen` is fine) → **Create**.
4. Wait for it to be created, then make sure it is **selected** in that
   dropdown. Most problems below come from being in the wrong project.

### 7.3 Enable the Drive API

1. Left menu → **APIs & Services → Library**.
2. Search for **Google Drive API**.
3. Open it → **Enable**.

### 7.4 Configure the consent screen

1. **APIs & Services → OAuth consent screen**.
2. User type: **External** → **Create**.
3. Fill the required fields — app name (anything), your own email for both
   *User support email* and *Developer contact*. Everything else can stay
   empty.
4. Save and continue through the Scopes and Test users steps.

### 7.5 Add yourself as a test user — do not skip this

1. Still on **OAuth consent screen**, find **Test users** → **+ Add users**.
2. Enter **the Google address you will sign in with**.
3. Save.

Skip this and sign-in fails with `Error 403: access_denied` before you ever see
a consent screen. It is the single most common thing to get wrong.

*(Alternatively click **Publish app**. It stays unverified, so you still get a
warning screen, but any account can then authorise.)*

### 7.6 Create the OAuth client

1. **APIs & Services → Credentials → + Create credentials → OAuth client ID**.
2. Application type: **Desktop app**. Name it anything → **Create**.
3. **Download JSON**.
4. Save that file into your notesgen folder as exactly:

```
.gdocs/google-credentials.json
```

```bash
mkdir -p .gdocs
mv ~/Downloads/client_secret_*.json .gdocs/google-credentials.json
```

`.gdocs/` is gitignored, so it is never committed.

### 7.7 Push

```bash
python3 -m notesgen push -i "MyCourse-transcripts.zip"
```

A browser opens once. Sign in **with the address you added as a test user**.

You will see **"Google hasn't verified this app"** — expected for your own
unpublished client. Click **Advanced → Go to (your app name) (unsafe)**.

The permission requested is `drive.file`: access limited to files this tool
creates. It cannot see the rest of your Drive.

When it finishes you get a link. Open it and use **View → Show outline** for
the navigation pane.

### Finding the link again

You do not have to keep the terminal open. The link is saved and shown in
several places:

```bash
python3 -m notesgen links -i "MyCourse-transcripts.zip"
```

It is also printed at the end of `discover` and `run`, and written to
`output/<course>/LINKS.md` as a clickable file next to your notes.

Re-running updates the same document instead of making duplicates, so any link
you have shared keeps working. Add `--split-sections` for one document per
section instead of one big one.

---

## 8. Command reference

| Command | What it does | Costs |
|---|---|---|
| `discover` | List the course, flag broken captions | free |
| `fetch` | Download transcripts (URL) or unpack a zip | free |
| `generate` | Write the notes | **the only paid step** |
| `diagram` | Add diagrams from existing notes | small |
| `build` | Make `.docx` | free |
| `export` | Make `.html`, `.txt`, `.md` | free |
| `push` | Publish to Google Docs | free |
| `links` | Show where a course's notes live | free |
| `run` | Everything above, in order | — |
| `setup` | Install optional extras | free |

Useful flags:

| Flag | Effect |
|---|---|
| `-i`, `--input` | zip, folder, or Udemy URL |
| `--section 11 --section 12` | limit to those sections |
| `--only "11-*/01-*"` | limit to matching lectures |
| `--provider gemini` | pick the model backend |
| `--model MODEL` | override the model |
| `--workers 3` | parallel calls (default 3) |
| `--force` | redo work already done |
| `--no-diagrams`, `--no-docx`, `--no-images` | skip steps |
| `--split-sections` | one Google Doc per section |
| `--attach [PORT]` | drive a Chrome you launched yourself |

---

## 9. Troubleshooting

**Udemy keeps asking "are you human?"**
Close it and try attaching to your own browser instead:

```bash
./attach-chrome.sh
# in another terminal, once you are logged in there:
python3 -m notesgen fetch --attach -i "https://www.udemy.com/course/..."
```

This drives a Chrome you started, which is ordinary browsing rather than
automation. Failing that, use the extension (option A in section 3) — it always
works, because it *is* a browser.

**Udemy returns 403**
You are signed into the wrong account, or not enrolled in that course. Check
the browser window is on the account that owns it.

**`Error 403: access_denied` from Google**
You are not on the test-user list — see [7.5](#75-add-yourself-as-a-test-user--do-not-skip-this).
Also confirm you are in the right Cloud project and that the Drive API is
enabled.

**"Google hasn't verified this app"**
Expected. Click **Advanced → Go to (app) (unsafe)**. It is your own client.

**`provider 'x' needs Y_API_KEY`**
Set that variable in `.env` or your environment, or drop `--provider` to use
Claude Code.

**A lecture failed**
Re-run the same command. Finished work is skipped; only failures are retried.

**Notes for one lecture say the transcript was missing**
Udemy had no usable captions for it. That is reported rather than guessed at —
watch that lecture directly.

---

## 10. How it works, and what it will not do

### The pipeline

```
transcripts → fix caption errors → notes per lecture → section overviews
           → course index → diagrams → .docx / .html / .txt / .md / Google Docs
```

### Caption errors are fixed before the model sees them

Udemy's auto-captions mangle product names consistently — *Landgraf* and *line
graph* for LangGraph, *Lankin* for LangChain, *genetic AI* for agentic AI,
*grok* for Groq. One lecture in the test course had 36 such errors; the course
had 1,200. `glossary.yml` repairs them by pattern before anything is generated.

Add your own for your subject. One rule matters: **never add a variant that is
also an ordinary English word.** `Face`/`Phase` → `FAISS` is tempting and would
corrupt every legitimate use of those words.

### It tells you what it does not know

Transcripts are audio only. Code the instructor typed on screen without
narrating is simply absent, so the notes mark it:

> ⚠️ Code shown on screen, not described in the audio.

Lectures whose captions failed entirely are **never sent to the model** — they
get an honest "no transcript" note. A confident-looking page built from six
words is worse than an admitted gap.

Notes reflect *what the course taught*, not what is objectively true. Where an
instructor is loose, the notes follow the lecture. They are revision notes for
that course.

### Limits worth knowing

- **Google Docs tabs cannot be created by any API.** The Docs API and Apps
  Script both offer only `getTab`/`getTabs`/`getActiveTab`/`setActiveTab`.
  Navigation is the heading outline instead.
- **Diagrams are Mermaid, authored by the model** — flowcharts, sequence and
  state diagrams. Not image-model illustrations, which garble text labels on
  technical material.
- **Very long documents load slowly in Google Docs.** Use `--split-sections`.
- **Udemy's terms restrict redistributing course content.** These notes are
  derived from material you paid for; keep them for yourself. `output/` is
  gitignored for exactly this reason.

### Repeat runs

`manifest.json` records a hash of every input. Re-running skips anything
unchanged, so an interrupted run resumes cleanly and a re-run after editing one
transcript regenerates only that lecture. `--force` overrides.

### Tests

```bash
python3 tests_mdparse.py
```

Covers the Markdown parser and the diagram sanitiser. The emphasis cases matter
more than they look: a Python course is full of `**kwargs` and `x**2` in prose,
and a loose bold rule silently eats them.
