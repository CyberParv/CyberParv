#!/usr/bin/env python3
"""Generate the CyberParv GitHub profile graphics.

The generated SVGs are committed to the repository and referenced locally from
README.md. That keeps the profile independent from third-party README widgets.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "assets" / "generated"
AVATAR = ROOT / "assets" / "avatar.jpg"

LOGIN = os.environ.get("GH_LOGIN") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "CyberParv"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

WIDTH = 1000
BG = "#0f1720"
PANEL = "#151f2b"
INK = "#edf3f7"
MUTED = "#9aa8b5"
FAINT = "#314153"
CYAN = "#51d4e8"
LIME = "#9be564"
AMBER = "#f5bd5f"
PINK = "#ff7aa8"
VIOLET = "#b39cff"
BLUE = "#6db3ff"
RAMP = " .`:-=+*cs#%@"

IGNORE_REPOS = (
    re.compile(r"^proj_", re.I),
    re.compile(r"^github-(test|init-test)", re.I),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-", re.I),
    re.compile(r"^(test-|test_|mobile-app$|test-mobile-app$)", re.I),
    re.compile(r"^(edu_app_|fitness-app-|bean-brew-coffee-test)", re.I),
)

FEATURED = {
    "SecurGeek_v2": "Cybersecurity training platform with React, Supabase, PostgreSQL, RLS, roles, courses, and progress tracking.",
    "architect_plus": "Flask and Gemini app that turns natural language briefs into structured architectural design specifications.",
    "n8n_builder": "Production workflow-building workspace for n8n, MCP tooling, templates, validation, and reusable agent skills.",
    "cyberparv.github.io": "Portfolio for cybersecurity, AI, and web technology work.",
}

FALLBACK_LANGUAGE_COLORS = {
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Python": "#3572A5",
    "Swift": "#F05138",
    "CSS": "#663399",
    "HTML": "#e34c26",
    "Shell": "#89e051",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def font(size: int, weight: int = 500, color: str = INK) -> str:
    return (
        f"font-family='SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace' "
        f"font-size='{size}' font-weight='{weight}' fill='{color}'"
    )


def sans(size: int, weight: int = 500, color: str = INK) -> str:
    return (
        f"font-family='Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif' "
        f"font-size='{size}' font-weight='{weight}' fill='{color}'"
    )


def text(x: float, y: float, content: Any, attrs: str = "") -> str:
    return f"<text x='{x:g}' y='{y:g}' {attrs}>{esc(content)}</text>"


def rect(x: float, y: float, w: float, h: float, fill: str, radius: float = 0, attrs: str = "") -> str:
    return (
        f"<rect x='{x:g}' y='{y:g}' width='{w:g}' height='{h:g}' "
        f"rx='{radius:g}' fill='{fill}' {attrs}/>"
    )


def line(x1: float, y1: float, x2: float, y2: float, color: str, width: float = 1, attrs: str = "") -> str:
    return (
        f"<line x1='{x1:g}' y1='{y1:g}' x2='{x2:g}' y2='{y2:g}' "
        f"stroke='{color}' stroke-width='{width:g}' {attrs}/>"
    )


def svg(width: int, height: int, body: str, label: str) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' role='img' aria-label='{esc(label)}' "
        f"viewBox='0 0 {width} {height}' width='{width}' height='{height}'>"
        f"<title>{esc(label)}</title>"
        f"{rect(0, 0, width, height, BG)}"
        f"{body}"
        "</svg>\n"
    )


def write_svg(name: str, content: str) -> None:
    ET.fromstring(content)
    path = GENERATED / name
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous != content:
        path.write_text(content, encoding="utf-8")


def fmt_int(value: int) -> str:
    return f"{value:,}"


def short_int(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN or GH_TOKEN is required to generate profile data.")

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "CyberParv-profile-generator",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"GitHub GraphQL request failed: {exc.code} {detail}") from exc

    if payload.get("errors"):
        raise SystemExit(json.dumps(payload["errors"], indent=2))
    return payload["data"]


def fetch_profile() -> dict[str, Any]:
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=364)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        login
        name
        bio
        location
        websiteUrl
        followers { totalCount }
        following { totalCount }
        repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, orderBy: {field: UPDATED_AT, direction: DESC}) {
          totalCount
          nodes {
            name
            description
            url
            isFork
            stargazerCount
            forkCount
            pushedAt
            updatedAt
            primaryLanguage { name color }
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node { name color }
              }
            }
            repositoryTopics(first: 10) {
              nodes { topic { name } }
            }
          }
        }
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    data = graphql(
        query,
        {
            "login": LOGIN,
            "from": f"{start.isoformat()}T00:00:00Z",
            "to": f"{today.isoformat()}T23:59:59Z",
        },
    )
    user = data.get("user")
    if not user:
        raise SystemExit(f"GitHub user not found: {LOGIN}")
    return user


def is_meaningful_repo(repo: dict[str, Any]) -> bool:
    name = repo["name"]
    if repo.get("isFork"):
        return False
    if any(pattern.search(name) for pattern in IGNORE_REPOS):
        return False
    description = (repo.get("description") or "").lower()
    if description.startswith("generated project:") or description.startswith("generated mobile app:"):
        return False
    return True


def calendar_days(user: dict[str, Any]) -> list[dict[str, Any]]:
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [day for week in weeks for day in week["contributionDays"]]
    return sorted(days, key=lambda day: day["date"])


def streaks(days: list[dict[str, Any]]) -> tuple[int, int, str, str]:
    current = 0
    for day in reversed(days):
        if day["contributionCount"] > 0:
            current += 1
        else:
            break

    best = 0
    run = 0
    best_start = ""
    best_end = ""
    run_start = ""
    for day in days:
        if day["contributionCount"] > 0:
            if run == 0:
                run_start = day["date"]
            run += 1
            if run > best:
                best = run
                best_start = run_start
                best_end = day["date"]
        else:
            run = 0
            run_start = ""
    return current, best, best_start, best_end


def weekly_counts(days: list[dict[str, Any]]) -> list[int]:
    counts: list[int] = []
    for index in range(0, len(days), 7):
        counts.append(sum(day["contributionCount"] for day in days[index : index + 7]))
    return counts[-52:]


def language_data(repos: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    bytes_by_language: dict[str, dict[str, Any]] = defaultdict(lambda: {"bytes": 0, "color": MUTED})
    repo_counts: Counter[str] = Counter()

    for repo in repos:
        primary = repo.get("primaryLanguage")
        if primary and primary.get("name"):
            repo_counts[primary["name"]] += 1

        for edge in repo.get("languages", {}).get("edges", []):
            node = edge.get("node") or {}
            language = node.get("name")
            if not language:
                continue
            bytes_by_language[language]["bytes"] += int(edge.get("size") or 0)
            bytes_by_language[language]["color"] = node.get("color") or FALLBACK_LANGUAGE_COLORS.get(language, MUTED)

    rows = [
        {"name": name, "bytes": int(info["bytes"]), "color": info["color"]}
        for name, info in bytes_by_language.items()
        if info["bytes"] > 0
    ]
    rows.sort(key=lambda row: row["bytes"], reverse=True)
    return rows, repo_counts


def max_or_one(values: Iterable[int]) -> int:
    values = list(values)
    return max(values) if values else 1


def render_header(user: dict[str, Any], repos: list[dict[str, Any]], days: list[dict[str, Any]]) -> str:
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    top_language = "TypeScript"
    languages, _ = language_data(repos)
    if languages:
        top_language = languages[0]["name"]

    body = []
    body.append(rect(0, 0, WIDTH, 10, CYAN))
    body.append(rect(0, 10, 330, 6, LIME))
    body.append(rect(330, 10, 330, 6, AMBER))
    body.append(rect(660, 10, 340, 6, PINK))
    for y in range(40, 220, 28):
        body.append(line(48, y, 952, y, "#172331", 1))

    body.append(text(54, 86, "Parv Jain", sans(58, 750, INK)))
    body.append(text(58, 124, "CyberParv", font(22, 650, CYAN)))
    body.append(text(58, 162, "AI automation / cybersecurity / full-stack web apps", sans(24, 520, "#d8e3ea")))
    body.append(text(58, 198, "Jaipur, India  |  Manipal University Jaipur  |  parv.space", font(17, 500, MUTED)))

    stats = [
        ("public repos", fmt_int(user["repositories"]["totalCount"])),
        ("last-year contribs", fmt_int(total)),
        ("top language", top_language),
    ]
    x = 592
    for label, value in stats:
        body.append(rect(x, 62, 124, 92, PANEL, 8, "stroke='#263648' stroke-width='1'"))
        value_size = 18 if len(value) >= 9 else 25
        body.append(text(x + 12, 96, value, font(value_size, 750, INK)))
        body.append(text(x + 12, 126, label, font(11, 500, MUTED)))
        x += 136

    counts = weekly_counts(days)
    maximum = max_or_one(counts)
    spark_x = 600
    spark_y = 188
    bar_w = 5
    gap = 3
    for index, count in enumerate(counts[-44:]):
        height = 3 + int((count / maximum) * 30) if count else 2
        color = CYAN if count else FAINT
        body.append(rect(spark_x + index * (bar_w + gap), spark_y - height, bar_w, height, color, 1))
    body.append(text(600, 218, "weekly contribution rhythm, generated in this repo", font(12, 500, MUTED)))
    return svg(WIDTH, 244, "".join(body), "Parv Jain GitHub profile header")


def avatar_to_ascii(cols: int = 76) -> list[str]:
    if not AVATAR.exists():
        return ["CyberParv".center(cols), "avatar source missing".center(cols)]

    image = Image.open(AVATAR).convert("RGB")
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    image = image.resize((cols, int(cols * 0.48)), Image.Resampling.LANCZOS)
    image = ImageEnhance.Contrast(image).enhance(1.85)
    image = ImageEnhance.Sharpness(image).enhance(1.35)
    image = image.filter(ImageFilter.SMOOTH_MORE).convert("L")

    lines: list[str] = []
    for y in range(image.height):
        chars = []
        for x in range(image.width):
            value = image.getpixel((x, y))
            normalized = 1.0 - (value / 255.0)
            normalized = min(1.0, max(0.0, normalized ** 0.78))
            chars.append(RAMP[int(normalized * (len(RAMP) - 1))])
        lines.append("".join(chars).rstrip())
    return lines


def render_portrait() -> str:
    lines = avatar_to_ascii()
    font_size = 12.9
    line_height = 15
    char_width = 7.74
    padding_x = 22
    padding_y = 28
    width = int(padding_x * 2 + 76 * char_width)
    height = int(padding_y * 2 + len(lines) * line_height + 34)

    body = []
    body.append(rect(0, 0, width, height, "#101820"))
    body.append(text(padding_x, 25, "$ whoami", font(13, 650, LIME)))
    body.append(text(width - 220, 25, "animated ascii portrait", font(12, 500, MUTED)))

    defs = ["<defs>"]
    content = []
    cursor = []
    for index, row in enumerate(lines):
        y = padding_y + 24 + index * line_height
        clip_id = f"row{index}"
        row_width = max(2, min(len(row), 76) * char_width)
        begin = index * 0.075
        dur = 0.28
        defs.append(
            f"<clipPath id='{clip_id}'><rect x='{padding_x:g}' y='{y - line_height + 2:g}' "
            f"width='0' height='{line_height + 3:g}'>"
            f"<animate attributeName='width' from='0' to='{row_width:g}' dur='{dur:.2f}s' "
            f"begin='{begin:.3f}s' fill='freeze'/></rect></clipPath>"
        )
        content.append(
            f"<text x='{padding_x:g}' y='{y:g}' xml:space='preserve' "
            f"{font(font_size, 500, '#dce7ed')} clip-path='url(#{clip_id})'>{esc(row)}</text>"
        )
        cursor.append(
            f"<rect x='{padding_x:g}' y='{y - 11:g}' width='7' height='13' fill='{CYAN}' opacity='0'>"
            f"<set attributeName='opacity' to='0.85' begin='{begin:.3f}s' dur='{dur:.2f}s'/>"
            f"<animate attributeName='x' from='{padding_x:g}' to='{padding_x + row_width:g}' "
            f"dur='{dur:.2f}s' begin='{begin:.3f}s' fill='freeze'/>"
            f"<set attributeName='opacity' to='0' begin='{begin + dur:.3f}s'/></rect>"
        )
    defs.append("</defs>")
    body.extend(defs)
    body.extend(content)
    body.extend(cursor)
    body.append(text(padding_x, height - 22, "Parv Jain / CyberParv", font(13, 650, CYAN)))
    return svg(width, height, "".join(body), "Animated ASCII portrait of Parv Jain")


def render_stats(user: dict[str, Any], repos: list[dict[str, Any]], days: list[dict[str, Any]]) -> str:
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    current, best, _, _ = streaks(days)
    counts = weekly_counts(days)
    maximum = max_or_one(counts)

    body = []
    body.append(text(42, 48, "activity", font(22, 750, CYAN)))
    body.append(text(42, 78, "Public GitHub signal, generated from GraphQL inside this repository.", sans(16, 500, MUTED)))

    cards = [
        ("contributions", fmt_int(total), "last 365 days", CYAN),
        ("repositories", fmt_int(user["repositories"]["totalCount"]), "public owner repos", LIME),
        ("current streak", f"{current}d", "ending today if active", AMBER),
        ("longest streak", f"{best}d", "last 365 days", PINK),
    ]
    x = 42
    for label, value, caption, color in cards:
        body.append(rect(x, 112, 210, 88, PANEL, 8, "stroke='#263648' stroke-width='1'"))
        body.append(rect(x, 112, 5, 88, color, 2))
        body.append(text(x + 22, 150, value, font(29, 760, INK)))
        body.append(text(x + 22, 176, label, font(13, 650, color)))
        body.append(text(x + 22, 194, caption, font(11, 500, MUTED)))
        x += 230

    x0 = 42
    y0 = 260
    body.append(text(x0, y0 - 24, "weekly columns", font(13, 650, MUTED)))
    bar_w = 13
    gap = 5
    for index, count in enumerate(counts):
        height = 3 + int((count / maximum) * 72) if count else 2
        color = CYAN if count else FAINT
        body.append(rect(x0 + index * (bar_w + gap), y0 + 82 - height, bar_w, height, color, 2))
    body.append(text(x0, 372, "Each column is one UTC week. No external card service is requested by this README.", font(12, 500, MUTED)))
    return svg(WIDTH, 400, "".join(body), "CyberParv GitHub activity stats")


def render_streak(user: dict[str, Any], days: list[dict[str, Any]]) -> str:
    current, best, best_start, best_end = streaks(days)
    active_days = sum(1 for day in days if day["contributionCount"] > 0)
    busiest = max(days, key=lambda day: day["contributionCount"]) if days else {"date": "", "contributionCount": 0}

    body = []
    body.append(text(42, 48, "streak discipline", font(22, 750, AMBER)))
    body.append(text(42, 78, "The profile tracks consistency without a hosted streak widget.", sans(16, 500, MUTED)))

    items = [
        ("current", f"{current} days", "consecutive active days"),
        ("longest", f"{best} days", f"{best_start} to {best_end}" if best_start else "no active range yet"),
        ("active days", f"{active_days} / {len(days)}", "days with public contributions"),
        ("busiest day", short_int(busiest["contributionCount"]), busiest["date"]),
    ]
    x = 42
    for label, value, caption in items:
        body.append(rect(x, 112, 210, 88, PANEL, 8, "stroke='#263648' stroke-width='1'"))
        body.append(text(x + 18, 148, value, font(24, 760, INK)))
        body.append(text(x + 18, 174, label, font(13, 650, AMBER)))
        body.append(text(x + 18, 194, caption, font(11, 500, MUTED)))
        x += 230

    return svg(WIDTH, 230, "".join(body), "CyberParv contribution streaks")


def render_languages(repos: list[dict[str, Any]]) -> str:
    languages, repo_counts = language_data(repos)
    total_bytes = sum(row["bytes"] for row in languages) or 1
    top = languages[:7]

    body = []
    body.append(text(42, 48, "language map", font(22, 750, LIME)))
    body.append(text(42, 78, "Filtered to public, non-generated repositories so the profile highlights real project work.", sans(16, 500, MUTED)))

    y = 118
    for row in top:
        pct = row["bytes"] / total_bytes
        bar_width = int(610 * pct)
        color = row["color"] or FALLBACK_LANGUAGE_COLORS.get(row["name"], CYAN)
        body.append(text(42, y + 17, row["name"], font(14, 650, INK)))
        body.append(rect(208, y, 610, 18, "#243244", 5))
        body.append(rect(208, y, max(4, bar_width), 18, color, 5))
        body.append(text(842, y + 15, f"{pct * 100:4.1f}%", font(13, 650, MUTED)))
        body.append(text(910, y + 15, f"{repo_counts.get(row['name'], 0)} repos", font(12, 500, MUTED)))
        y += 32

    if not top:
        body.append(text(42, 138, "Language data will appear after public repositories report byte totals.", font(16, 500, MUTED)))

    return svg(WIDTH, 370, "".join(body), "CyberParv language breakdown")


def render_calendar(days: list[dict[str, Any]]) -> str:
    counts = [day["contributionCount"] for day in days]
    maximum = max_or_one(counts)
    chars = " .:-=+*#%@"

    body = []
    body.append(text(42, 48, "contribution year", font(22, 750, PINK)))
    body.append(text(42, 78, "One character per UTC day, using the same ASCII idea as the portrait.", sans(16, 500, MUTED)))

    cell = 14
    gap = 4
    x0 = 42
    y0 = 122
    for index, day in enumerate(days):
        col = index // 7
        row = index % 7
        count = day["contributionCount"]
        normalized = 0 if count == 0 else max(1, math.ceil((count / maximum) * (len(chars) - 1)))
        char = chars[normalized]
        color = FAINT if count == 0 else [VIOLET, BLUE, CYAN, LIME, AMBER, PINK][min(5, normalized * 6 // len(chars))]
        x = x0 + col * (cell + gap)
        y = y0 + row * (cell + gap)
        body.append(text(x, y + 12, char, font(14, 650, color)))

    body.append(text(42, 270, "less", font(12, 500, MUTED)))
    legend_x = 84
    for i, char in enumerate([".", ":", "+", "#", "@"]):
        color = [FAINT, VIOLET, CYAN, LIME, PINK][i]
        body.append(text(legend_x + i * 24, 270, char, font(14, 650, color)))
    body.append(text(220, 270, "more", font(12, 500, MUTED)))
    body.append(text(720, 270, f"{len(days)} days from GitHub GraphQL", font(12, 500, MUTED)))
    return svg(WIDTH, 300, "".join(body), "CyberParv contribution calendar")


def render_projects(repos: list[dict[str, Any]]) -> str:
    repo_by_name = {repo["name"]: repo for repo in repos}
    body = []
    body.append(text(42, 48, "selected builds", font(22, 750, BLUE)))
    body.append(text(42, 78, "Curated from public repositories; links and fuller details live below the image in Markdown.", sans(16, 500, MUTED)))

    y = 112
    accents = [CYAN, LIME, AMBER, PINK]
    for index, (name, fallback) in enumerate(FEATURED.items()):
        repo = repo_by_name.get(name, {})
        description = repo.get("description") or fallback
        language = ((repo.get("primaryLanguage") or {}).get("name")) or "Mixed"
        stars = repo.get("stargazerCount", 0)
        forks = repo.get("forkCount", 0)
        color = accents[index % len(accents)]

        body.append(rect(42, y, 916, 74, PANEL, 8, "stroke='#263648' stroke-width='1'"))
        body.append(rect(42, y, 6, 74, color, 2))
        body.append(text(66, y + 28, name, font(17, 750, INK)))
        body.append(text(66, y + 53, description[:112] + ("..." if len(description) > 112 else ""), sans(13, 500, MUTED)))
        body.append(text(780, y + 28, language, font(13, 650, color)))
        body.append(text(780, y + 53, f"{stars} stars / {forks} forks", font(12, 500, MUTED)))
        y += 88

    return svg(WIDTH, 500, "".join(body), "Featured CyberParv projects")


def main() -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    user = fetch_profile()
    all_repos = user["repositories"]["nodes"]
    meaningful_repos = [repo for repo in all_repos if is_meaningful_repo(repo)]
    repos_for_language = meaningful_repos or [repo for repo in all_repos if not repo.get("isFork")]
    days = calendar_days(user)

    write_svg("header.svg", render_header(user, repos_for_language, days))
    write_svg("portrait.svg", render_portrait())
    write_svg("stats.svg", render_stats(user, repos_for_language, days))
    write_svg("streak.svg", render_streak(user, days))
    write_svg("languages.svg", render_languages(repos_for_language))
    write_svg("calendar.svg", render_calendar(days))
    write_svg("projects.svg", render_projects(all_repos))


if __name__ == "__main__":
    main()
