#!/usr/bin/env python3
"""Generate GitHub-style vibe coding heatmaps from Claude/Codex local history logs."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


PALETTE = ["#1d1511", "#4b2718", "#7a3b1d", "#b75a23", "#ff7b2c"]
OUTSIDE_YEAR_COLOR = "#120c08"
MARKER_START = "<!-- vibe-heatmap:start -->"
MARKER_END = "<!-- vibe-heatmap:end -->"
INTENSITY_LABELS = {
    "minutes": "active minutes/day",
    "sessions": "sessions/day",
    "events": "events/day",
}


@dataclass(frozen=True)
class Event:
    source: str
    ts: datetime
    session_key: str


@dataclass(frozen=True)
class SessionWindow:
    source: str
    start: datetime
    end: datetime
    session_key: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read Claude/Codex local history logs and generate a GitHub-style "
            "vibe coding heatmap."
        )
    )
    parser.add_argument(
        "--source",
        choices=["claude", "codex", "combined"],
        default="combined",
        help="Data source to render.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=datetime.now().year,
        help="Calendar year to render.",
    )
    parser.add_argument(
        "--claude-history",
        default="~/.claude/history.jsonl",
        help="Path to Claude history JSONL.",
    )
    parser.add_argument(
        "--codex-history",
        default="~/.codex/history.jsonl",
        help="Path to Codex history JSONL.",
    )
    parser.add_argument(
        "--output-svg",
        default="vibe-heatmap.svg",
        help="Output SVG path.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional output JSON summary path.",
    )
    parser.add_argument(
        "--readme",
        default="",
        help="Optional README path to update marker block.",
    )
    parser.add_argument(
        "--svg-url",
        default="",
        help=(
            "SVG URL/path used in README block. "
            "If omitted and --readme is set, a relative path is used."
        ),
    )
    parser.add_argument(
        "--idle-gap-minutes",
        type=float,
        default=25.0,
        help="Gap threshold used to split sessions.",
    )
    parser.add_argument(
        "--event-window-minutes",
        type=float,
        default=4.0,
        help="Active window size contributed by each event.",
    )
    parser.add_argument(
        "--intensity-mode",
        choices=["minutes", "sessions", "events"],
        default="minutes",
        help="Metric used for heatmap color depth.",
    )
    parser.add_argument(
        "--tz",
        default="",
        help="Timezone name (example: Asia/Hong_Kong). Defaults to local timezone.",
    )
    return parser.parse_args()


def resolve_tz(tz_name: str):
    if tz_name:
        if ZoneInfo is None:
            raise ValueError("ZoneInfo is unavailable in this Python runtime.")
        try:
            return ZoneInfo(tz_name)
        except Exception as exc:
            raise ValueError(f"Unsupported timezone: {tz_name}") from exc
    return datetime.now().astimezone().tzinfo


def ensure_parent(path: Path) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def to_datetime(value: float, tz) -> datetime:
    return datetime.fromtimestamp(value, tz=tz)


def parse_numeric_timestamp(raw: object) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
    elif isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            ts = float(raw)
        except ValueError:
            return None
    else:
        return None

    if ts > 1e12:
        ts = ts / 1000.0
    if ts < 0:
        return None
    return ts


def load_codex_events(path: Path, tz) -> List[Event]:
    events: List[Event] = []
    if not path.exists():
        return events

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_raw = parse_numeric_timestamp(payload.get("ts"))
            if ts_raw is None:
                continue

            session_id = str(payload.get("session_id") or payload.get("sessionId") or "unknown")
            events.append(
                Event(
                    source="codex",
                    ts=to_datetime(ts_raw, tz),
                    session_key=f"codex:{session_id}",
                )
            )
    return events


def load_claude_events(path: Path, tz) -> List[Event]:
    events: List[Event] = []
    if not path.exists():
        return events

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_raw = parse_numeric_timestamp(payload.get("timestamp") or payload.get("ts"))
            if ts_raw is None:
                continue

            session_id = str(payload.get("sessionId") or payload.get("session_id") or "unknown")
            events.append(
                Event(
                    source="claude",
                    ts=to_datetime(ts_raw, tz),
                    session_key=f"claude:{session_id}",
                )
            )
    return events


def filter_events(events: Sequence[Event], source: str) -> List[Event]:
    if source == "combined":
        chosen = list(events)
    else:
        chosen = [event for event in events if event.source == source]
    chosen.sort(key=lambda item: item.ts)
    return chosen


def build_sessions(events: Sequence[Event], idle_gap: timedelta) -> List[SessionWindow]:
    grouped: Dict[str, List[Event]] = defaultdict(list)
    for event in events:
        grouped[event.session_key].append(event)

    windows: List[SessionWindow] = []
    for session_key, group in grouped.items():
        group.sort(key=lambda item: item.ts)
        source = group[0].source
        start = group[0].ts
        last = group[0].ts
        for event in group[1:]:
            if event.ts - last > idle_gap:
                windows.append(
                    SessionWindow(source=source, start=start, end=last, session_key=session_key)
                )
                start = event.ts
            last = event.ts
        windows.append(SessionWindow(source=source, start=start, end=last, session_key=session_key))

    windows.sort(key=lambda item: item.start)
    return windows


def merge_intervals(intervals: Sequence[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda item: item[0])
    merged: List[Tuple[datetime, datetime]] = [ordered[0]]

    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def split_interval_by_day(
    start: datetime,
    end: datetime,
    year_start: datetime,
    year_end_exclusive: datetime,
) -> List[Tuple[date, float]]:
    clipped_start = max(start, year_start)
    clipped_end = min(end, year_end_exclusive)
    if clipped_end <= clipped_start:
        return []

    chunks: List[Tuple[date, float]] = []
    current = clipped_start
    while current.date() < clipped_end.date():
        boundary = datetime.combine(current.date() + timedelta(days=1), time.min, tzinfo=current.tzinfo)
        minutes = (boundary - current).total_seconds() / 60.0
        chunks.append((current.date(), minutes))
        current = boundary

    minutes = (clipped_end - current).total_seconds() / 60.0
    chunks.append((current.date(), minutes))
    return chunks


def quantile_thresholds(values: Sequence[float]) -> Tuple[float, float, float, float]:
    nonzero = sorted([value for value in values if value > 0])
    if not nonzero:
        return (0.0, 0.0, 0.0, 0.0)

    def pick(q: float) -> float:
        idx = int((len(nonzero) - 1) * q)
        return nonzero[idx]

    q1 = pick(0.25)
    q2 = pick(0.5)
    q3 = pick(0.75)
    q4 = nonzero[-1]

    if q1 == q2 == q3 == q4:
        q1 = q2 = q3 = q4
    return (q1, q2, q3, q4)


def to_level(value: float, thresholds: Tuple[float, float, float, float]) -> int:
    q1, q2, q3, _ = thresholds
    if value <= 0:
        return 0
    if value <= q1:
        return 1
    if value <= q2:
        return 2
    if value <= q3:
        return 3
    return 4


def sunday_on_or_before(day: date) -> date:
    shift = (day.weekday() + 1) % 7
    return day - timedelta(days=shift)


def saturday_on_or_after(day: date) -> date:
    shift = (5 - day.weekday()) % 7
    return day + timedelta(days=shift)


def render_svg(
    *,
    source: str,
    year: int,
    day_minutes: Dict[date, float],
    day_sessions: Dict[date, int],
    day_events: Dict[date, int],
    intensity_mode: str,
    display_start: date,
    display_end: date,
    summary: Dict[str, float],
) -> str:
    total_days = (display_end - display_start).days + 1
    weeks = math.ceil(total_days / 7)

    cell = 11
    gap = 4
    left = 56
    top = 52
    width = left + weeks * (cell + gap) + 32
    height = top + 7 * (cell + gap) + 80

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    if intensity_mode == "sessions":
        intensity_values = [float(value) for value in day_sessions.values()]
    elif intensity_mode == "events":
        intensity_values = [float(value) for value in day_events.values()]
    else:
        intensity_values = list(day_minutes.values())

    thresholds = quantile_thresholds(intensity_values)

    title = (
        f"{int(summary['sessions'])} sessions, {int(summary['active_minutes'])} active minutes, "
        f"{int(summary['active_days'])} active days in {year} ({source}, {intensity_mode})"
    )

    month_labels: List[str] = []
    for month in range(1, 13):
        first = date(year, month, 1)
        if not (display_start <= first <= display_end):
            continue
        week_index = (first - display_start).days // 7
        x = left + week_index * (cell + gap)
        month_labels.append(
            f'<text x="{x}" y="38" fill="#c9d1d9" font-size="10" font-family="system-ui, sans-serif">{first.strftime("%b")}</text>'
        )

    day_labels = [
        (1, "Mon"),
        (3, "Wed"),
        (5, "Fri"),
    ]

    day_label_nodes: List[str] = []
    for row, label in day_labels:
        y = top + row * (cell + gap) + 9
        day_label_nodes.append(
            f'<text x="16" y="{y}" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">{label}</text>'
        )

    cells: List[str] = []
    for current in date_range(display_start, display_end):
        week_index = (current - display_start).days // 7
        dow = (current.weekday() + 1) % 7
        x = left + week_index * (cell + gap)
        y = top + dow * (cell + gap)

        in_year = year_start <= current <= year_end
        minutes = day_minutes.get(current, 0.0) if in_year else 0.0
        sessions = day_sessions.get(current, 0) if in_year else 0
        events = day_events.get(current, 0) if in_year else 0

        if intensity_mode == "sessions":
            intensity_value = float(sessions)
        elif intensity_mode == "events":
            intensity_value = float(events)
        else:
            intensity_value = minutes

        level = to_level(intensity_value, thresholds)
        fill = PALETTE[level] if in_year else OUTSIDE_YEAR_COLOR

        tooltip = (
            f"{current.isoformat()}: {int(round(minutes))} active minutes, "
            f"{sessions} sessions, {events} events"
            if in_year
            else f"{current.isoformat()}: out of range"
        )
        cells.append(
            "".join(
                [
                    f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" ',
                    'rx="2" ry="2" ',
                    f'fill="{fill}"><title>{escape(tooltip)}</title></rect>',
                ]
            )
        )

    legend_x = width - 220
    legend_y = height - 24
    legend_cells = []
    for idx, color in enumerate(PALETTE):
        x = legend_x + 28 + idx * (cell + 5)
        legend_cells.append(
            f'<rect x="{x}" y="{legend_y - 9}" width="{cell}" height="{cell}" rx="2" ry="2" fill="{color}" />'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Vibe coding heatmap">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#0d1117" rx="10" />
  <text x="16" y="28" fill="#e6edf3" font-size="18" font-family="system-ui, sans-serif">{escape(title)}</text>
  {''.join(month_labels)}
  {''.join(day_label_nodes)}
  {''.join(cells)}
  <text x="{legend_x}" y="{legend_y}" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">Less</text>
  {''.join(legend_cells)}
  <text x="{legend_x + 28 + len(PALETTE) * (cell + 5) + 4}" y="{legend_y}" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">More ({INTENSITY_LABELS[intensity_mode]})</text>
</svg>
"""
    return svg


def build_report(
    events: Sequence[Event],
    source: str,
    year: int,
    idle_gap_minutes: float,
    event_window_minutes: float,
    tz,
) -> Dict[str, object]:
    year_start = datetime(year, 1, 1, tzinfo=tz)
    year_end_exclusive = datetime(year + 1, 1, 1, tzinfo=tz)

    selected = filter_events(events, source)
    idle_gap = timedelta(minutes=idle_gap_minutes)
    event_window = timedelta(minutes=event_window_minutes)

    sessions = build_sessions(selected, idle_gap)

    day_minutes: Dict[date, float] = defaultdict(float)
    day_events: Dict[date, int] = defaultdict(int)
    day_sessions: Dict[date, int] = defaultdict(int)

    for event in selected:
        if year_start <= event.ts < year_end_exclusive:
            day_events[event.ts.date()] += 1

    for session in sessions:
        if year_start <= session.start < year_end_exclusive:
            day_sessions[session.start.date()] += 1

    intervals = [(event.ts, event.ts + event_window) for event in selected]
    merged = merge_intervals(intervals)
    for start, end in merged:
        for day, minutes in split_interval_by_day(start, end, year_start, year_end_exclusive):
            day_minutes[day] += minutes

    all_days = list(date_range(date(year, 1, 1), date(year, 12, 31)))
    for day in all_days:
        day_minutes.setdefault(day, 0.0)
        day_events.setdefault(day, 0)
        day_sessions.setdefault(day, 0)

    total_minutes = sum(day_minutes.values())
    active_days = sum(1 for day in all_days if day_minutes[day] > 0)
    total_sessions = sum(day_sessions.values())
    total_events = sum(day_events.values())

    summary = {
        "active_minutes": round(total_minutes),
        "active_days": active_days,
        "sessions": total_sessions,
        "events": total_events,
        "avg_minutes_per_active_day": round(total_minutes / active_days, 2)
        if active_days
        else 0.0,
        "max_day_minutes": round(max(day_minutes.values()) if day_minutes else 0.0, 2),
    }

    display_start = sunday_on_or_before(date(year, 1, 1))
    display_end = saturday_on_or_after(date(year, 12, 31))

    day_rows = []
    for day in all_days:
        day_rows.append(
            {
                "date": day.isoformat(),
                "active_minutes": round(day_minutes[day], 2),
                "events": int(day_events[day]),
                "sessions": int(day_sessions[day]),
            }
        )

    return {
        "source": source,
        "year": year,
        "summary": summary,
        "day_minutes": {day: day_minutes[day] for day in all_days},
        "day_sessions": {day: day_sessions[day] for day in all_days},
        "day_events": {day: day_events[day] for day in all_days},
        "display_start": display_start,
        "display_end": display_end,
        "days": day_rows,
    }


def update_readme_block(
    *,
    readme_path: Path,
    summary: Dict[str, float],
    year: int,
    source: str,
    intensity_mode: str,
    svg_ref: str,
) -> None:
    ensure_parent(readme_path)
    content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

    updated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    active_days = int(summary["active_days"])
    sessions = int(summary["sessions"])
    active_minutes = int(summary["active_minutes"])
    active_hours = round(active_minutes / 60, 1)
    source_label = {
        "claude": "Claude",
        "codex": "Codex",
        "combined": "AI",
    }.get(source, source.title())
    block = "\n".join(
        [
            MARKER_START,
            f"### The {source_label} build streak, {year}",
            f"{active_days} days showed up, {sessions} sessions made it into the log, and about {active_hours} hours went from \"what if\" to \"it runs on my machine\".",
            "",
            f"`{active_days} active days` `{sessions} detours survived` `{active_hours}h of prompt-fueled shipping`",
            "",
            "<br>",
            "",
            f"![AI coding activity heatmap]({svg_ref})",
            "",
            f"_Last refreshed: {updated_at}_",
            MARKER_END,
        ]
    )

    if MARKER_START in content and MARKER_END in content:
        prefix, rest = content.split(MARKER_START, 1)
        _, suffix = rest.split(MARKER_END, 1)
        new_content = prefix.rstrip() + "\n\n" + block + "\n" + suffix.lstrip("\n")
    else:
        joiner = "\n\n" if content and not content.endswith("\n") else "\n"
        new_content = content + joiner + block + "\n"

    readme_path.write_text(new_content, encoding="utf-8")


def main() -> int:
    args = parse_args()

    tz = resolve_tz(args.tz)
    claude_history = Path(os.path.expanduser(args.claude_history))
    codex_history = Path(os.path.expanduser(args.codex_history))

    events: List[Event] = []
    events.extend(load_claude_events(claude_history, tz))
    events.extend(load_codex_events(codex_history, tz))

    report = build_report(
        events=events,
        source=args.source,
        year=args.year,
        idle_gap_minutes=args.idle_gap_minutes,
        event_window_minutes=args.event_window_minutes,
        tz=tz,
    )

    output_svg = Path(args.output_svg).expanduser()
    ensure_parent(output_svg)
    svg_text = render_svg(
        source=args.source,
        year=args.year,
        day_minutes=report["day_minutes"],
        day_sessions=report["day_sessions"],
        day_events=report["day_events"],
        intensity_mode=args.intensity_mode,
        display_start=report["display_start"],
        display_end=report["display_end"],
        summary=report["summary"],
    )
    output_svg.write_text(svg_text, encoding="utf-8")

    output_json = args.output_json.strip()
    if output_json:
        json_path = Path(output_json).expanduser()
        ensure_parent(json_path)
        payload = {
            "source": report["source"],
            "year": report["year"],
            "intensity_mode": args.intensity_mode,
            "summary": report["summary"],
            "days": report["days"],
            "generated_at": datetime.now().astimezone().isoformat(),
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    readme_target = args.readme.strip()
    if readme_target:
        readme_path = Path(readme_target).expanduser()
        if args.svg_url.strip():
            svg_ref = args.svg_url.strip()
        else:
            try:
                svg_ref = os.path.relpath(output_svg, readme_path.parent)
            except ValueError:
                svg_ref = str(output_svg)
        update_readme_block(
            readme_path=readme_path,
            summary=report["summary"],
            year=args.year,
            source=args.source,
            intensity_mode=args.intensity_mode,
            svg_ref=svg_ref,
        )

    summary = report["summary"]
    print(
        json.dumps(
            {
                "source": args.source,
                "year": args.year,
                "intensity_mode": args.intensity_mode,
                "active_days": int(summary["active_days"]),
                "sessions": int(summary["sessions"]),
                "active_minutes": int(summary["active_minutes"]),
                "events": int(summary["events"]),
                "output_svg": str(output_svg),
                "output_json": output_json or None,
                "readme": readme_target or None,
            },
            ensure_ascii=False,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
