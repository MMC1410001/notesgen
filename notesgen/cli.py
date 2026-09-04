"""Command line entry point.

    python -m notesgen discover --course "<path>"
    python -m notesgen generate --course "<path>" --section 11
    python -m notesgen build    --course "<path>"
    python -m notesgen run      --course "<path>"
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

from . import build as build_mod
from . import diagrams as diagrams_mod
from . import engine
from . import export as export_mod
from . import gdocs
from . import generate as gen
from . import ingest
from . import setup_cmd
from .discover import STATUS_NO_TRANSCRIPT, course_name, discover, flatten
from .glossary import Glossary
from .manifest import Manifest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "output"
DEFAULT_INPUT = PROJECT_ROOT / "input"


def _select(sections, section_filter, only):
    if section_filter:
        wanted = {s.lstrip("0") for s in section_filter}
        sections = [s for s in sections if s.idx.lstrip("0") in wanted]
    if only:
        kept = []
        for s in sections:
            lectures = [l for l in s.lectures if fnmatch.fnmatch(l.slug, only)]
            if lectures:
                s.lectures = lectures
                kept.append(s)
        sections = kept
    return sections


def _paths(args):
    """Resolve the input (zip, folder or URL) into a course directory."""
    source = getattr(args, "input", None) or getattr(args, "course", None)
    if not source:
        raise SystemExit("--input is required (a .zip, a folder, or a Udemy course URL)")

    course_dir = ingest.resolve_input(
        source,
        Path(args.input_dir).expanduser().resolve(),
        cdp_port=getattr(args, "attach", None),
    )
    name = course_name(course_dir)
    root = Path(args.output).expanduser().resolve() / course_dir.name
    return course_dir, name, root, root / "md", root / "docx", root / "manifest.json"


def cmd_discover(args) -> int:
    course_dir, name, *_ = _paths(args)
    sections = _select(discover(course_dir), args.section, args.only)
    lectures = flatten(sections)
    missing = [l for l in lectures if l.status == STATUS_NO_TRANSCRIPT]

    print(f"\n{name}")
    print(f"{course_dir}\n")
    for s in sections:
        bad = sum(1 for l in s.lectures if l.status == STATUS_NO_TRANSCRIPT)
        flag = f"   <-- {bad} without transcript" if bad else ""
        print(f"  {s.idx}  {s.title[:52]:<52} {len(s.lectures):>3} lec  {s.words:>7,} words{flag}")

    print(f"\n  {len(sections)} sections, {len(lectures)} lectures, "
          f"{sum(l.words for l in lectures):,} words")
    if missing:
        print(f"\n  {len(missing)} lecture(s) without a usable transcript "
              f"(stubbed, never sent to the model):")
        for l in missing:
            print(f"    {l.slug}  ({l.words} words)")
    return 0


def cmd_generate(args) -> int:
    course_dir, name, root, md_root, _, manifest_path = _paths(args)
    sections = _select(discover(course_dir), args.section, args.only)
    if not sections:
        print("no lectures matched", file=sys.stderr)
        return 1

    root.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(manifest_path)
    glossary = Glossary.load(Path(args.glossary) if args.glossary else None)

    print(f"\nGenerating notes for {name}")
    stats = gen.generate_lectures(
        name, sections, md_root, manifest, glossary,
        model=args.model, workers=args.workers, force=args.force,
    )
    print(f"\n  lectures: {stats}")

    if not args.no_rollup:
        r = gen.generate_rollups(
            name, sections, md_root, manifest,
            model=args.model, workers=args.workers, force=args.force,
        )
        print(f"  rollups:  {r}")
        # A course index over a filtered subset would be misleading.
        if not (args.section or args.only):
            gen.generate_course_index(
                name, sections, md_root, manifest, model=args.model, force=args.force
            )

    print(f"\n  markdown in {md_root}")
    if stats.get("failed"):
        print(f"  {stats['failed']} failed - re-run the same command to retry only those")
        return 1
    return 0


def cmd_diagram(args) -> int:
    course_dir, name, root, md_root, _, manifest_path = _paths(args)
    if not md_root.exists():
        print(f"no generated notes at {md_root}; run `generate` first", file=sys.stderr)
        return 1
    sections = _select(discover(course_dir), args.section, args.only)
    manifest = Manifest(manifest_path)

    print(f"\nGenerating diagrams for {name}")
    if not diagrams_mod.renderer_available():
        print("  note: no mermaid renderer found. Diagrams will render live in")
        print("  the HTML, but .docx will show their source instead.")
        print("  Fix with: npm install -g @mermaid-js/mermaid-cli\n")

    stats = diagrams_mod.generate(
        name, sections, md_root, manifest,
        model=args.model, workers=args.workers, force=args.force,
    )
    print(f"\n  diagrams: {stats}")
    return 1 if stats.get("failed") else 0


def cmd_build(args) -> int:
    course_dir, name, root, md_root, docx_root, _ = _paths(args)
    if not md_root.exists():
        print(f"no generated notes at {md_root}; run `generate` first", file=sys.stderr)
        return 1
    sections = _select(discover(course_dir), args.section, args.only)
    written = build_mod.build(
        name, sections, md_root, docx_root,
        max_words=args.max_words,
        image_cache=None if args.no_images else root / "diagram-images",
    )
    print(f"\n  {len(written)} document(s) in {docx_root}")
    for p in written:
        print(f"    {p.name}")
    print(f"\n  Upload instructions: {docx_root / 'UPLOAD.md'}")
    return 0


def cmd_setup(args) -> int:
    print("\nOptional extras (the core pipeline needs none of these):\n")
    for name, ok in setup_cmd.status().items():
        print(f"  [{'x' if ok else ' '}] {name:<7} {setup_cmd.EXTRAS[name]['why']}")
    print()
    return setup_cmd.run(args.extra or None, dry_run=args.dry_run)


def cmd_fetch(args) -> int:
    """Download transcripts only, without generating notes."""
    course_dir = ingest.resolve_input(
        args.input or args.course,
        Path(args.input_dir).expanduser().resolve(),
        cdp_port=args.attach,
    )
    sections = discover(course_dir)
    lectures = flatten(sections)
    print(f"\n  {course_name(course_dir)}")
    print(f"  {len(sections)} sections, {len(lectures)} lectures -> {course_dir}")
    return 0


def cmd_export(args) -> int:
    course_dir, name, root, md_root, _, _ = _paths(args)
    if not md_root.exists():
        print(f"no generated notes at {md_root}; run `generate` first", file=sys.stderr)
        return 1
    sections = _select(discover(course_dir), args.section, args.only)
    formats = tuple(args.format) if args.format else export_mod.FORMATS

    written = export_mod.export(
        name, sections, md_root, root,
        formats=formats,
        max_words=args.max_words,
        whole_course=not args.no_whole_course,
    )
    print()
    for fmt, paths in written.items():
        print(f"  {len(paths):>3} {fmt:<5} -> {root / export_mod.SUBDIR[fmt]}")
    print(f"\n  These cost nothing to regenerate - only `generate` spends tokens.")
    return 0


def cmd_push(args) -> int:
    course_dir, name, root, md_root, docx_root, manifest_path = _paths(args)
    if not md_root.exists():
        print(f"no generated notes at {md_root}; run `generate` first", file=sys.stderr)
        return 1
    sections = _select(discover(course_dir), args.section, args.only)
    manifest = Manifest(manifest_path)
    config_dir = Path(args.config_dir).expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    image_cache = None if args.no_images else root / "diagram-images"

    try:
        if args.split_sections:
            print(f"\nPushing {len(sections)} section documents to Google Docs")
            urls = []
            for doc in build_mod.collect(name, sections, md_root, max_words=args.max_words):
                path = docx_root / (doc.basename + ".docx")
                if not path.exists():
                    path = build_mod.build_section_doc(
                        doc.title, doc.subtitle, doc.parts, path, image_cache
                    )
                url = gdocs.push(path, f"{name} - {doc.title}", config_dir, manifest,
                                 folder_name=name, key=f"__gdoc__/{doc.basename}")
                print(f"  {doc.basename}\n    {url}")
                urls.append(url)
            print(f"\n  {len(urls)} document(s) in your Drive folder '{name}'")
        else:
            print(f"\nBuilding one document for the whole course...")
            combined = root / "gdocs" / f"{name}.docx"
            combined.parent.mkdir(parents=True, exist_ok=True)
            build_mod.build_single(name, sections, md_root, combined, image_cache=image_cache)
            print(f"  {combined.stat().st_size // 1024} KB, uploading...")
            url = gdocs.push(combined, name, config_dir, manifest, folder_name=name)
            print(f"\n  {url}")
            print("  Navigate it with View > Show outline.")
    except gdocs.GDocsError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
    return 0


def cmd_run(args) -> int:
    rc = cmd_generate(args)
    if rc and not args.keep_going:
        return rc
    if not args.no_diagrams:
        rc = cmd_diagram(args) or rc
    if not args.no_docx:
        rc = cmd_build(args) or rc
    return cmd_export(args) or rc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="notesgen",
        description="Turn Udemy course transcripts into revision notes as .docx",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, *, generating=False, building=False, exporting=False):
        p.add_argument(
            "--input", "-i",
            help="a .zip from the Udemy Transcript Extractor, an extracted "
                 "folder, or a Udemy course URL",
        )
        p.add_argument("--course", help=argparse.SUPPRESS)  # old name, still works
        p.add_argument("--output", default=str(DEFAULT_OUTPUT))
        p.add_argument("--input-dir", default=str(DEFAULT_INPUT),
                       help="where zips are extracted and URL fetches are saved")
        p.add_argument(
            "--attach", type=int, metavar="PORT", nargs="?", const=9222,
            help="attach to a Chrome you started with --remote-debugging-port "
                 "(default 9222). Use this if Cloudflare keeps challenging.",
        )
        p.add_argument("--section", action="append", help="limit to section number(s), repeatable")
        p.add_argument("--only", help="glob over '<section-dir>/<lecture-file>'")
        if generating:
            p.add_argument(
                "--provider", choices=["claude-cli", "anthropic", "openai", "gemini"],
                help="default: claude CLI if installed, else whichever API key is set",
            )
            p.add_argument("--model", default="sonnet")
            p.add_argument("--workers", type=int, default=3)
            p.add_argument("--glossary", help="override glossary.yml")
            p.add_argument("--force", action="store_true", help="regenerate even if current")
            p.add_argument("--no-rollup", action="store_true")
        if building:
            p.add_argument("--max-words", type=int, default=build_mod.MAX_WORDS_PER_DOC)
            p.add_argument("--no-images", action="store_true",
                           help="skip rendering diagrams into .docx")
        if exporting:
            p.add_argument(
                "--format", action="append", choices=list(export_mod.FORMATS),
                help="repeatable; default is all three",
            )
            p.add_argument("--no-whole-course", action="store_true",
                           help="skip the single combined all-sections file")

    p = sub.add_parser("setup", help="install the optional extras (gdocs, udemy, api)")
    p.add_argument("--extra", action="append", choices=list(setup_cmd.EXTRAS),
                   help="install just one; default is all missing")
    p.add_argument("--dry-run", action="store_true", help="print the commands only")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("discover", help="list the course tree and flag missing transcripts")
    common(p)
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("generate", help="generate Markdown notes")
    common(p, generating=True)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser(
        "diagram", help="generate Mermaid diagrams per section from existing notes"
    )
    common(p, generating=True)
    p.set_defaults(func=cmd_diagram)

    p = sub.add_parser("build", help="assemble .docx from generated Markdown")
    common(p, building=True)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser(
        "fetch",
        help="download transcripts from a Udemy URL (or unpack a zip) and stop",
    )
    common(p)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("export", help="write notes as .html, .txt and .md (no model calls)")
    common(p, building=True, exporting=True)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("push", help="upload the notes to Google Docs")
    common(p, building=True)
    p.add_argument("--split-sections", action="store_true",
                   help="one Doc per section instead of one for the whole course")
    p.add_argument("--config-dir", default=str(PROJECT_ROOT / ".gdocs"),
                   help="where the OAuth client and cached token live")
    p.set_defaults(func=cmd_push)

    p = sub.add_parser("run", help="generate, then build and export every format")
    common(p, generating=True, building=True, exporting=True)
    p.add_argument("--keep-going", action="store_true", help="build even if some lectures failed")
    p.add_argument("--no-docx", action="store_true", help="skip the .docx step")
    p.add_argument("--no-diagrams", action="store_true", help="skip diagram generation")
    p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    engine.configure(
        provider=getattr(args, "provider", None),
        model=getattr(args, "model", None),
    )
    try:
        return args.func(args)
    except ingest.IngestError as exc:
        print(f"\ninput error: {exc}", file=sys.stderr)
        return 1
    except engine.EngineError as exc:
        print(f"\nprovider error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
