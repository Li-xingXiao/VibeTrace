#!/usr/bin/env python3
"""Generate GitHub-style vibe coding heatmaps from local AI coding history logs."""

from __future__ import annotations

import argparse
import glob
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
TOOL_LABELS = {
    "claude": "Claude",
    "codex": "Codex",
    "codefuse": "CodeFuse",
    "codefuse-codex": "CodeFuse Codex",
    "codefuse-claude": "CodeFuse Claude",
    "codebuddy": "CodeBuddy",
    "opencode": "OpenCode",
    "antigravity": "Antigravity",
    "copilot": "GitHub Copilot",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "continue": "Continue",
    "aider": "Aider",
    "gemini-cli": "Gemini CLI",
    "qwen-code": "Qwen Code",
}
TOOL_COLORS = {
    "claude": "#d97757",
    "codex": "#3b82f6",
    "codefuse": "#5eead4",
    "codefuse-codex": "#2563eb",
    "codefuse-claude": "#f97316",
    "codebuddy": "#22c55e",
    "opencode": "#a78bfa",
    "antigravity": "#f59e0b",
    "copilot": "#10b981",
    "cursor": "#38bdf8",
    "windsurf": "#06b6d4",
    "continue": "#e879f9",
    "aider": "#f43f5e",
    "gemini-cli": "#8b5cf6",
    "qwen-code": "#ef4444",
}
TIMESTAMP_KEYS = (
    "timestamp",
    "ts",
    "time",
    "created_at",
    "createdAt",
    "updated_at",
    "updatedAt",
    "created",
)
SESSION_KEYS = (
    "sessionId",
    "session_id",
    "session",
    "conversationId",
    "conversation_id",
    "chatId",
    "chat_id",
    "threadId",
    "thread_id",
    "id",
)


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
            "Read local AI coding history logs and generate a GitHub-style "
            "vibe coding heatmap."
        )
    )
    parser.add_argument(
        "--source",
        default="combined",
        help="Data source to render: combined or a detected tool id such as claude/codex/opencode.",
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
        "--codefuse-codex-history",
        default="~/.codefuse/engine/codex/history.jsonl",
        help="Path to CodeFuse Codex-engine history JSONL.",
    )
    parser.add_argument(
        "--codefuse-claude-history",
        default="~/.codefuse/engine/cc/history.jsonl",
        help="Path to CodeFuse Claude-engine history JSONL.",
    )
    parser.add_argument(
        "--codefuse-projects-history",
        default="~/.codefuse/projects/**/*.jsonl",
        help="Glob for CodeFuse project JSONL transcripts.",
    )
    parser.add_argument(
        "--opencode-history",
        default="~/.local/share/opencode/**/*.json*",
        help="Glob for OpenCode JSON/JSONL session data.",
    )
    parser.add_argument(
        "--extra-history",
        action="append",
        default=[],
        metavar="TOOL=PATH_OR_GLOB",
        help="Add a generic JSON/JSONL history source, for example cursor=~/.cursor/history.jsonl.",
    )
    parser.add_argument(
        "--output-svg",
        default="vibe-heatmap.svg",
        help="Output SVG path.",
    )
    parser.add_argument(
        "--output-tools-svg",
        default="",
        help="Optional output SVG path for overall vibe tool usage share.",
    )
    parser.add_argument(
        "--output-recent-tools-svg",
        default="",
        help="Optional output SVG path for recent vibe tool usage share.",
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
        "--tools-svg-url",
        default="",
        help="Tool usage SVG URL/path used in README block.",
    )
    parser.add_argument(
        "--recent-tools-svg-url",
        default="",
        help="Recent tool usage SVG URL/path used in README block.",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=7,
        help="Number of days used for the recent tool usage card.",
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


def parse_datetime_value(raw: object, tz) -> Optional[datetime]:
    ts_raw = parse_numeric_timestamp(raw)
    if ts_raw is not None:
        return to_datetime(ts_raw, tz)

    if not isinstance(raw, str):
        return None

    value = raw.strip()
    if not value:
        return None

    iso_value = value
    if iso_value.endswith("Z"):
        iso_value = iso_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.astimezone(tz)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def tool_label(source: str) -> str:
    return TOOL_LABELS.get(source, source.replace("-", " ").replace("_", " ").title())


def tool_color(source: str) -> str:
    if source in TOOL_COLORS:
        return TOOL_COLORS[source]
    colors = list(TOOL_COLORS.values())
    return colors[sum(ord(ch) for ch in source) % len(colors)]


def expand_history_paths(pattern: str) -> List[Path]:
    expanded = os.path.expanduser(pattern)
    if any(ch in expanded for ch in "*?["):
        return [Path(path) for path in sorted(glob.glob(expanded, recursive=True))]
    return [Path(expanded)]


def first_present(payload: Dict[str, object], keys: Sequence[str]) -> Optional[object]:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def event_from_payload(
    payload: object,
    *,
    source: str,
    tz,
    fallback_session: str,
) -> Optional[Event]:
    if not isinstance(payload, dict):
        return None

    ts = parse_datetime_value(first_present(payload, TIMESTAMP_KEYS), tz)
    if ts is None:
        return None

    session_raw = first_present(payload, SESSION_KEYS)
    session_id = str(session_raw or fallback_session or "unknown")
    return Event(source=source, ts=ts, session_key=f"{source}:{session_id}")


def load_json_events(path: Path, tz, source: str) -> List[Event]:
    events: List[Event] = []
    if not path.exists() or not path.is_file():
        return events

    fallback_session = path.stem
    suffix = path.suffix.lower()

    if suffix in {".jsonl", ".log"}:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = event_from_payload(
                    payload,
                    source=source,
                    tz=tz,
                    fallback_session=fallback_session,
                )
                if event is not None:
                    events.append(event)
        return events

    if suffix != ".json":
        return events

    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return events

    candidates: List[object]
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        list_values = [value for value in payload.values() if isinstance(value, list)]
        candidates = [payload]
        for value in list_values:
            candidates.extend(value)
    else:
        candidates = []

    for candidate in candidates:
        event = event_from_payload(
            candidate,
            source=source,
            tz=tz,
            fallback_session=fallback_session,
        )
        if event is not None:
            events.append(event)
    return events


def load_generic_history(pattern: str, tz, source: str) -> List[Event]:
    events: List[Event] = []
    for path in expand_history_paths(pattern):
        events.extend(load_json_events(path, tz, source))
    return events


def load_codex_events(path: Path, tz, source: str = "codex") -> List[Event]:
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
            events.append(Event(source=source, ts=to_datetime(ts_raw, tz), session_key=f"{source}:{session_id}"))
    return events


def load_claude_events(path: Path, tz, source: str = "claude") -> List[Event]:
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

            ts = parse_datetime_value(payload.get("timestamp") or payload.get("ts"), tz)
            if ts is None:
                continue

            session_id = str(payload.get("sessionId") or payload.get("session_id") or "unknown")
            events.append(Event(source=source, ts=ts, session_key=f"{source}:{session_id}"))
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


def visible_end_for_year(year: int, tz) -> date:
    today = datetime.now(tz).date()
    if year < today.year:
        return date(year, 12, 31)
    if year == today.year:
        return min(date(year, 12, 31), today)
    return date(year, 1, 1) - timedelta(days=1)


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
    visible_end: date,
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
        visible_day = in_year and current <= visible_end
        minutes = day_minutes.get(current, 0.0) if visible_day else 0.0
        sessions = day_sessions.get(current, 0) if visible_day else 0
        events = day_events.get(current, 0) if visible_day else 0

        if intensity_mode == "sessions":
            intensity_value = float(sessions)
        elif intensity_mode == "events":
            intensity_value = float(events)
        else:
            intensity_value = minutes

        level = to_level(intensity_value, thresholds)
        fill = PALETTE[level] if in_year else OUTSIDE_YEAR_COLOR

        if visible_day:
            tooltip = (
                f"{current.isoformat()}: {int(round(minutes))} active minutes, "
                f"{sessions} sessions, {events} events"
            )
        elif in_year:
            tooltip = "No vibe record yet"
        else:
            tooltip = f"{current.isoformat()}: out of range"
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


def format_duration(minutes: float) -> str:
    total = int(round(minutes))
    hours = total // 60
    mins = total % 60
    if hours and mins:
        return f"{hours} hr{'s' if hours != 1 else ''} {mins} min{'s' if mins != 1 else ''}"
    if hours:
        return f"{hours} hr{'s' if hours != 1 else ''}"
    return f"{mins} min{'s' if mins != 1 else ''}"


def summarize_tool_period(
    *,
    events: Sequence[Event],
    sessions: Sequence[SessionWindow],
    event_window: timedelta,
    period_start: datetime,
    period_end: datetime,
) -> List[Dict[str, object]]:
    intervals_by_source: Dict[str, List[Tuple[datetime, datetime]]] = defaultdict(list)
    event_counts: Dict[str, int] = defaultdict(int)
    session_counts: Dict[str, int] = defaultdict(int)

    for event in events:
        event_end = event.ts + event_window
        if event_end <= period_start or event.ts >= period_end:
            continue
        intervals_by_source[event.source].append((event.ts, event_end))
        if period_start <= event.ts < period_end:
            event_counts[event.source] += 1

    for session in sessions:
        if period_start <= session.start < period_end:
            session_counts[session.source] += 1

    rows: List[Dict[str, object]] = []
    sources = set(intervals_by_source) | set(event_counts) | set(session_counts)
    for source in sources:
        minutes = 0.0
        for start, end in merge_intervals(intervals_by_source[source]):
            clipped_start = max(start, period_start)
            clipped_end = min(end, period_end)
            if clipped_end > clipped_start:
                minutes += (clipped_end - clipped_start).total_seconds() / 60.0

        rows.append(
            {
                "source": source,
                "label": tool_label(source),
                "color": tool_color(source),
                "active_minutes": round(minutes, 2),
                "sessions": int(session_counts[source]),
                "events": int(event_counts[source]),
            }
        )

    total_minutes = sum(float(row["active_minutes"]) for row in rows)
    for row in rows:
        row["percent"] = round((float(row["active_minutes"]) / total_minutes) * 100, 2) if total_minutes else 0.0

    rows.sort(
        key=lambda row: (
            float(row["active_minutes"]),
            int(row["sessions"]),
            int(row["events"]),
            str(row["label"]),
        ),
        reverse=True,
    )
    return [row for row in rows if float(row["active_minutes"]) > 0 or int(row["events"]) > 0]


def build_tool_stats(
    *,
    events: Sequence[Event],
    source: str,
    year: int,
    idle_gap_minutes: float,
    event_window_minutes: float,
    recent_days: int,
    tz,
) -> Dict[str, object]:
    selected = filter_events(events, source)
    sessions = build_sessions(selected, timedelta(minutes=idle_gap_minutes))
    event_window = timedelta(minutes=event_window_minutes)
    year_start = datetime(year, 1, 1, tzinfo=tz)
    year_end_exclusive = datetime(year + 1, 1, 1, tzinfo=tz)

    visible_end = visible_end_for_year(year, tz)

    recent_end = datetime.combine(visible_end + timedelta(days=1), time.min, tzinfo=tz)
    recent_start = max(year_start, recent_end - timedelta(days=max(recent_days, 1)))

    return {
        "overall": summarize_tool_period(
            events=selected,
            sessions=sessions,
            event_window=event_window,
            period_start=year_start,
            period_end=year_end_exclusive,
        ),
        "recent": summarize_tool_period(
            events=selected,
            sessions=sessions,
            event_window=event_window,
            period_start=recent_start,
            period_end=recent_end,
        ),
        "recent_days": max(recent_days, 1),
        "recent_start": recent_start.date().isoformat(),
        "recent_end": visible_end.isoformat(),
    }


def render_tool_stats_svg(
    *,
    title: str,
    subtitle: str,
    stats: Sequence[Dict[str, object]],
    empty_text: str,
    clip_id: str,
) -> str:
    display_stats = list(stats)
    if len(display_stats) > 6:
        top_stats = display_stats[:5]
        remaining = display_stats[5:]
        other_minutes = sum(float(stat["active_minutes"]) for stat in remaining)
        other_percent = sum(float(stat["percent"]) for stat in remaining)
        other_sessions = sum(int(stat["sessions"]) for stat in remaining)
        other_events = sum(int(stat["events"]) for stat in remaining)
        display_stats = top_stats + [
            {
                "source": "other",
                "label": "Other tools",
                "color": "#8b949e",
                "active_minutes": round(other_minutes, 2),
                "sessions": other_sessions,
                "events": other_events,
                "percent": round(other_percent, 2),
            }
        ]

    width = 560
    rows = max(1, len(display_stats))
    height = 116 + rows * 28
    bar_x = 32
    bar_y = 58
    bar_width = width - 64
    bar_height = 10

    segments: List[str] = []
    cursor = bar_x
    for idx, stat in enumerate(display_stats):
        percent = float(stat["percent"])
        segment_width = bar_width * percent / 100.0
        if idx == len(display_stats) - 1:
            segment_width = max(0.0, bar_x + bar_width - cursor)
        if segment_width <= 0:
            continue
        segments.append(
            f'<rect x="{cursor:.2f}" y="{bar_y}" width="{segment_width:.2f}" height="{bar_height}" fill="{stat["color"]}" clip-path="url(#{clip_id})" />'
        )
        cursor += segment_width

    legend_nodes: List[str] = []
    if display_stats:
        for idx, stat in enumerate(display_stats):
            x = 42
            y = 96 + idx * 28
            label = str(stat["label"])
            duration = format_duration(float(stat["active_minutes"]))
            percent = float(stat["percent"])
            text = f"{label} - {duration} ({percent:.1f}%)"
            legend_nodes.append(
                "".join(
                    [
                        f'<circle cx="{x}" cy="{y}" r="6" fill="{stat["color"]}" />',
                        f'<text x="{x + 16}" y="{y + 5}" fill="#9aa7b6" font-size="13" font-family="system-ui, sans-serif">{escape(text)}</text>',
                    ]
                )
            )
    else:
        legend_nodes.append(
            f'<text x="32" y="96" fill="#9aa7b6" font-size="13" font-family="system-ui, sans-serif">{escape(empty_text)}</text>'
        )

    segment_nodes = "".join(segments)
    legend = "".join(legend_nodes)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <defs>
    <clipPath id="{clip_id}">
      <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="8" ry="8" />
    </clipPath>
  </defs>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="#0d1117" stroke="#24493e" stroke-width="2" rx="8" />
  <text x="32" y="34" fill="#5eead4" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{escape(title)}</text>
  <text x="32" y="50" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">{escape(subtitle)}</text>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" fill="#30363d" rx="8" ry="8" />
  {segment_nodes}
  {legend}
</svg>
"""


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
    visible_end = visible_end_for_year(year, tz)

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
        "visible_end": visible_end,
        "days": day_rows,
    }


def update_readme_block(
    *,
    readme_path: Path,
    summary: Dict[str, float],
    tool_stats: Dict[str, object],
    year: int,
    source: str,
    intensity_mode: str,
    svg_ref: str,
    tools_svg_ref: str,
    recent_tools_svg_ref: str,
) -> None:
    ensure_parent(readme_path)
    content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

    updated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    active_days = int(summary["active_days"])
    sessions = int(summary["sessions"])
    active_minutes = int(summary["active_minutes"])
    active_hours = round(active_minutes / 60, 1)
    source_label = "AI" if source == "combined" else tool_label(source)
    overall_tools = tool_stats.get("overall", [])
    tool_line = ""
    if isinstance(overall_tools, list) and overall_tools:
        top_tools = overall_tools[:3]
        tool_line = "Current vibe bench: " + ", ".join(
            f"{item['label']} {float(item['percent']):.1f}%" for item in top_tools
        ) + "."

    block_lines = [
        MARKER_START,
        f"### The {source_label} build streak, {year}",
        f"{active_days} active days, {sessions} sessions, and about {active_hours} hours of \"wait, try that again\" turning into shipped code.",
    ]
    if tool_line:
        block_lines.extend(["", tool_line])
    block_lines.extend(
        [
            "",
            f"`{active_days} active days` `{sessions} detours survived` `{active_hours}h of prompt-fueled shipping`",
            "",
            "<br>",
            "",
            f"![AI coding activity heatmap]({svg_ref})",
        ]
    )
    if tools_svg_ref and recent_tools_svg_ref:
        block_lines.extend(
            [
                "",
                '<p align="center">',
                f'  <img src="{tools_svg_ref}" alt="Vibe coding tool usage mix" width="49%">',
                f'  <img src="{recent_tools_svg_ref}" alt="Recent vibe coding tool usage" width="49%">',
                "</p>",
            ]
        )
    elif tools_svg_ref:
        block_lines.extend(["", f'<img src="{tools_svg_ref}" alt="Vibe coding tool usage mix" width="58%">'])
    elif recent_tools_svg_ref:
        block_lines.extend(["", f'<img src="{recent_tools_svg_ref}" alt="Recent vibe coding tool usage" width="58%">'])
    block_lines.extend(["", f"_Last refreshed: {updated_at}_", MARKER_END])
    block = "\n".join(block_lines)

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
    codefuse_codex_history = Path(os.path.expanduser(args.codefuse_codex_history))
    codefuse_claude_history = Path(os.path.expanduser(args.codefuse_claude_history))

    events: List[Event] = []
    events.extend(load_claude_events(claude_history, tz))
    events.extend(load_codex_events(codex_history, tz))
    events.extend(load_codex_events(codefuse_codex_history, tz, source="codefuse-codex"))
    events.extend(load_claude_events(codefuse_claude_history, tz, source="codefuse-claude"))
    events.extend(load_generic_history(args.codefuse_projects_history, tz, source="codefuse"))
    events.extend(load_generic_history(args.opencode_history, tz, source="opencode"))

    for item in args.extra_history:
        if "=" not in item:
            raise ValueError(f"--extra-history must be TOOL=PATH_OR_GLOB, got: {item}")
        extra_source, extra_pattern = item.split("=", 1)
        extra_source = extra_source.strip().lower()
        extra_pattern = extra_pattern.strip()
        if not extra_source or not extra_pattern:
            raise ValueError(f"--extra-history must be TOOL=PATH_OR_GLOB, got: {item}")
        events.extend(load_generic_history(extra_pattern, tz, source=extra_source))

    report = build_report(
        events=events,
        source=args.source,
        year=args.year,
        idle_gap_minutes=args.idle_gap_minutes,
        event_window_minutes=args.event_window_minutes,
        tz=tz,
    )
    tool_stats = build_tool_stats(
        events=events,
        source=args.source,
        year=args.year,
        idle_gap_minutes=args.idle_gap_minutes,
        event_window_minutes=args.event_window_minutes,
        recent_days=args.recent_days,
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
        visible_end=report["visible_end"],
        summary=report["summary"],
    )
    output_svg.write_text(svg_text, encoding="utf-8")

    output_tools_svg = args.output_tools_svg.strip()
    if output_tools_svg:
        tools_svg_path = Path(output_tools_svg).expanduser()
        ensure_parent(tools_svg_path)
        tools_svg_path.write_text(
            render_tool_stats_svg(
                title=f"Vibe Tool Mix ({args.year})",
                subtitle="Estimated active time by detected AI coding tool",
                stats=tool_stats["overall"],
                empty_text="No tool activity detected for this year yet.",
                clip_id="vibe-tool-mix-bar",
            ),
            encoding="utf-8",
        )

    output_recent_tools_svg = args.output_recent_tools_svg.strip()
    if output_recent_tools_svg:
        recent_tools_svg_path = Path(output_recent_tools_svg).expanduser()
        ensure_parent(recent_tools_svg_path)
        recent_tools_svg_path.write_text(
            render_tool_stats_svg(
                title=f"Vibe Tools (last {int(tool_stats['recent_days'])} days)",
                subtitle=f"{tool_stats['recent_start']} to {tool_stats['recent_end']}",
                stats=tool_stats["recent"],
                empty_text="No recent tool activity detected yet.",
                clip_id="vibe-tool-recent-bar",
            ),
            encoding="utf-8",
        )

    output_json = args.output_json.strip()
    if output_json:
        json_path = Path(output_json).expanduser()
        ensure_parent(json_path)
        payload = {
            "source": report["source"],
            "year": report["year"],
            "intensity_mode": args.intensity_mode,
            "summary": report["summary"],
            "tool_stats": tool_stats,
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

        tools_svg_ref = args.tools_svg_url.strip()
        if not tools_svg_ref and output_tools_svg:
            try:
                tools_svg_ref = os.path.relpath(Path(output_tools_svg).expanduser(), readme_path.parent)
            except ValueError:
                tools_svg_ref = output_tools_svg

        recent_tools_svg_ref = args.recent_tools_svg_url.strip()
        if not recent_tools_svg_ref and output_recent_tools_svg:
            try:
                recent_tools_svg_ref = os.path.relpath(Path(output_recent_tools_svg).expanduser(), readme_path.parent)
            except ValueError:
                recent_tools_svg_ref = output_recent_tools_svg

        update_readme_block(
            readme_path=readme_path,
            summary=report["summary"],
            tool_stats=tool_stats,
            year=args.year,
            source=args.source,
            intensity_mode=args.intensity_mode,
            svg_ref=svg_ref,
            tools_svg_ref=tools_svg_ref,
            recent_tools_svg_ref=recent_tools_svg_ref,
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
                "output_tools_svg": output_tools_svg or None,
                "output_recent_tools_svg": output_recent_tools_svg or None,
                "output_json": output_json or None,
                "readme": readme_target or None,
            },
            ensure_ascii=False,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
