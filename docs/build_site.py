#!/usr/bin/env python3
"""Generate the GF5 static website from Markdown sources.

The Markdown files are the source of truth. Generated HTML files should not be
edited by hand; rerun this script after editing Markdown.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT.parent / "site"
SITE_TITLE = "GF5: Animating 3D Characters"
GITHUB_REPOSITORY_URL = "https://github.com/CambridgeCVCourses/IIA-Project-GF5"
COPYRIGHT_OWNER = "Elliott (Shangzhe) Wu"
COPYRIGHT_OWNER_URL = "https://www.elliottwu.com/"


@dataclass(frozen=True)
class Page:
    source: str
    output: str
    nav_label: str
    eyebrow: str


@dataclass(frozen=True)
class SlideDeck:
    source: str
    output: str
    nav_label: str


SLIDE_DECKS = [
    SlideDeck("../slides/parts12.md", "parts12-slides.html", "Parts 1&2"),
    SlideDeck("../slides/part3.md", "part3-slides.html", "Part 3"),
]

PAGES = [
    Page("project_overview.md", "index.html", "Overview", "Student release"),
    Page("setup.md", "setup.html", "Setup", "Before coding"),
    Page("part1.md", "part1.html", "Part 1", "Part 1"),
    Page("part2.md", "part2.html", "Part 2", "Part 2"),
    Page("interim.md", "interim.html", "Interim Report", "Checkpoint"),
    Page("part3.md", "part3.html", "Part 3", "Group project"),
    Page("scene_editor.md", "scene_editor.html", "Scene Editor", "Part 3 tool"),
    Page("showcase.md", "showcase.html", "Showcase", "Final session"),
    Page("final_report.md", "final_report.html", "Final Report", "Final submission"),
    Page("faq.md", "faq.html", "FAQ", "Common questions"),
    Page("references.md", "references.html", "References", "Further reading"),
]


def build_source_to_output() -> dict[str, str]:
    mapping = {page.source: page.output for page in PAGES}
    for deck in SLIDE_DECKS:
        mapping[deck.source] = deck.output
        if deck.source.startswith("../"):
            mapping[deck.source[3:]] = deck.output
    return mapping


SOURCE_TO_OUTPUT = build_source_to_output()


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    ident: str


@dataclass(frozen=True)
class RenderedDocument:
    body: str
    title: str
    headings: tuple[Heading, ...]


def strip_inline_markdown(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", text)
    return text


def slugify(text: str, used: dict[str, int]) -> str:
    base = strip_inline_markdown(text).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not base:
        base = "section"
    count = used.get(base, 0)
    used[base] = count + 1
    return base if count == 0 else f"{base}-{count + 1}"


def rewrite_href(href: str) -> str:
    if re.match(r"^[a-z]+:", href) or href.startswith("#"):
        return href
    path, fragment = (href.split("#", 1) + [""])[:2] if "#" in href else (href, "")
    output = SOURCE_TO_OUTPUT.get(path, path)
    if output.endswith(".md"):
        output = output[:-3] + ".html"
    return f"{output}#{fragment}" if fragment else output


def format_plain(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    return text


def format_inline(text: str) -> str:
    parts = re.split(r"(`[^`]*`)", text)
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`"):
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue

        pos = 0
        for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", part):
            rendered.append(format_plain(part[pos : match.start()]))
            label = format_plain(match.group(1))
            href = html.escape(rewrite_href(match.group(2)), quote=True)
            rendered.append(f'<a href="{href}">{label}</a>')
            pos = match.end()
        rendered.append(format_plain(part[pos:]))
    return "".join(rendered)


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
        raise SystemExit("YouTube directive is missing a video id")

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
        '<figure class="doc-media-embed youtube-embed">'
        '<div class="doc-media-frame">'
        f'<iframe src="https://www.youtube-nocookie.com/embed/{video_id}?{query}" '
        f'title="{title_attr}" loading="lazy" allowfullscreen '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
        'picture-in-picture; web-share"></iframe>'
        "</div>"
        f"{caption_html}"
        "</figure>"
    )


def local_video_embed(markdown: str) -> str:
    fields = split_directive_fields(markdown)
    if not fields or not fields[0]:
        raise SystemExit("Video directive is missing a source path")

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
        '<figure class="doc-media-embed local-video-embed">'
        '<div class="doc-media-frame">'
        f'<video controls preload="metadata" playsinline{autoplay_attr}{loop_attr}>'
        f'<source src="{src}"{type_attr}>'
        f"{fallback}"
        "</video>"
        "</div>"
        f"{caption_html}"
        "</figure>"
    )


SCHEDULE_COLUMNS = [
    ("Tue", "am", "Tue AM", "11-13"),
    ("Fri", "am", "Fri AM", "9-11"),
    ("Fri", "pm", "Fri PM", "see cells / due"),
]
SCHEDULE_WEEKS = [
    {
        "label": "Intro",
        "dates": "15 May",
        "am": {"Fri": [("mandatory", "Intro session", "9-11, LR11")]},
        "pm": {"Fri": [("help", "Help", "14-16, BE454")]},
    },
    {
        "label": "Week 1",
        "dates": "18-22 May",
        "am": {
            "Tue": [("help", "Help", "11-13, BE454")],
            "Fri": [("help", "Help", "9-11, BE454")],
        },
        "pm": {"Fri": [("mandatory", "Mandatory", "14-16, LR11")]},
    },
    {
        "label": "Week 2",
        "dates": "25-29 May",
        "am": {
            "Tue": [("help", "Help", "11-13, BE454")],
            "Fri": [("help", "Help", "9-10, BE454")],
        },
        "pm": {
            "Fri": [
                ("mandatory", "Mandatory", "14-16, LR11"),
                ("deadline", "Interim due", "2pm"),
            ]
        },
    },
    {
        "label": "Week 3",
        "dates": "1-5 Jun",
        "am": {
            "Tue": [("help", "Help", "11-13, BE454")],
            "Fri": [("help", "Help", "9-11, BE454")],
        },
        "pm": {"Fri": [("mandatory", "Mandatory", "15-16, LR11")]},
    },
    {
        "label": "Week 4",
        "dates": "8-12 Jun",
        "am": {
            "Tue": [("presentation", "Showcase", "11-13, LT6")],
        },
        "pm": {
            "Fri": [
                ("deadline", "Final report due", "4pm; animation due"),
            ]
        },
    },
]
SCHEDULE_CALENDAR_NOTE = (
    "Booking is no longer needed for the BE454 help sessions. "
    "You can come to the office during the Help times shown in the calendar."
)


def schedule_calendar_embed(markdown: str = "") -> str:
    fields = split_directive_fields(markdown)
    highlight_updates = any(field in {"updates", "highlight-updates"} for field in fields[1:])
    highlighted_events = {
        ("Week 2", "Fri", "am", "help", "Help", "9-10, BE454"),
        ("Week 2", "Fri", "pm", "deadline", "Interim due", "2pm"),
        ("Week 3", "Fri", "pm", "mandatory", "Mandatory", "15-16, LR11"),
        ("Week 4", "Tue", "am", "presentation", "Showcase", "11-13, LT6"),
        ("Week 4", "Fri", "pm", "deadline", "Final report due", "4pm; animation due"),
    }
    highlighted_empty_cells = {("Week 4", "Fri", "am")}

    def render_event(kind: str, title: str, meta: str, *, highlighted: bool = False) -> str:
        classes = ["calendar-pin", f"is-{html.escape(kind, quote=True)}"]
        if highlighted:
            classes.append("is-highlighted")
        return (
            f'<span class="{" ".join(classes)}">'
            '<span class="pin-dot" aria-hidden="true"></span>'
            "<span>"
            f"<strong>{html.escape(title)}</strong>"
            f"<small>{html.escape(meta)}</small>"
            "</span>"
            "</span>"
        )

    rows: list[str] = []
    for week in SCHEDULE_WEEKS:
        cells = [
            '<tr>',
            '<th class="calendar-week" scope="row">',
            f'<strong>{html.escape(week["label"])}</strong>',
            f'<span>{html.escape(week["dates"])}</span>',
            "</th>",
        ]
        for day, slot, _label, _meta in SCHEDULE_COLUMNS:
            events = week.get(slot, {}).get(day, [])
            content = "".join(
                render_event(
                    *event,
                    highlighted=highlight_updates
                    and (week["label"], day, slot, *event) in highlighted_events,
                )
                for event in events
            )
            empty_class = " is-empty" if not content else ""
            multiple_class = " has-multiple" if len(events) > 1 else ""
            highlight_class = (
                " is-highlighted-empty"
                if highlight_updates and (week["label"], day, slot) in highlighted_empty_cells
                else ""
            )
            cells.append(
                f'<td class="calendar-cell{empty_class}{multiple_class}{highlight_class}">'
                f'<div class="calendar-cell-inner">{content}</div>'
                "</td>"
            )
        cells.append("</tr>")
        rows.append("".join(cells))

    legend = "".join(
        render_event(kind, title, "")
        for kind, title in [
            ("mandatory", "Mandatory"),
            ("help", "Optional help"),
            ("deadline", "Deadline"),
            ("presentation", "Showcase"),
        ]
    )
    return (
        '<section class="schedule-calendar" aria-label="Project session calendar">'
        '<div class="calendar-legend" aria-label="Calendar legend">'
        f"{legend}"
        "</div>"
        '<table class="calendar-table">'
        "<thead><tr><th>Week</th>"
        + "".join(
            f"<th><span>{html.escape(label)}</span><small>{html.escape(meta)}</small></th>"
            for _day, _slot, label, meta in SCHEDULE_COLUMNS
        )
        + "</tr></thead>"
        + "<tbody>"
        + "".join(rows)
        + "</tbody></table>"
        + (
            '<p class="calendar-change-note">'
            "<strong>Updated:</strong> Fri 29 May help is 9-10; interim report and results are due 2pm; "
            "Fri 5 Jun mandatory session is 15-16; Tue 9 Jun showcase is in LT6; "
            "Fri 12 Jun has no help or mandatory session."
            "</p>"
            if highlight_updates
            else ""
        )
        + f'<p class="calendar-note">{html.escape(SCHEDULE_CALENDAR_NOTE)}</p>'
        + "</section>"
    )


def reports_overview_embed(_markdown: str = "") -> str:
    interim_href = html.escape(rewrite_href("interim.md"), quote=True)
    final_href = html.escape(rewrite_href("final_report.md"), quote=True)
    items = [
        (
            f'<a href="{interim_href}">Interim Report</a>',
            "due after Part 2; individual report, code, videos, and comparison figures.",
        ),
        (
            f'<a href="{final_href}">Final Report</a>',
            "due after Part 3; each student submits a PDF with a shared group-work section and their own individual contribution section, plus the group animation result files.",
        ),
    ]

    rendered_items = "".join(
        f"<li><strong>{label}</strong>: {html.escape(description)}</li>"
        for label, description in items
    )
    return (
        "<p>There are two report checkpoints in the project.</p>"
        f"<ul>{rendered_items}</ul>"
        "<p>Each report page gives the exact structure, evidence, and submission requirements.</p>"
    )


def is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def parse_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(row: list[str]) -> bool:
    return bool(row) and all(re.match(r"^:?-{3,}:?$", cell.strip()) for cell in row)


def table_class_for(headers: list[str]) -> str:
    normalized = [strip_inline_markdown(header).strip().lower() for header in headers]
    classes = ["doc-table"]
    if normalized[:3] == ["week", "mode", "focus"]:
        classes.append("timeline-table")
    if "coursework" in normalized and "due date" in normalized:
        classes.append("assessment-table")
    if normalized[:3] == ["date", "time", "what"]:
        classes.append("key-dates-table")
    return " ".join(classes)


class MarkdownRenderer:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.out: list[str] = []
        self.heading_ids: dict[str, int] = {}
        self.paragraph: list[str] = []
        self.list_type: str | None = None
        self.list_items: list[str] = []
        self.list_start = 1
        self.table_rows: list[list[str]] = []
        self.in_code = False
        self.code_info = ""
        self.code_lines: list[str] = []
        self.title = ""
        self.headings: list[Heading] = []
        self.current_heading_id = ""

    def render(self, text: str) -> RenderedDocument:
        self.lines = text.splitlines()
        for line in self.lines:
            self.handle_line(line)
        self.close_all()
        return RenderedDocument("\n".join(self.out), self.title, tuple(self.headings))

    def handle_line(self, line: str) -> None:
        fence = re.match(r"^```(.*)$", line)
        if fence:
            if self.in_code:
                self.close_code()
            else:
                self.close_blocks()
                self.in_code = True
                self.code_info = fence.group(1).strip()
                self.code_lines = []
            return

        if self.in_code:
            self.code_lines.append(line)
            return

        if is_table_row(line):
            self.close_paragraph()
            self.close_list()
            self.table_rows.append(parse_table_row(line))
            return

        self.close_table()

        directive = re.match(r"^\s*\{\{([a-z-]+):\s*([^}]+?)\s*\}\}\s*$", line.strip())
        if directive:
            self.close_blocks()
            mode, payload = directive.groups()
            if mode == "youtube":
                self.out.append(youtube_embed(payload))
                return
            if mode == "video":
                self.out.append(local_video_embed(payload))
                return
            if mode == "schedule-calendar":
                self.out.append(schedule_calendar_embed(payload))
                return
            if mode == "reports-overview":
                self.out.append(reports_overview_embed(payload))
                return
            raise SystemExit(f"Unknown site directive: {mode}")

        image = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", line.strip())
        if image:
            self.close_blocks()
            alt = html.escape(image.group(1), quote=True)
            src = html.escape(rewrite_href(image.group(2)), quote=True)
            self.out.append(
                '<figure class="doc-figure">'
                f'<img src="{src}" alt="{alt}">'
                "</figure>"
            )
            return

        if not line.strip():
            self.close_blocks()
            return

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            self.close_blocks()
            level = len(heading.group(1))
            text = heading.group(2)
            if level == 1 and not self.title:
                self.title = strip_inline_markdown(text)
                return
            ident = slugify(text, self.heading_ids)
            self.current_heading_id = ident
            if level in {2, 3}:
                self.headings.append(Heading(level, strip_inline_markdown(text), ident))
            self.out.append(f'<h{level} id="{ident}">{format_inline(text)}</h{level}>')
            return

        item = re.match(r"^\s*([-*])\s+(.+)$", line)
        numbered = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
        if item or numbered:
            kind = "ul" if item else "ol"
            content = item.group(2) if item else numbered.group(2)
            start = int(numbered.group(1)) if numbered else None
            self.add_list_item(kind, content, start)
            return

        if self.list_type and re.match(r"^\s{2,}\S", line):
            self.list_items[-1] += " " + line.strip()
            return

        self.close_list()
        self.paragraph.append(line.strip())

    def add_list_item(self, kind: str, content: str, start: int | None = None) -> None:
        self.close_paragraph()
        if self.list_type and self.list_type != kind:
            self.close_list()
        if not self.list_type:
            self.list_start = start or 1
        self.list_type = kind
        self.list_items.append(content.strip())

    def close_code(self) -> None:
        language = ""
        if self.code_info:
            language = f' class="language-{html.escape(self.code_info, quote=True)}"'
        code = html.escape("\n".join(self.code_lines))
        self.out.append(f"<pre><code{language}>{code}</code></pre>")
        self.in_code = False
        self.code_info = ""
        self.code_lines = []

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

    def close_paragraph(self) -> None:
        if self.paragraph:
            text = " ".join(self.paragraph)
            self.out.append(f"<p>{format_inline(text)}</p>")
            self.paragraph = []

    def close_list(self) -> None:
        if self.list_type:
            list_class = ""
            list_classes = {
                "learning-goals": "checklist",
                "part-1-output": "checklist",
                "part-2-output": "checklist",
                "what-to-submit": "checklist",
                "required-figures-and-media": "checklist",
                "what-to-do-now": "checklist",
                "motivation": "feature-list",
                "four-week-shape": "timeline-list",
                "assessment-at-a-glance": "assessment-list",
                "animation-and-rigging": "reference-list",
                "recommended-starting-points": "reference-list",
                "useful-materials": "reference-list",
                "tools-used-in-gf5": "reference-list",
            }
            if self.list_type == "ul" and self.current_heading_id in list_classes:
                list_class = f' class="{list_classes[self.current_heading_id]}"'

            if self.list_type == "ol" and self.list_start != 1:
                self.out.append(f'<ol start="{self.list_start}"{list_class}>')
            else:
                self.out.append(f"<{self.list_type}{list_class}>")
            for item in self.list_items:
                self.out.append(f"  <li>{format_inline(item)}</li>")
            self.out.append(f"</{self.list_type}>")
            self.list_type = None
            self.list_items = []
            self.list_start = 1

    def close_blocks(self) -> None:
        self.close_table()
        self.close_paragraph()
        self.close_list()

    def close_all(self) -> None:
        if self.in_code:
            self.close_code()
        self.close_blocks()


def render_nav(
    current: Page | None,
    *,
    slides_active: bool = False,
    current_slide_output: str | None = None,
) -> str:
    def nav_link(label: str, href: str, active: bool = False, class_name: str = "") -> str:
        aria = ' aria-current="page"' if active else ""
        class_attr = f' class="{html.escape(class_name, quote=True)}"' if class_name else ""
        return f'          <a href="{html.escape(href, quote=True)}"{class_attr}{aria}>{html.escape(label)}</a>'

    overview = PAGES[0]
    material_pages = PAGES[1:]
    material_active = current in material_pages
    material_class = "nav-dropdown is-active" if material_active else "nav-dropdown"
    material_links = "\n".join(
        nav_link(page.nav_label, page.output, page == current) for page in material_pages
    )
    slide_decks = SLIDE_DECKS
    active_slide_output = current_slide_output or (slide_decks[0].output if slide_decks else "")
    slides_class = "nav-dropdown is-active" if slides_active else "nav-dropdown"
    slide_links = "\n".join(
        nav_link(deck.nav_label, deck.output, slides_active and deck.output == active_slide_output)
        for deck in slide_decks
    )
    github_href = html.escape(GITHUB_REPOSITORY_URL, quote=True)
    links = [
        nav_link(overview.nav_label, overview.output, current == overview),
        f"""          <div class="{material_class}" data-nav-dropdown>
            <button class="nav-dropdown-trigger" type="button" aria-haspopup="true" aria-expanded="false" data-nav-dropdown-trigger>Materials</button>
            <div class="nav-dropdown-menu" data-nav-dropdown-menu>
{material_links}
            </div>
          </div>""",
        f"""          <div class="{slides_class}" data-nav-dropdown>
            <button class="nav-dropdown-trigger" type="button" aria-haspopup="true" aria-expanded="false" data-nav-dropdown-trigger>Slides</button>
            <div class="nav-dropdown-menu" data-nav-dropdown-menu>
{slide_links}
            </div>
          </div>""",
        (
            f'          <a class="nav-github-button" href="{github_href}" '
            'target="_blank" rel="noreferrer">GitHub</a>'
        ),
    ]
    return "\n".join(links)


def render_release_summary() -> str:
    return f"""      <section class="release-strip" aria-label="Release summary">
        <div class="metric">
          <strong>Part 1</strong>
          <span>Forward kinematics and a saved custom motion.</span>
        </div>
        <div class="metric">
          <strong>Part 2</strong>
          <span>Skinning weights, one-hot binding, and LBS comparison.</span>
        </div>
        <div class="metric">
          <strong>Part 3</strong>
          <span>Group character animation, motion planning, and final video.</span>
        </div>
      </section>
"""


def render_actions(page: Page) -> str:
    if page.output == "index.html":
        github_href = html.escape(GITHUB_REPOSITORY_URL, quote=True)
        return f"""          <div class="actions">
            <a class="button primary" href="{github_href}" target="_blank" rel="noreferrer">GitHub codebase</a>
            <a class="button" href="setup.html">Start setup</a>
            <a class="button" href="parts12-slides.html">Open slides</a>
          </div>
"""
    index = PAGES.index(page)
    actions: list[str] = []
    if index > 0:
        previous = PAGES[index - 1]
        actions.append(
            f'<a class="button" href="{html.escape(previous.output, quote=True)}">'
            f'Previous: {html.escape(previous.nav_label)}</a>'
        )
    if index < len(PAGES) - 1:
        next_page = PAGES[index + 1]
        actions.append(
            f'<a class="button primary" href="{html.escape(next_page.output, quote=True)}">'
            f'Next: {html.escape(next_page.nav_label)}</a>'
        )
    if not actions:
        actions.append('<a class="button" href="index.html">Back to overview</a>')
    return "          <div class=\"actions\">\n            " + "\n            ".join(actions) + "\n          </div>\n"


def render_hero(page: Page, doc: RenderedDocument) -> str:
    title = html.escape(doc.title or page.nav_label)
    eyebrow = html.escape(page.eyebrow)
    actions = render_actions(page)
    if page.output == "index.html":
        return f"""      <section class="release-band">
        <div>
          <p class="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p class="lede">The Markdown handouts are the source of truth; this page is generated from them for the student-facing release.</p>
          <p class="instructor-line"><strong>Instructor:</strong> <a href="https://www.elliottwu.com/">Elliott (Shangzhe) Wu</a></p>
{actions}
        </div>
        <figure class="visual-panel" aria-label="Animation viewer preview">
          <img src="assets/gf5-rig-preview.svg" alt="Diagram of the GF5 viewer showing a block character, skeleton, skinning weights, and a timeline.">
        </figure>
      </section>
"""
    return f"""      <section class="doc-hero">
        <div>
          <p class="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
{actions}        </div>
      </section>
"""


def render_toc(doc: RenderedDocument) -> str:
    headings = [heading for heading in doc.headings if heading.level == 2]
    if not headings:
        return ""
    links = "\n".join(
        f'            <a href="#{html.escape(heading.ident, quote=True)}">{html.escape(heading.title)}</a>'
        for heading in headings
    )
    return f"""        <aside class="doc-toc" aria-label="On this page">
          <strong>On this page</strong>
{links}
        </aside>
"""


def render_page(
    page: Page,
    *,
    source_base_url: str | None = None,
    source_relative_base: str = "",
) -> str:
    markdown = (ROOT / page.source).read_text(encoding="utf-8")
    doc = MarkdownRenderer().render(markdown)
    title = doc.title or page.nav_label
    html_title = SITE_TITLE if title == SITE_TITLE else f"{title} | {SITE_TITLE}"
    release_summary = render_release_summary() if page.output == "index.html" else ""
    toc = render_toc(doc)
    article_class = "doc-content faq-content" if page.output == "faq.html" else "doc-content"
    if source_base_url:
        source_href = f"{source_base_url.rstrip('/')}/{page.source}"
    elif source_relative_base and source_relative_base != ".":
        source_href = f"{source_relative_base.rstrip('/')}/{page.source}"
    else:
        source_href = page.source
    return f"""<!doctype html>
<!-- Generated from {page.source} by docs/build_site.py. Do not edit by hand. -->
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(html_title)}</title>
    <link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
    <link rel="stylesheet" href="assets/site.css">
    <script src="assets/site.js" defer></script>
  </head>
  <body>
    <a class="skip-link" href="#main">Skip to content</a>
    <header class="site-header">
      <div class="nav-shell">
        <a class="brand" href="index.html" aria-label="GF5 home">
          <span class="brand-mark">GF5</span>
          <span>{html.escape(SITE_TITLE)}</span>
        </a>
        <nav class="nav-links" aria-label="Main navigation">
{render_nav(page)}
        </nav>
      </div>
    </header>

    <main id="main" class="page doc-page">
{render_hero(page, doc)}
      <div class="doc-shell">
{toc}        <article class="{article_class}">
{release_summary}
{indent(doc.body, 10)}
        </article>
      </div>
    </main>

    <footer class="footer">
      <div class="footer-inner">
        <p>
          Copyright &copy; 2026
          <a href="{html.escape(COPYRIGHT_OWNER_URL, quote=True)}">{html.escape(COPYRIGHT_OWNER)}</a>.
          Released under the <a href="LICENSE">MIT License</a>.
        </p>
        <p>
          Generated from Markdown source:
          <a href="{html.escape(source_href, quote=True)}">{html.escape(page.source)}</a>.
        </p>
      </div>
    </footer>
  </body>
</html>
"""


def indent(text: str, spaces: int) -> str:
    """Indent rendered HTML without changing visible whitespace in code blocks."""
    prefix = " " * spaces
    lines: list[str] = []
    in_pre = False
    for line in text.splitlines():
        lines.append(line if in_pre or not line else prefix + line)
        if re.search(r"<pre\b", line) and not re.search(r"</pre>", line):
            in_pre = True
        if in_pre and re.search(r"</pre>", line):
            in_pre = False
    return "\n".join(lines)


def build_site(
    output: Path,
    *,
    source_base_url: str | None = None,
) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assets_output = output / "assets"
    if assets_output.exists():
        shutil.rmtree(assets_output)
    shutil.copytree(ROOT / "assets", assets_output)
    shutil.copy2(ROOT.parent / "LICENSE", output / "LICENSE")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    source_relative_base = Path(os.path.relpath(ROOT, output)).as_posix()

    for page in PAGES:
        output_path = output / page.output
        output_path.write_text(
            render_page(
                page,
                source_base_url=source_base_url,
                source_relative_base=source_relative_base,
            ),
            encoding="utf-8",
        )
        display_path = output_path.relative_to(Path.cwd()) if output_path.is_relative_to(Path.cwd()) else output_path
        print(f"wrote {display_path} from {page.source}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory where generated site files should be written.",
    )
    parser.add_argument(
        "--source-base-url",
        default=None,
        help="Optional URL prefix for Markdown source links in generated footers.",
    )
    args = parser.parse_args()

    build_site(
        args.output.resolve(),
        source_base_url=args.source_base_url,
    )


if __name__ == "__main__":
    main()
