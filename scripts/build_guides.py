#!/usr/bin/env python3
"""Generate panel guide HTML fragments from the Markdown sources in docs/guides/.

Single Source of Truth: docs/guides/*.md + docs/images/**
Output:                 custom_components/eeg_energy_optimizer/frontend/guide/

Usage:
    python scripts/build_guides.py          # regenerate the frontend guide files
    python scripts/build_guides.py --check  # exit 1 if frontend files are out of sync

Requires: pip install markdown

Markdown conventions (see docs/README.md):
    # Title              -> <h2 class="guide-title"> (dialog heading)
    ##/###/####          -> shifted one level down (h3/h4/h5)
    > [!WARNING]         -> <div class="guide-alert warning">
    > [!NOTE]            -> <div class="guide-alert note">
    > [!CAUTION]         -> <div class="guide-alert caution">
    ![alt](../images/x)  -> src rewritten to /eeg_optimizer_panel/guide/x
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import markdown
except ImportError:  # pragma: no cover
    sys.exit("Fehler: 'markdown' nicht installiert. Bitte: pip install markdown")

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDES_DIR = REPO_ROOT / "docs" / "guides"
IMAGES_DIR = REPO_ROOT / "docs" / "images"
OUTPUT_DIR = (
    REPO_ROOT / "custom_components" / "eeg_energy_optimizer" / "frontend" / "guide"
)

# GitHub alert type -> CSS class on the panel side
ALERT_CLASSES = {
    "WARNING": "warning",
    "NOTE": "note",
    "CAUTION": "caution",
    "IMPORTANT": "caution",
    "TIP": "note",
}

GENERATED_HEADER = (
    "<!-- GENERATED FILE - DO NOT EDIT.\n"
    "     Quelle: docs/guides/{name}.md\n"
    "     Neu generieren mit: python scripts/build_guides.py -->\n"
)


def _render_alerts(md_text: str) -> str:
    """Replace GitHub-style alert blockquotes with raw HTML alert divs."""
    out_lines: list[str] = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        match = re.match(r">\s*\[!(\w+)\]\s*$", lines[i])
        if match and match.group(1).upper() in ALERT_CLASSES:
            css = ALERT_CLASSES[match.group(1).upper()]
            i += 1
            body: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                body.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            inner = markdown.markdown("\n".join(body), extensions=["tables"])
            out_lines.append(f'<div class="guide-alert {css}">{inner}</div>')
        else:
            out_lines.append(lines[i])
            i += 1
    return "\n".join(out_lines)


def _shift_headings(html: str) -> str:
    """h1 -> h2.guide-title, h2 -> h3, h3 -> h4, h4 -> h5 (deepest first)."""
    for level in (4, 3, 2):
        html = html.replace(f"<h{level}>", f"<h{level + 1}>")
        html = html.replace(f"</h{level}>", f"</h{level + 1}>")
    html = html.replace("<h1>", '<h2 class="guide-title">')
    html = html.replace("</h1>", "</h2>")
    return html


def render_guide(md_path: Path) -> str:
    text = md_path.read_text(encoding="utf-8")
    text = _render_alerts(text)
    html = markdown.markdown(text, extensions=["tables"])
    html = _shift_headings(html)
    html = html.replace('src="../images/', 'src="/eeg_optimizer_panel/guide/')
    return GENERATED_HEADER.format(name=md_path.stem) + html + "\n"


def build_expected() -> dict[Path, bytes]:
    """Map of OUTPUT_DIR-relative path -> expected file content."""
    expected: dict[Path, bytes] = {}
    for md_path in sorted(GUIDES_DIR.glob("*.md")):
        rendered = render_guide(md_path).replace("\r\n", "\n")
        expected[Path(f"{md_path.stem}.html")] = rendered.encode("utf-8")
    if IMAGES_DIR.is_dir():
        for img in sorted(IMAGES_DIR.rglob("*")):
            if img.is_file():
                expected[img.relative_to(IMAGES_DIR)] = img.read_bytes()
    return expected


def current_files() -> dict[Path, bytes]:
    actual: dict[Path, bytes] = {}
    if OUTPUT_DIR.is_dir():
        for f in sorted(OUTPUT_DIR.rglob("*")):
            if f.is_file() and f.suffix != ".pyc" and "__pycache__" not in f.parts:
                content = f.read_bytes()
                if f.suffix == ".html":
                    # Zeilenenden normalisieren — git autocrlf darf den
                    # Byte-Vergleich nicht brechen (CRLF-Checkout auf Windows)
                    content = content.replace(b"\r\n", b"\n")
                actual[f.relative_to(OUTPUT_DIR)] = content
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Nur prüfen, nichts schreiben. Exit 1 bei Abweichungen.",
    )
    args = parser.parse_args()

    expected = build_expected()
    actual = current_files()

    if args.check:
        problems: list[str] = []
        for rel in sorted(set(expected) | set(actual)):
            if rel not in actual:
                problems.append(f"FEHLT:     frontend/guide/{rel.as_posix()}")
            elif rel not in expected:
                problems.append(f"VERWAIST:  frontend/guide/{rel.as_posix()}")
            elif expected[rel] != actual[rel]:
                problems.append(f"VERALTET:  frontend/guide/{rel.as_posix()}")
        if problems:
            print("docs/ und frontend/guide/ sind nicht synchron:\n")
            print("\n".join(problems))
            print("\nBitte ausführen: python scripts/build_guides.py")
            return 1
        print(f"OK — {len(expected)} Dateien synchron.")
        return 0

    # Write/refresh expected files, remove orphans
    written = 0
    for rel, content in expected.items():
        target = OUTPUT_DIR / rel
        if actual.get(rel) == content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        written += 1
        print(f"geschrieben: {target.relative_to(REPO_ROOT).as_posix()}")
    for rel in set(actual) - set(expected):
        (OUTPUT_DIR / rel).unlink()
        print(f"entfernt:    frontend/guide/{rel.as_posix()} (verwaist)")
    print(f"Fertig — {written} Datei(en) aktualisiert, {len(expected)} gesamt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
