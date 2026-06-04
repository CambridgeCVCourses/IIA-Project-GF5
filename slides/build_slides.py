#!/usr/bin/env python3
"""Generate a browser presentation deck from a Markdown slide source.

Slides are separated by a line containing only `---`. Speaker notes for a slide
start after a line containing only `???`.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
DOCS_ROOT = PROJECT_ROOT / "docs"
sys.path.insert(0, str(DOCS_ROOT))

from build_site import (
    COPYRIGHT_OWNER,
    COPYRIGHT_OWNER_URL,
    MarkdownRenderer,
    SITE_TITLE,
    format_inline,
    indent,
    render_nav,
    rewrite_href,
    schedule_calendar_embed,
    slugify,
    strip_inline_markdown,
)


DEFAULT_SOURCE = ROOT / "parts12.md"
DEFAULT_OUTPUT = PROJECT_ROOT / "site" / "parts12-slides.html"
STYLE_ASSET = "deck.css"


@dataclass(frozen=True)
class Slide:
    index: int
    title: str
    body: str
    notes: str


class SlideMarkdownRenderer(MarkdownRenderer):
    """Markdown renderer with image-line support for presentation slides."""

    def __init__(self) -> None:
        super().__init__()
        self.table_rows: list[list[str]] = []

    def handle_line(self, line: str) -> None:
        if not self.in_code and is_table_row(line):
            self.close_paragraph()
            self.close_list()
            self.table_rows.append(parse_table_row(line))
            return

        self.close_table()

        if not self.in_code:
            raw_component = line.strip()
            if raw_component.startswith((
                '<figure class="media-embed',
                '<figure class="website-shot',
                '<article class="resource-card',
                '<section class="presentation-order-tool',
                '<section class="schedule-calendar',
            )):
                self.close_blocks()
                self.out.append(raw_component)
                return

            image = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", line.strip())
            if image:
                self.close_blocks()
                alt = html.escape(image.group(1), quote=True)
                src = html.escape(rewrite_href(image.group(2)), quote=True)
                self.out.append(
                    '<figure class="slide-figure">'
                    f'<img src="{src}" alt="{alt}">'
                    "</figure>"
                )
                return
        super().handle_line(line)

    def close_table(self) -> None:
        if not self.table_rows:
            return

        rows = self.table_rows
        self.table_rows = []
        if len(rows) < 2 or not is_table_separator(rows[1]):
            for row in rows:
                self.out.append(f"<p>{format_inline(' | '.join(row))}</p>")
            return

        headers = rows[0]
        body_rows = rows[2:]
        table_class = table_class_for(headers)
        should_clip_table = "assessment-table" in table_class.split()
        if should_clip_table:
            self.out.append('<div class="table-clip assessment-table-clip">')
        self.out.append(f'<table class="{table_class}">')
        self.out.append("  <thead>")
        self.out.append("    <tr>")
        for cell in headers:
            self.out.append(f"      <th>{format_inline(cell)}</th>")
        self.out.append("    </tr>")
        self.out.append("  </thead>")
        self.out.append("  <tbody>")
        for row in body_rows:
            padded = row + [""] * max(0, len(headers) - len(row))
            self.out.append("    <tr>")
            for cell in padded[: len(headers)]:
                self.out.append(f"      <td>{format_inline(cell)}</td>")
            self.out.append("    </tr>")
        self.out.append("  </tbody>")
        self.out.append("</table>")
        if should_clip_table:
            self.out.append("</div>")

    def close_list(self) -> None:
        if not self.list_type:
            return

        class_attr = ""
        if self.list_type == "ol" and len(self.list_items) >= 5:
            class_attr = ' class="plain-list"'

        if self.list_type == "ol" and self.list_start != 1:
            self.out.append(f'<ol start="{self.list_start}"{class_attr}>')
        else:
            self.out.append(f"<{self.list_type}{class_attr}>")
        for item in self.list_items:
            self.out.append(f"  <li>{format_inline(item)}</li>")
        self.out.append(f"</{self.list_type}>")
        self.list_type = None
        self.list_items = []
        self.list_start = 1

    def close_blocks(self) -> None:
        self.close_table()
        super().close_blocks()


def is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def parse_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(row: list[str]) -> bool:
    return bool(row) and all(re.match(r"^:?-{3,}:?$", cell.strip()) for cell in row)


def table_class_for(headers: list[str]) -> str:
    normalized = [strip_inline_markdown(header).strip().lower() for header in headers]
    classes = ["slide-table"]
    if normalized[:3] == ["week", "mode", "focus"]:
        classes.append("timeline-table")
    if "coursework" in normalized and "due date" in normalized:
        classes.append("assessment-table")
    if normalized[:3] == ["date", "time", "what"]:
        classes.append("key-dates-table")
    return " ".join(classes)


def split_directive_fields(text: str) -> list[str]:
    return [field.strip() for field in text.split("|")]


def youtube_video_id(source: str) -> str:
    source = source.strip()
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{6,})", source)
    return match.group(1) if match else source


def youtube_time_seconds(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)

    total = 0
    for match in re.finditer(r"(\d+)([hms])", value):
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "h":
            total += amount * 3600
        elif unit == "m":
            total += amount * 60
        else:
            total += amount
    return total if total else None


def youtube_start_seconds(source: str) -> int | None:
    match = re.search(r"[?&#](?:t|start)=([0-9hms]+)", source.strip())
    if not match:
        return None
    return youtube_time_seconds(match.group(1))


def youtube_watch_url(source: str) -> str:
    video_id = youtube_video_id(source)
    if start_seconds := youtube_start_seconds(source):
        return f"https://youtu.be/{video_id}?t={start_seconds}"
    return f"https://youtu.be/{video_id}"


def youtube_embed(markdown: str) -> str:
    fields = split_directive_fields(markdown)
    if not fields or not fields[0]:
        raise SystemExit("YouTube slide directive is missing a video id")

    video_id = html.escape(youtube_video_id(fields[0]), quote=True)
    query_parts = ["rel=0"]
    if (start_seconds := youtube_start_seconds(fields[0])) is not None:
        query_parts.append(f"start={start_seconds}")
    query = "&".join(query_parts)
    title = fields[1] if len(fields) > 1 and fields[1] else "YouTube video"
    caption = fields[2] if len(fields) > 2 else ""
    title_attr = html.escape(strip_inline_markdown(title), quote=True)
    fallback_href = html.escape(youtube_watch_url(fields[0]), quote=True)
    caption_parts = [format_inline(caption)] if caption else []
    caption_parts.append(
        f'<a href="{fallback_href}" target="_blank" rel="noreferrer">Open on YouTube</a>'
    )
    caption_html = f"<figcaption>{' '.join(caption_parts)}</figcaption>"
    return (
        '<figure class="media-embed youtube-embed">'
        '<div class="media-frame">'
        f'    <iframe src="https://www.youtube-nocookie.com/embed/{video_id}?{query}" '
        f'title="{title_attr}" loading="lazy" allowfullscreen '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
        'picture-in-picture; web-share"></iframe>'
        "</div>"
        f"{caption_html}"
        "</figure>"
    )


def website_card(markdown: str) -> str:
    fields = split_directive_fields(markdown)
    if not fields or not fields[0]:
        raise SystemExit("Website card directive is missing a URL")

    href = html.escape(fields[0], quote=True)
    title = fields[1] if len(fields) > 1 and fields[1] else fields[0]
    caption = fields[2] if len(fields) > 2 else ""
    return (
        '<article class="resource-card">'
        f'<a href="{href}" target="_blank" rel="noreferrer">'
        '<span class="resource-kicker">Open website</span>'
        f"<strong>{format_inline(title)}</strong>"
        f"<span>{format_inline(caption)}</span>"
        "</a>"
        "</article>"
    )


def website_screenshot(markdown: str) -> str:
    fields = split_directive_fields(markdown)
    if len(fields) < 3:
        raise SystemExit("Website screenshot directive expects image, URL, and title")

    image_src = html.escape(rewrite_href(fields[0]), quote=True)
    href = html.escape(fields[1], quote=True)
    title = fields[2]
    caption = fields[3] if len(fields) > 3 else ""
    title_text = html.escape(strip_inline_markdown(title), quote=True)
    caption_html = f"<figcaption>{format_inline(caption)}</figcaption>" if caption else ""
    return (
        '<figure class="website-shot">'
        f'<a href="{href}" target="_blank" rel="noreferrer">'
        f'<img src="{image_src}" alt="{title_text} website screenshot">'
        "</a>"
        f"{caption_html}"
        "</figure>"
    )


def local_video_embed(markdown: str) -> str:
    fields = split_directive_fields(markdown)
    if not fields or not fields[0]:
        raise SystemExit("Video slide directive is missing a source path")

    source = fields[0]
    caption = fields[1] if len(fields) > 1 else ""
    options = {field.lower() for field in fields[2:]}
    src = html.escape(rewrite_href(source), quote=True)
    source_type = "video/mp4" if source.lower().split("?", 1)[0].endswith(".mp4") else ""
    type_attr = f' type="{source_type}"' if source_type else ""
    autoplay_attr = " autoplay muted" if "autoplay" in options else ""
    loop_attr = " loop" if "loop" in options else ""
    caption_html = f"<figcaption>{format_inline(caption)}</figcaption>" if caption else ""
    fallback = f'<a href="{src}">Open video</a>'
    return (
        '<figure class="media-embed local-video-embed">'
        '<div class="media-frame">'
        f'<video controls preload="metadata" playsinline{autoplay_attr}{loop_attr}>'
        f'<source src="{src}"{type_attr}>'
        f"{fallback}"
        "</video>"
        "</div>"
        f"{caption_html}"
        "</figure>"
    )


def fragment_to_anchor(fragment: str) -> str:
    fragment = fragment.strip().lstrip("#")
    if re.match(r"^[a-z0-9-]+$", fragment):
        return fragment
    return slugify(fragment, {})


def markdown_section(target: str, base_dir: Path) -> str:
    path_text, _, fragment = target.partition("#")
    path = (base_dir / path_text.strip()).resolve()
    if not path.is_relative_to(PROJECT_ROOT):
        raise SystemExit(f"Slide include points outside the project: {target}")
    if not path.exists():
        raise SystemExit(f"Slide include source not found: {path}")

    text = path.read_text(encoding="utf-8")
    if not fragment:
        return text.strip()

    anchor = fragment_to_anchor(fragment)
    used: dict[str, int] = {}
    section_lines: list[str] = []
    section_level: int | None = None
    in_section = False

    for line in text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            ident = slugify(heading.group(2), used)
            if in_section and section_level is not None and level <= section_level:
                break
            if ident == anchor:
                in_section = True
                section_level = level
                continue
        if in_section:
            section_lines.append(line)

    if not in_section:
        raise SystemExit(f"Heading not found for slide include: {target}")
    return "\n".join(section_lines).strip()


def bullet_lines(markdown: str) -> str:
    lines: list[str] = []
    in_bullet = False
    for line in markdown.splitlines():
        if re.match(r"^\s*[-*]\s+", line):
            lines.append(line)
            in_bullet = True
        elif in_bullet and line.startswith(("  ", "\t")) and line.strip():
            lines.append(line)
        else:
            in_bullet = False
    return "\n".join(lines)


def list_items(markdown: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines():
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet:
            if current:
                items.append(" ".join(current))
            current = [bullet.group(1).strip()]
            continue
        if current and line.startswith(("  ", "\t")) and line.strip():
            current.append(line.strip())
            continue
        if current and not line.strip():
            continue
        if current:
            items.append(" ".join(current))
            current = []
    if current:
        items.append(" ".join(current))
    return items


def first_paragraph(markdown: str) -> str:
    paragraph: list[str] = []
    for line in markdown.splitlines():
        if not line.strip():
            if paragraph:
                break
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", line) or line.startswith("```"):
            if paragraph:
                break
            continue
        paragraph.append(line)
    return "\n".join(paragraph)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def clean(cell: str) -> str:
        return cell.replace("|", "/").strip()

    table = [
        "| " + " | ".join(clean(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = row + [""] * max(0, len(headers) - len(row))
        table.append("| " + " | ".join(clean(cell) for cell in padded[: len(headers)]) + " |")
    return "\n".join(table)


def existing_table(markdown: str) -> str:
    lines: list[str] = []
    in_table = False
    for line in markdown.splitlines():
        if is_table_row(line):
            lines.append(line)
            in_table = True
            continue
        if in_table:
            break
    return "\n".join(lines)


def timeline_table(markdown: str) -> str:
    if table := existing_table(markdown):
        return table

    rows: list[list[str]] = []
    for item in list_items(markdown):
        match = re.match(r"Week\s+(\d+):\s*(.+)$", item, re.IGNORECASE)
        if not match:
            continue
        week = int(match.group(1))
        mode = "Individual" if week <= 2 else "Pairs"
        focus = match.group(2).strip().rstrip(".")
        focus = focus[:1].upper() + focus[1:] if focus else focus
        rows.append([f"Week {week}", mode, focus])
    return markdown_table(["Week", "Mode", "Focus"], rows) if rows else bullet_lines(markdown)


def assessment_table(markdown: str) -> str:
    if table := existing_table(markdown):
        return table

    rows: list[list[str]] = []
    for item in list_items(markdown):
        course, separator, rest = item.partition(":")
        if not separator:
            continue
        due_match = re.search(r"\bdue\s+(.+?),\s+worth\b", rest)
        marks_match = re.search(r"\bworth\s+(\d+)\s+marks\b", rest)
        if not due_match or not marks_match:
            continue

        due = due_match.group(1).replace("Friday", "Fri").replace(" at ", ", ")
        mode = ""
        if re.search(r"\bsplit\s+50%\s+individual\s+and\s+50%\s+group\b", rest):
            mode = "50% individual / 50% group"
        elif re.search(r"\bindividual\b", rest):
            mode = "Individual"
        elif re.search(r"\bgroup\b", rest):
            mode = "Group"
        rows.append([course.strip(), due, marks_match.group(1), mode])
    return markdown_table(["Coursework", "Due date", "Marks", "Mode"], rows) if rows else bullet_lines(markdown)


def presentation_order_embed(markdown: str) -> str:
    fields = [field for field in split_directive_fields(markdown) if field]
    if fields and fields[0] in {"assignments", "compact"}:
        fields = fields[1:]
    names = fields or [f"Group {index}" for index in range(1, 10)]
    if len(names) == 1:
        try:
            count = max(1, int(names[0]))
        except ValueError:
            pass
        else:
            names = [f"Group {index}" for index in range(1, count + 1)]

    rendered_items = "".join(
        "<li>"
        f"<span>{html.escape(name)}</span>"
        '<input type="text" inputmode="numeric" placeholder="No." '
        'aria-label="Group order" data-order-assignment>'
        "</li>"
        for name in names
    )
    return (
        '<section class="presentation-order-tool is-assignments" '
        f'data-presentation-order data-order-mode="assignments" data-default-count="{len(names)}" '
        'aria-label="Presentation order randomizer">'
        '<div class="presentation-order-header">'
        "<strong>Presentation order</strong>"
        '<button class="button primary" type="button" data-order-shuffle>Shuffle</button>'
        "</div>"
        f"<ol data-order-result>{rendered_items}</ol>"
        "</section>"
    )


def expand_directives(markdown: str, base_dir: Path) -> str:
    directive = re.compile(
        r"^\s*\{\{([a-z-]+):\s*([^}]+?)\s*\}\}\s*$"
    )
    expanded: list[str] = []
    for line in markdown.splitlines():
        match = directive.match(line)
        if not match:
            expanded.append(line)
            continue

        mode, payload = match.groups()
        if mode == "youtube":
            expanded.extend(youtube_embed(payload).splitlines())
            continue
        if mode in {"website-card", "link-card"}:
            expanded.extend(website_card(payload).splitlines())
            continue
        if mode in {"website-shot", "website-screenshot"}:
            expanded.extend(website_screenshot(payload).splitlines())
            continue

        if mode == "schedule-calendar":
            expanded.extend(schedule_calendar_embed(payload).splitlines())
            continue
        if mode == "presentation-order":
            expanded.append(presentation_order_embed(payload).replace("\n", ""))
            continue
        if mode == "video":
            expanded.extend(local_video_embed(payload).splitlines())
            continue

        if mode not in {"include", "bullets", "first-paragraph", "timeline", "assessment-table"}:
            raise SystemExit(f"Unknown slide directive: {mode}")

        section = markdown_section(payload, base_dir)
        if mode == "bullets":
            replacement = bullet_lines(section)
        elif mode == "first-paragraph":
            replacement = first_paragraph(section)
        elif mode == "timeline":
            replacement = timeline_table(section)
        elif mode == "assessment-table":
            replacement = assessment_table(section)
        else:
            replacement = section
        expanded.extend(replacement.splitlines())
    return "\n".join(expanded)


def split_slides(markdown: str) -> list[str]:
    slides: list[list[str]] = [[]]
    for line in markdown.splitlines():
        if line.strip() == "---":
            if any(part.strip() for part in slides[-1]):
                slides.append([])
            continue
        slides[-1].append(line)
    return ["\n".join(slide).strip() for slide in slides if any(line.strip() for line in slide)]


def split_notes(markdown: str) -> tuple[str, str]:
    body: list[str] = []
    notes: list[str] = []
    target = body
    for line in markdown.splitlines():
        if line.strip() == "???":
            target = notes
            continue
        target.append(line)
    return "\n".join(body).strip(), "\n".join(notes).strip()


def first_heading(markdown: str) -> tuple[int, str] | None:
    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            return len(heading.group(1)), heading.group(2)
    return None


def render_markdown(markdown: str) -> str:
    rendered = SlideMarkdownRenderer().render(markdown)
    body = rendered.body
    heading = first_heading(markdown)
    if heading and heading[0] == 1:
        body = f"<h1>{format_inline(heading[1])}</h1>\n{body}"
    return body


def render_slide(raw_slide: str, index: int, base_dir: Path) -> Slide:
    body_markdown, notes_markdown = split_notes(raw_slide)
    body_markdown = expand_directives(body_markdown, base_dir)
    notes_markdown = expand_directives(notes_markdown, base_dir)
    heading = first_heading(body_markdown)
    title = strip_inline_markdown(heading[1]) if heading else f"Slide {index}"
    body = render_markdown(body_markdown)
    notes = render_markdown(notes_markdown) if notes_markdown else ""
    return Slide(index=index, title=title, body=body, notes=notes)


def render_slides(slides: list[Slide]) -> str:
    rendered: list[str] = []
    total = len(slides)
    for slide in slides:
        classes = ["slide"]
        if slide.index == 1:
            classes.append("is-active")
        if "media-embed" in slide.body:
            classes.append("has-media")
        if "website-shot" in slide.body:
            classes.append("has-website-shot")
        if "resource-card" in slide.body:
            classes.append("has-resource-cards")
        if "schedule-calendar" in slide.body:
            classes.append("has-calendar")
        hidden = "false" if slide.index == 1 else "true"
        rendered.append(
            f"""        <article class="{' '.join(classes)}" data-slide="{slide.index}" data-title="{html.escape(slide.title, quote=True)}" aria-hidden="{hidden}" aria-label="Slide {slide.index} of {total}: {html.escape(slide.title, quote=True)}">
          <div class="slide-stage">
            <div class="slide-canvas">
              <div class="slide-content">
                <div class="slide-fit">
{indent(slide.body, 14)}
                </div>
                <div class="slide-number" aria-hidden="true">{slide.index} / {total}</div>
              </div>
            </div>
          </div>
          <aside class="slide-notes">
{indent(slide.notes, 12) if slide.notes else "            <p>No speaker notes for this slide.</p>"}
          </aside>
        </article>"""
        )
    return "\n".join(rendered)


def render_section_nav(slides: list[Slide]) -> str:
    preferred_markers = [
        ("Intro", "Parts 1&2: Bring A Character To Life"),
        ("Logistics", "Four-Week Timeline"),
        ("Week 1", "Week 1: Forward Kinematics"),
        ("Week 2", "Week 2: Skinning And SMPL"),
        ("Reports", "Reports"),
        ("Beyond", "Part 3"),
        ("Intro", "Part 3: Group Character Animation Project"),
        ("Editor", "Scene Motion Editor"),
        ("Avatars", "Custom Avatars"),
        ("Motion", "Text-to-Motion Generation"),
        ("Report & Showcase", "Interim Report Feedback"),
        ("Policy", "AI Use Policy"),
    ]
    by_title = {slide.title: slide.index for slide in slides}
    markers: list[tuple[str, int]] = []
    seen: set[int] = set()
    for label, title in preferred_markers:
        index = by_title.get(title)
        if index is not None and index not in seen:
            markers.append((label, index))
            seen.add(index)

    if not markers:
        return ""

    rendered: list[str] = ['      <div class="deck-sections" aria-label="Slide sections">']
    for marker_index, (label, slide_index) in enumerate(markers):
        next_index = markers[marker_index + 1][1] if marker_index + 1 < len(markers) else len(slides) + 1
        span = max(1, next_index - slide_index)
        rendered.append(
            f'        <button type="button" data-section-target="{slide_index}" '
            f'style="--section-span: {span}" '
            f'aria-label="Jump to {html.escape(label, quote=True)} section">'
            f'<span class="section-label">{html.escape(label)}</span></button>'
        )
    rendered.append("      </div>")
    return "\n".join(rendered)


def render_html(source: Path, slides: list[Slide], output_dir: Path, output_name: str) -> str:
    title = slides[0].title if slides else "Parts 1&2 Session"
    html_title = SITE_TITLE if title == SITE_TITLE else f"{title} | {SITE_TITLE}"
    source_relative = Path(os.path.relpath(source, output_dir)).as_posix()
    return f"""<!doctype html>
<!-- Generated from {html.escape(source.name)} by slides/build_slides.py. Do not edit by hand. -->
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(html_title)}</title>
    <link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
    <link rel="stylesheet" href="assets/site.css">
    <link rel="stylesheet" href="assets/{STYLE_ASSET}">
    <script src="assets/site.js" defer></script>
  </head>
  <body class="deck-page" data-deck="{html.escape(source.stem, quote=True)}">
    <a class="skip-link" href="#deck">Skip to slides</a>
    <header class="site-header">
      <div class="nav-shell">
        <a class="brand" href="index.html" aria-label="GF5 home">
          <span class="brand-mark">GF5</span>
          <span>{html.escape(SITE_TITLE)}</span>
        </a>
        <nav class="nav-links" aria-label="Main navigation">
{render_nav(None, slides_active=True, current_slide_output=output_name)}
        </nav>
      </div>
    </header>
    <header class="deck-header" aria-label="Presentation controls">
      <div class="deck-toolbar" aria-label="Presentation controls">
        <div class="deck-control-cluster" aria-label="Slide movement">
          <button class="icon-button" type="button" data-action="first" aria-label="Return to first slide" title="First slide"><svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M5 19V5"></path><path d="m19 18-6-6 6-6"></path><path d="m13 18-6-6 6-6"></path></svg></button>
          <button class="icon-button" type="button" data-action="prev" aria-label="Previous slide" title="Previous slide"><svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"></path></svg></button>
          <button class="icon-button" type="button" data-action="next" aria-label="Next slide" title="Next slide"><svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"></path></svg></button>
        </div>
        <label class="deck-scrubber-wrap">
          <span class="deck-counter" aria-live="polite"><span class="deck-counter-label">Slide</span> <span data-current>1</span><span class="deck-counter-divider">/</span>{len(slides)}</span>
          <input class="deck-scrubber" type="range" min="1" max="{len(slides)}" value="1" step="1" data-slide-scrubber aria-label="Slide navigator">
        </label>
        <div class="deck-control-cluster deck-mode-controls" aria-label="Deck tools">
          <button class="tool-button" type="button" data-action="notes" aria-pressed="false" aria-label="Toggle student notes"><svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M6 4h9l3 3v13H6z"></path><path d="M14 4v4h4"></path><path d="M9 12h6"></path><path d="M9 16h4"></path></svg><span>Notes</span></button>
          <button class="tool-button" type="button" data-action="fullscreen" aria-label="Enter fullscreen"><svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M8 3H3v5"></path><path d="M16 3h5v5"></path><path d="M8 21H3v-5"></path><path d="M16 21h5v-5"></path></svg><span data-fullscreen-label>Full</span></button>
          <button class="tool-button" type="button" data-action="print" aria-label="Print slides"><svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M7 8V3h10v5"></path><path d="M6 17H4a2 2 0 0 1-2-2v-5h20v5a2 2 0 0 1-2 2h-2"></path><path d="M7 14h10v7H7z"></path></svg><span>Print</span></button>
        </div>
      </div>
{render_section_nav(slides)}
    </header>

    <main id="deck" class="deck" data-slide-count="{len(slides)}">
      <section class="slides" aria-live="polite">
{render_slides(slides)}
      </section>
      <aside class="notes-panel" data-notes-panel hidden aria-label="Student notes">
        <div class="notes-panel-header">
          <strong data-notes-title>Slide 1 notes</strong>
          <button type="button" data-action="download-notes">Download</button>
        </div>
        <textarea data-student-notes spellcheck="true" placeholder="Type your notes for this slide."></textarea>
        <p class="notes-status" data-notes-save-state aria-live="polite">Checking save location...</p>
      </aside>
    </main>

    <footer class="footer">
      <div class="footer-inner">
        <p>
          Copyright &copy; 2026
          <a href="{html.escape(COPYRIGHT_OWNER_URL, quote=True)}">{html.escape(COPYRIGHT_OWNER)}</a>.
          Released under the <a href="LICENSE">MIT License</a>.
        </p>
        <p>
          Generated from slide source:
          <a href="{html.escape(source_relative, quote=True)}">{html.escape(source.name)}</a>.
        </p>
      </div>
    </footer>

    <script>
      (() => {{
        const slides = Array.from(document.querySelectorAll(".slide"));
        const currentLabel = document.querySelector("[data-current]");
        const scrubber = document.querySelector("[data-slide-scrubber]");
        const sectionButtons = Array.from(document.querySelectorAll("[data-section-target]"));
        const notesPanel = document.querySelector("[data-notes-panel]");
        const notesTitle = document.querySelector("[data-notes-title]");
        const notesSaveState = document.querySelector("[data-notes-save-state]");
        const studentNotes = document.querySelector("[data-student-notes]");
        const notesButton = document.querySelector('[data-action="notes"]');
        const fullscreenButton = document.querySelector('[data-action="fullscreen"]');
        const fullscreenLabel = document.querySelector("[data-fullscreen-label]");
        const printButton = document.querySelector('[data-action="print"]');
        const downloadNotesButton = document.querySelector('[data-action="download-notes"]');
        const root = document.body;
        const deck = document.querySelector(".deck");
        const slidesRegion = document.querySelector(".slides");
        const deckId = document.body.dataset.deck || "parts12";
        const notesApiUrl = `api/slide-notes/${{encodeURIComponent(deckId)}}`;
        const noteCache = new Map();
        let current = 0;
        let showNotes = false;
        let projectNotesAvailable = false;
        let projectNotesPath = "";
        let saveTimer = null;

        function clamp(index) {{
          return Math.max(0, Math.min(slides.length - 1, index));
        }}

        function slideFromHash() {{
          const match = window.location.hash.match(/^#slide-(\\d+)$/);
          return match ? clamp(Number(match[1]) - 1) : 0;
        }}

        function updateNotes() {{
          if (!showNotes) {{
            notesPanel.hidden = true;
            document.body.classList.remove("has-student-notes");
            refreshSlideLayout();
            return;
          }}
          document.body.classList.add("has-student-notes");
          notesPanel.hidden = false;
          loadStudentNotes();
          refreshSlideLayout();
        }}

        function slideNoteId(index = current) {{
          return String(index + 1);
        }}

        function noteKey(index = current) {{
          return `gf5-slides-notes-v1-${{deckId}}-slide-${{index + 1}}`;
        }}

        function cacheBrowserNotes() {{
          slides.forEach((slide, index) => {{
            const cached = readBrowserNote(index);
            if (cached) {{
              noteCache.set(slideNoteId(index), cached);
            }}
          }});
        }}

        function readBrowserNote(index = current) {{
          try {{
            return localStorage.getItem(noteKey(index)) || "";
          }} catch (error) {{
            return "";
          }}
        }}

        function writeBrowserNote(index = current, note = readStudentNote(index)) {{
          try {{
            localStorage.setItem(noteKey(index), note);
          }} catch (error) {{
            // Browser storage is a backup only when the local notes server is running.
          }}
        }}

        function readStudentNote(index = current) {{
          return noteCache.get(slideNoteId(index)) || "";
        }}

        function collectStudentNotes() {{
          const notes = {{}};
          slides.forEach((slide, index) => {{
            const note = readStudentNote(index);
            if (note) {{
              notes[slideNoteId(index)] = note;
            }}
          }});
          return notes;
        }}

        function collectSlideTitles() {{
          const titles = {{}};
          slides.forEach((slide, index) => {{
            titles[slideNoteId(index)] = slide.dataset.title || `Slide ${{index + 1}}`;
          }});
          return titles;
        }}

        function updateNotesSaveState(blank = false) {{
          if (blank) {{
            notesSaveState.textContent = projectNotesAvailable
              ? "Blank; saves to project folder"
              : "Blank; browser fallback";
            return;
          }}
          notesSaveState.textContent = projectNotesAvailable
            ? "Saved to project folder"
            : "Saved in this browser";
        }}

        function writeStudentNote() {{
          noteCache.set(slideNoteId(), studentNotes.value);
          writeBrowserNote();
          if (projectNotesAvailable) {{
            notesSaveState.textContent = "Saving to project folder...";
            scheduleProjectNotesSave();
          }} else {{
            updateNotesSaveState(!studentNotes.value.trim());
          }}
        }}

        function loadStudentNotes() {{
          const title = slides[current].dataset.title || `Slide ${{current + 1}}`;
          notesTitle.textContent = `Slide ${{current + 1}}: ${{title}}`;
          studentNotes.value = readStudentNote();
          updateNotesSaveState(!studentNotes.value.trim());
        }}

        async function loadProjectNotes() {{
          cacheBrowserNotes();
          try {{
            const response = await fetch(notesApiUrl, {{
              headers: {{ Accept: "application/json" }},
              cache: "no-store",
            }});
            if (!response.ok) {{
              throw new Error(`Notes API returned ${{response.status}}`);
            }}
            const payload = await response.json();
            projectNotesAvailable = true;
            projectNotesPath = payload.path || "";
            const projectNotes = payload.notes || {{}};
            let mergedBrowserNotes = false;
            slides.forEach((slide, index) => {{
              const id = slideNoteId(index);
              const projectNote = typeof projectNotes[id] === "string" ? projectNotes[id] : "";
              const browserNote = readStudentNote(index);
              noteCache.set(id, projectNote || browserNote);
              if (!projectNote && browserNote) {{
                mergedBrowserNotes = true;
              }}
            }});
            if (mergedBrowserNotes) {{
              scheduleProjectNotesSave(0);
            }}
          }} catch (error) {{
            projectNotesAvailable = false;
            projectNotesPath = "";
          }}
          if (showNotes) {{
            loadStudentNotes();
          }}
        }}

        function scheduleProjectNotesSave(delay = 450) {{
          if (!projectNotesAvailable) {{
            return;
          }}
          if (saveTimer) {{
            clearTimeout(saveTimer);
          }}
          saveTimer = setTimeout(saveProjectNotes, delay);
        }}

        async function saveProjectNotes() {{
          saveTimer = null;
          try {{
            const response = await fetch(notesApiUrl, {{
              method: "POST",
              headers: {{ "Content-Type": "application/json" }},
              body: JSON.stringify({{
                notes: collectStudentNotes(),
                titles: collectSlideTitles(),
              }}),
            }});
            if (!response.ok) {{
              throw new Error(`Notes API returned ${{response.status}}`);
            }}
            const payload = await response.json();
            projectNotesAvailable = true;
            projectNotesPath = payload.path || projectNotesPath;
            updateNotesSaveState(!studentNotes.value.trim());
          }} catch (error) {{
            projectNotesAvailable = false;
            updateNotesSaveState(!studentNotes.value.trim());
          }}
        }}

        function downloadStudentNotes() {{
          const lines = [document.title.replace(" | ", " - "), ""];
          slides.forEach((slide, index) => {{
            const note = readStudentNote(index).trim();
            if (!note) {{
              return;
            }}
            const title = slide.dataset.title || `Slide ${{index + 1}}`;
            lines.push(`Slide ${{index + 1}}: ${{title}}`, "", note, "");
          }});
          if (lines.length === 2) {{
            lines.push("No notes yet.");
          }}
          const blob = new Blob([lines.join("\\n")], {{ type: "text/plain" }});
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `gf5-${{deckId}}-notes.txt`;
          document.body.append(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 0);
        }}

        function showSlide(index, updateHash = true) {{
          current = clamp(index);
          slides.forEach((slide, slideIndex) => {{
            const active = slideIndex === current;
            slide.classList.toggle("is-active", active);
            slide.setAttribute("aria-hidden", active ? "false" : "true");
          }});
          currentLabel.textContent = String(current + 1);
          scrubber.value = String(current + 1);
          const progressPercent = slides.length <= 1 ? 100 : (current / (slides.length - 1)) * 100;
          scrubber.style.setProperty("--scrubber-progress", `${{progressPercent}}%`);
          scrubber.setAttribute(
            "aria-valuetext",
            `Slide ${{current + 1}} of ${{slides.length}}: ${{slides[current].dataset.title || ""}}`,
          );
          updateSectionNav();
          updateNotes();
          refreshSlideLayout();
          if (updateHash) {{
            history.replaceState(null, "", `#slide-${{current + 1}}`);
          }}
        }}

        function updateSectionNav() {{
          sectionButtons.forEach((button, index) => {{
            const start = clamp(Number(button.dataset.sectionTarget || "1") - 1);
            const nextButton = sectionButtons[index + 1];
            const end = nextButton ? clamp(Number(nextButton.dataset.sectionTarget || slides.length + 1) - 1) : slides.length;
            const active = current >= start && current < end;
            button.classList.toggle("is-active", active);
            if (active) {{
              button.setAttribute("aria-current", "true");
            }} else {{
              button.removeAttribute("aria-current");
            }}
          }});
        }}

        function nextSlide() {{
          if (current >= slides.length - 1) {{
            return;
          }}
          showSlide(current + 1);
        }}

        function updateFullscreenState() {{
          const active = Boolean(document.fullscreenElement);
          document.body.classList.toggle("is-fullscreen", active);
          fullscreenLabel.textContent = active ? "Exit" : "Full";
          fullscreenButton.setAttribute("aria-label", active ? "Exit fullscreen" : "Enter fullscreen");
          updateResponsiveStageSize();
          updateFullscreenScale();
          requestAnimationFrame(() => {{
            updateResponsiveStageSize();
            fitActiveSlide();
            updateFullscreenScale();
          }});
          if (active && document.activeElement && typeof document.activeElement.blur === "function") {{
            document.activeElement.blur();
          }}
        }}

        function updateFullscreenScale() {{
          if (!document.fullscreenElement) {{
            root.style.setProperty("--deck-fullscreen-scale", "1");
            return;
          }}
          const styles = getComputedStyle(root);
          const designWidth = parseFloat(styles.getPropertyValue("--slide-stage-width")) || 960;
          const designHeight = parseFloat(styles.getPropertyValue("--slide-stage-height")) || 540;
          const scale = Math.max(0.1, Math.min(window.innerWidth / designWidth, window.innerHeight / designHeight));
          root.style.setProperty("--deck-fullscreen-scale", scale.toFixed(3));
        }}

        function updateResponsiveStageSize() {{
          if (document.fullscreenElement || root.classList.contains("is-printing")) {{
            root.style.removeProperty("--deck-slide-width");
            root.style.removeProperty("--deck-stage-scale");
            return;
          }}
          if (!deck || !slidesRegion) {{
            return;
          }}
          const styles = getComputedStyle(root);
          const designWidth = parseFloat(styles.getPropertyValue("--slide-stage-width")) || 960;
          const designHeight = parseFloat(styles.getPropertyValue("--slide-stage-height")) || 540;
          const aspect = designWidth / designHeight;
          const slidesRect = slidesRegion.getBoundingClientRect();
          const availableWidth = Math.max(0, slidesRect.width);
          const availableHeight = Math.max(0, slidesRect.height);
          if (!availableWidth) {{
            return;
          }}
          const narrowScreen = window.matchMedia("(max-width: 760px)").matches;
          const heightLimitedWidth = availableHeight ? availableHeight * aspect : designWidth;
          const width = narrowScreen
            ? Math.min(designWidth, availableWidth)
            : Math.min(designWidth, availableWidth, heightLimitedWidth);
          const stageWidth = Math.max(1, width);
          root.style.setProperty("--deck-slide-width", `${{stageWidth.toFixed(1)}}px`);
          root.style.setProperty("--deck-stage-scale", `${{(stageWidth / designWidth).toFixed(4)}}`);
        }}

        function nextFrame() {{
          return new Promise((resolve) => requestAnimationFrame(() => resolve()));
        }}

        function preparePrintLayout() {{
          root.classList.add("is-printing");
          fitAllSlides();
        }}

        function cleanupPrintLayout() {{
          root.classList.remove("is-printing");
          refreshSlideLayout();
        }}

        async function printSlides() {{
          if (document.fullscreenElement) {{
            await document.exitFullscreen();
          }}
          root.classList.add("is-printing");
          await nextFrame();
          fitAllSlides();
          await nextFrame();
          window.print();
        }}

        function fitSlideTitle(slide) {{
          const content = slide.querySelector(".slide-content");
          const title = content ? content.querySelector("h1") : null;
          if (!content || !title) {{
            return;
          }}
          let size = 2.55;
          const minSize = 1.85;
          content.style.setProperty("--slide-title-size", `${{size.toFixed(2)}}rem`);
          while (
            (title.scrollHeight > title.clientHeight + 1 || title.scrollWidth > title.clientWidth + 1)
            && size > minSize
          ) {{
            size -= 0.08;
            content.style.setProperty("--slide-title-size", `${{size.toFixed(2)}}rem`);
          }}
        }}

        function fitSlideContent(slide) {{
          const content = slide.querySelector(".slide-content");
          const fit = slide.querySelector(".slide-fit");
          if (!content || !fit) {{
            return;
          }}
          content.style.setProperty("--slide-content-scale", "1");
          const styles = getComputedStyle(content);
          const horizontalPadding = parseFloat(styles.paddingLeft) + parseFloat(styles.paddingRight);
          const verticalPadding = parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom);
          const availableWidth = content.clientWidth - horizontalPadding;
          const availableHeight = content.clientHeight - verticalPadding;
          const neededWidth = fit.scrollWidth;
          const neededHeight = fit.scrollHeight;
          if (!availableWidth || !availableHeight || !neededWidth || !neededHeight) {{
            return;
          }}
          const scale = Math.min(1, availableWidth / neededWidth, availableHeight / neededHeight);
          content.style.setProperty("--slide-content-scale", Math.max(0.1, scale).toFixed(3));
        }}

        function fitActiveSlide() {{
          const slide = slides[current];
          fitSlideTitle(slide);
          fitSlideContent(slide);
          updateNotesPanelHeight(slide);
        }}

        function fitAllSlides() {{
          slides.forEach((slide) => {{
            fitSlideTitle(slide);
            fitSlideContent(slide);
          }});
        }}

        function updateNotesPanelHeight(slide = slides[current]) {{
          const stage = slide ? slide.querySelector(".slide-stage") : null;
          if (!stage) {{
            return;
          }}
          const height = stage.getBoundingClientRect().height;
          if (height > 0) {{
            root.style.setProperty("--active-slide-height", `${{height.toFixed(1)}}px`);
          }}
        }}

        function refreshSlideLayout() {{
          requestAnimationFrame(() => {{
            updateResponsiveStageSize();
            fitActiveSlide();
            updateFullscreenScale();
          }});
        }}

        function refreshAfterMediaLoads() {{
          document.querySelectorAll(".slide img, .slide iframe").forEach((media) => {{
            media.addEventListener("load", refreshSlideLayout, {{ once: false }});
          }});
          if (document.fonts && document.fonts.ready) {{
            document.fonts.ready.then(refreshSlideLayout).catch(() => {{}});
          }}
          window.addEventListener("load", refreshSlideLayout);
        }}

        document.querySelector('[data-action="first"]').addEventListener("click", () => showSlide(0));
        document.querySelector('[data-action="prev"]').addEventListener("click", () => showSlide(current - 1));
        document.querySelector('[data-action="next"]').addEventListener("click", nextSlide);
        scrubber.addEventListener("input", () => showSlide(Number(scrubber.value) - 1));
        sectionButtons.forEach((button) => {{
          button.addEventListener("click", () => {{
            showSlide(Number(button.dataset.sectionTarget || "1") - 1);
            button.blur();
          }});
        }});
        notesButton.addEventListener("click", () => {{
          showNotes = !showNotes;
          notesButton.setAttribute("aria-pressed", showNotes ? "true" : "false");
          updateNotes();
        }});
        studentNotes.addEventListener("input", writeStudentNote);
        downloadNotesButton.addEventListener("click", downloadStudentNotes);
        fullscreenButton.addEventListener("click", () => {{
          if (document.fullscreenElement) {{
            document.exitFullscreen();
          }} else {{
            document.documentElement.requestFullscreen();
          }}
          fullscreenButton.blur();
        }});
        printButton.addEventListener("click", printSlides);
        document.addEventListener("fullscreenchange", updateFullscreenState);
        window.addEventListener("beforeprint", preparePrintLayout);
        window.addEventListener("afterprint", cleanupPrintLayout);
        window.addEventListener("resize", refreshSlideLayout);
        refreshAfterMediaLoads();

        document.addEventListener("keydown", (event) => {{
          const activeTag = document.activeElement ? document.activeElement.tagName : "";
          if (["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A"].includes(activeTag)) {{
            return;
          }}
          if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {{
            event.preventDefault();
            nextSlide();
          }} else if (event.key === "ArrowLeft" || event.key === "PageUp") {{
            event.preventDefault();
            showSlide(current - 1);
          }} else if (event.key === "Home") {{
            event.preventDefault();
            showSlide(0);
          }} else if (event.key === "End") {{
            event.preventDefault();
            showSlide(slides.length - 1);
          }} else if (event.key.toLowerCase() === "n") {{
            event.preventDefault();
            notesButton.click();
          }} else if (event.key.toLowerCase() === "f") {{
            event.preventDefault();
            fullscreenButton.click();
          }}
        }});

        cacheBrowserNotes();
        loadProjectNotes();
        current = slideFromHash();
        showSlide(current, false);
        updateFullscreenState();
      }})();
    </script>
  </body>
</html>
"""


def build_slides(source: Path, output: Path) -> None:
    markdown = source.read_text(encoding="utf-8")
    slides = [
        render_slide(raw, index + 1, source.parent)
        for index, raw in enumerate(split_slides(markdown))
    ]
    if not slides:
        raise SystemExit(f"No slides found in {source}")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    assets_output = output.parent / "assets"
    assets_output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DOCS_ROOT / "assets", assets_output, dirs_exist_ok=True)
    shutil.copy2(ROOT / "assets" / STYLE_ASSET, assets_output / STYLE_ASSET)
    shutil.copy2(PROJECT_ROOT / "LICENSE", output.parent / "LICENSE")
    output.write_text(render_html(source.resolve(), slides, output.parent, output.name), encoding="utf-8")
    display_path = output.relative_to(Path.cwd()) if output.is_relative_to(Path.cwd()) else output
    print(f"wrote {display_path} from {source.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Markdown slide source.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Generated HTML deck path.",
    )
    args = parser.parse_args()

    build_slides(args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
