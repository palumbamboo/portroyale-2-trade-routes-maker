"""Extract one version's section from CHANGELOG.md into a notes file.

Usage:
    python tools/extract_changelog.py <tag-or-version> <output-file>

The version may be given as a tag ("v0.6.3") or a bare version ("0.6.3");
a leading "v" is stripped. The matched section is everything from the
"## [version]" heading up to (but excluding) the next "## [" heading, with
the heading line itself removed (the GitHub Release already shows the tag).

Used by the release workflow so the published release body mirrors the
CHANGELOG; also handy locally:
    python tools/extract_changelog.py v0.6.2 /tmp/notes.md
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def extract(version: str) -> str | None:
    version = version.lstrip("v").strip()
    text = CHANGELOG.read_text(encoding="utf-8")
    pat = re.compile(
        r"^##\s*\[" + re.escape(version) + r"\].*?(?=^##\s*\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pat.search(text)
    if not m:
        return None
    section = m.group(0).strip()
    # Drop the "## [version] …" heading line itself.
    section = re.sub(
        r"^##\s*\[" + re.escape(version) + r"\][^\n]*\n+", "", section, count=1
    )
    return section.strip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: extract_changelog.py <tag-or-version> <output-file>", file=sys.stderr)
        return 2
    version, out = argv[1], Path(argv[2])
    body = extract(version)
    if body is None:
        # No matching section — fall back to a minimal placeholder so the
        # release still gets a sensible body instead of failing the build.
        body = f"Release {version.lstrip('v')}.\n"
        print(f"warning: no CHANGELOG section for {version!r}; using placeholder",
              file=sys.stderr)
    out.write_text(body, encoding="utf-8")
    print(f"wrote {len(body)} chars to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
