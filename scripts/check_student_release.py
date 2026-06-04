#!/usr/bin/env python3
"""Audit a GF5 student release tree for staff-only material."""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from pathlib import Path
from urllib.parse import urldefrag


FORBIDDEN_PATHS = (
    ".viewer_imports",
    "4DDress_samples",
    "UP2You",
    "assets/smpl",
    "libraries/motions/custom",
    "libraries/poses",
    "libraries/scenes",
    "docs/__pycache__",
    "docs/future_edition_notes.md",
    "docs/part3_notes.md",
    "docs/staff_runbook.md",
    "docs/staff_release_workflow.md",
    "docs/session_handoff.md",
    "exports",
    "human_character_demo",
    "nvdiffrast",
    "staff_tools",
    "viewer/__pycache__",
    "viewer/CONVENTIONS.md",
    "viewer/COORDINATES_AND_ENV.md",
    "viewer/reference_impl",
)

REQUIRED_PATHS = (
    "docs/final_report.md",
    "docs/part3.md",
    "slides/part3.md",
    "libraries/motions/preset",
    "viewer/hy_motion_import.py",
    "viewer/scene_web_server.py",
    "viewer/avatar_export_worker.py",
)

FORBIDDEN_GLOBS = (
    "**/.DS_Store",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pkl",
    "libraries/avatars/*.zip",
    "libraries/avatars/**/*.zip",
    "**/*.pickle",
    "docs/*.html",
)

FORBIDDEN_TEXT = (
    "answer key",
    "correct implementation",
    "future_edition_notes",
    "marking",
    "part3_notes",
    "reference_impl",
    "rubric",
    "session_handoff",
    "staff-facing",
)

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".svg",
    ".txt",
    ".yml",
    ".yaml",
}

LINK_SUFFIXES = {
    ".html",
    ".md",
}

IGNORED_TEXT_FILES = {
    "scripts/check_student_release.py",
    ".github/workflows/student-release-audit.yml",
}

GENERATED_SITE_LINK_SOURCES = {
    "slides/parts12.md",
    "slides/part3.md",
}


def normalize(path: Path) -> str:
    return path.as_posix().strip("/")


def is_forbidden_path(relative: str) -> str | None:
    for forbidden in FORBIDDEN_PATHS:
        if relative == forbidden or relative.startswith(f"{forbidden}/"):
            return forbidden
    for pattern in FORBIDDEN_GLOBS:
        if fnmatch.fnmatch(relative, pattern):
            return pattern
    return None


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def audit(root: Path, *, max_file_mb: int) -> list[str]:
    problems: list[str] = []
    max_bytes = max_file_mb * 1024 * 1024
    root = root.resolve()

    if not root.exists():
        return [f"release root does not exist: {root}"]

    for required in REQUIRED_PATHS:
        if not (root / required).exists():
            problems.append(f"missing required release path: {required}")

    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        relative = normalize(path.relative_to(root))
        forbidden = is_forbidden_path(relative)
        if forbidden:
            problems.append(f"forbidden path matched {forbidden!r}: {relative}")
            continue

        if path.is_file() and path.stat().st_size > max_bytes:
            size_mb = path.stat().st_size / (1024 * 1024)
            problems.append(f"oversized file ({size_mb:.1f} MB): {relative}")

        if not path.is_file() or relative in IGNORED_TEXT_FILES or not is_text_file(path):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"non-UTF-8 text-like file: {relative}")
            continue

        lowered = text.lower()
        for needle in FORBIDDEN_TEXT:
            if needle in lowered:
                problems.append(f"forbidden text {needle!r} in {relative}")

        if path.suffix.lower() in LINK_SUFFIXES and relative not in GENERATED_SITE_LINK_SOURCES:
            problems.extend(check_links(root, path, text))

    return problems


def check_links(root: Path, path: Path, text: str) -> list[str]:
    problems: list[str] = []
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
    links.extend(re.findall(r"""(?:href|src)=["']([^"']+)["']""", text))

    for link in links:
        if link.startswith(("#", "http:", "https:", "mailto:")):
            continue
        target, _fragment = urldefrag(link)
        if not target:
            continue
        relative = normalize(path.relative_to(root))
        if target.startswith("/") and relative == "viewer/scene_editor_web/index.html":
            candidate = (path.parent / target.lstrip("/")).resolve()
        else:
            candidate = (path.parent / target).resolve()
        if root not in candidate.parents and candidate != root:
            problems.append(f"link escapes release tree in {relative}: {link}")
        elif not candidate.exists():
            problems.append(f"missing link target in {relative}: {link}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Student release tree to audit.",
    )
    parser.add_argument(
        "--max-file-mb",
        type=int,
        default=20,
        help="Maximum allowed size for a single released file.",
    )
    args = parser.parse_args()

    problems = audit(
        Path(args.root),
        max_file_mb=args.max_file_mb,
    )
    if problems:
        print("Student release audit failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print("Student release audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
