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
TOOL_ICON_PATHS = {
    "claude": "M6 0C6.5 3.8 8.2 5.5 12 6C8.2 6.5 6.5 8.2 6 12C5.5 8.2 3.8 6.5 0 6C3.8 5.5 5.5 3.8 6 0Z",
    "codex": "M6 .7L10.6 3.35V8.65L6 11.3L1.4 8.65V3.35Z",
    "codefuse": "M7.5.5L3 6.5H6L4.5 11.5L9 5.5H6Z",
    "codefuse-codex": "M6 .5L11 3V9L6 11.5L1 9V3Z",
    "codefuse-claude": "M6 .5L7.6 4.1L11.5 4.7L8.7 7.3L9.4 11.2L6 9.4L2.6 11.2L3.3 7.3L.5 4.7L4.4 4.1Z",
    "codebuddy": "M6 .5L11.5 2.5V6.5C11.5 9.5 9 11 6 11.5C3 11 .5 9.5.5 6.5V2.5Z",
    "opencode": "M6 .5L11.2 3.8L9.8 9.8L2.2 9.8L.8 3.8Z",
    "antigravity": "M6 0L11 10H7.5V12H4.5V10H1Z",
    "copilot": "M2 2C2 1 3 0 4.5 0H7.5C9 0 10 1 10 2V4.5L12 6.5L10 7.5V9C10 10 9 11 7.5 11H4.5C3 11 2 10 2 9V7.5L0 6.5L2 4.5Z",
    "cursor": "M2 .5V11L5 8L7.5 11.5L9 10.5L6.5 7L10.5 7Z",
    "windsurf": "M0 8C1.5 4 3 4 4.5 6S7.5 8 9 6C10.5 4 11 4 12 6V8C11 10 10.5 10 9 8S6 6 4.5 8C3 10 1.5 10 0 8Z",
    "continue": "M1.5 .5L10.5 6L1.5 11.5Z",
    "aider": "M9.5.5L11.5 2.5L4.5 9.5C3.5 10.5 2 11 1 10.5L.5 10L1.5 9C2 9 3 8.5 3.5 8L10.5 1Z",
    "gemini-cli": "M3 0C3.3 2.5 4.5 3.7 7 4C4.5 4.3 3.3 5.5 3 8C2.7 5.5 1.5 4.3 0 4C1.5 3.7 2.7 2.5 3 0ZM9 4C9.2 5.5 10 6.3 12 6.5C10 6.7 9.2 7.5 9 9C8.8 7.5 8 6.7 6 6.5C8 6.3 8.8 5.5 9 4Z",
    "qwen-code": "M6 .5A5.5 5.5 0 1 0 10 9L12 11.5H10L8.5 9.5A5.5 5.5 0 0 0 6 .5ZM6 3A3 3 0 1 1 6 9A3 3 0 0 1 6 3Z",
}
_BG_RGB = (13, 17, 23)


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _generate_palette(base_hex: str) -> List[str]:
    r, g, b = _hex_to_rgb(base_hex)
    fractions = [0.08, 0.22, 0.42, 0.65, 1.0]
    return [
        _rgb_to_hex(
            int(_BG_RGB[0] + (r - _BG_RGB[0]) * f),
            int(_BG_RGB[1] + (g - _BG_RGB[1]) * f),
            int(_BG_RGB[2] + (b - _BG_RGB[2]) * f),
        )
        for f in fractions
    ]


TOOL_PALETTES = {tool: _generate_palette(color) for tool, color in TOOL_COLORS.items()}
MODEL_LABELS = {
    "claude-opus-4-6": "Opus 4.6",
    "opus-4.6": "Opus 4.6",
    "claude-opus-4-5-20250918": "Opus 4.5",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "glm-5.1": "GLM 5.1",
    "glm-5": "GLM 5",
    "glm-5-turbo": "GLM 5 Turbo",
    "glm-4.7": "GLM 4.7",
}
MODEL_COLORS = {
    "claude-opus-4-6": "#d97757",
    "opus-4.6": "#d97757",
    "claude-opus-4-5-20250918": "#c2664a",
    "claude-sonnet-4-5-20250929": "#f0b27a",
    "claude-sonnet-4-6": "#e8a065",
    "claude-haiku-4-5-20251001": "#fcd9a8",
    "glm-5.1": "#5eead4",
    "glm-5": "#2dd4bf",
    "glm-5-turbo": "#14b8a6",
    "glm-4.7": "#0d9488",
}
_VIBE_PERSONALITIES = [
    (range(5, 12), "\U0001f305", "Early Bird"),
    (range(12, 18), "\u2600\ufe0f", "Afternoon Hacker"),
    (range(18, 24), "\U0001f319", "Night Owl"),
    (range(0, 5), "\U0001f987", "Midnight Hacker"),
]
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
    parser.add_argument(
        "--stats-cache",
        action="append",
        default=[],
        help="Path to stats-cache.json (can be repeated). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--output-token-svg",
        default="",
        help="Optional output SVG path for token economy card.",
    )
    parser.add_argument(
        "--token-svg-url",
        default="",
        help="Token economy SVG URL/path used in README block.",
    )
    parser.add_argument(
        "--output-scorecard-svg",
        default="",
        help="Optional output SVG path for vibe scorecard.",
    )
    parser.add_argument(
        "--scorecard-svg-url",
        default="",
        help="Vibe scorecard SVG URL/path used in README block.",
    )
    parser.add_argument(
        "--output-badges-svg",
        default="",
        help="Optional output SVG path for coding achievement badges.",
    )
    parser.add_argument(
        "--badges-svg-url",
        default="",
        help="Badges SVG URL/path used in README block.",
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


def tool_palette(source: str) -> List[str]:
    if source in TOOL_PALETTES:
        return TOOL_PALETTES[source]
    return _generate_palette(tool_color(source))


def tool_icon_svg(source: str, cx: float, cy: float, size: float, color: str) -> str:
    path_data = TOOL_ICON_PATHS.get(source)
    if not path_data:
        return f'<circle cx="{cx}" cy="{cy}" r="{size / 2}" fill="{color}" />'
    half = size / 2
    scale = size / 12
    x = cx - half
    y = cy - half
    fill_rule = ' fill-rule="evenodd"' if source == "qwen-code" else ""
    return (
        f'<g transform="translate({x},{y}) scale({scale})">'
        f'<path d="{path_data}" fill="{color}"{fill_rule}/></g>'
    )


def model_label(name: str) -> str:
    if name in MODEL_LABELS:
        return MODEL_LABELS[name]
    return name.replace("-", " ").replace("_", " ").title()


def model_color(name: str) -> str:
    if name in MODEL_COLORS:
        return MODEL_COLORS[name]
    colors = list(MODEL_COLORS.values())
    return colors[sum(ord(ch) for ch in name) % len(colors)] if colors else "#8b949e"


def format_tokens(count: float) -> str:
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(int(count))


def format_big_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def load_stats_caches(paths: Sequence[str]) -> Dict[str, object]:
    merged: Dict[str, object] = {
        "total_messages": 0,
        "total_sessions": 0,
        "total_tool_calls": 0,
        "model_usage": {},
        "hour_counts": defaultdict(int),
        "longest_session_ms": 0,
        "longest_session_messages": 0,
    }
    for raw_path in paths:
        p = Path(os.path.expanduser(raw_path))
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        merged["total_messages"] = int(merged["total_messages"]) + int(data.get("totalMessages", 0))
        merged["total_sessions"] = int(merged["total_sessions"]) + int(data.get("totalSessions", 0))

        for entry in data.get("dailyActivity", []):
            merged["total_tool_calls"] = int(merged["total_tool_calls"]) + int(entry.get("toolCallCount", 0))

        for model, usage in data.get("modelUsage", {}).items():
            existing = merged["model_usage"].get(model, {})
            for key in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "webSearchRequests"):
                existing[key] = existing.get(key, 0) + int(usage.get(key, 0))
            merged["model_usage"][model] = existing

        for hour, count in data.get("hourCounts", {}).items():
            merged["hour_counts"][int(hour)] += int(count)

        ls = data.get("longestSession", {})
        dur = int(ls.get("duration", 0))
        if dur > int(merged["longest_session_ms"]):
            merged["longest_session_ms"] = dur
            merged["longest_session_messages"] = int(ls.get("messageCount", 0))

    return merged


def compute_longest_streak(day_minutes: Dict[date, float]) -> int:
    active = sorted(d for d, m in day_minutes.items() if m > 0)
    if not active:
        return 0
    best = 1
    current = 1
    for i in range(1, len(active)):
        if (active[i] - active[i - 1]).days == 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def compute_vibe_personality(hour_counts: Dict[int, int]) -> Tuple[str, str, int]:
    if not hour_counts:
        return ("\u2728", "Vibe Explorer", 12)
    peak_hour = max(hour_counts, key=lambda h: hour_counts[h])
    for hours, emoji, title in _VIBE_PERSONALITIES:
        if peak_hour in hours:
            return (emoji, title, peak_hour)
    return ("\U0001f319", "Night Owl", peak_hour)


def _sparkline_data(
    events: Sequence[Event],
    period_start: datetime,
    period_end: datetime,
    bucket_days: int = 1,
) -> Dict[str, List[int]]:
    total_days = max(1, (period_end.date() - period_start.date()).days)
    n_buckets = max(1, math.ceil(total_days / bucket_days))
    counts: Dict[str, List[int]] = defaultdict(lambda: [0] * n_buckets)
    for event in events:
        if event.ts < period_start or event.ts >= period_end:
            continue
        day_offset = (event.ts.date() - period_start.date()).days
        bucket = min(day_offset // bucket_days, n_buckets - 1)
        counts[event.source][bucket] += 1
    return dict(counts)


def _render_sparkline(
    data: List[int], x: float, y: float, w: float, h: float, color: str,
) -> str:
    if not data or max(data) == 0:
        return ""
    max_val = max(data)
    n = len(data)
    pts = []
    for i, v in enumerate(data):
        px = x + (i / max(1, n - 1)) * w
        py = y + h - (v / max_val) * h * 0.85 - 1
        pts.append(f"{px:.1f},{py:.1f}")
    poly_str = " ".join(pts)
    fill_pts = f"{x:.1f},{y + h:.1f} " + poly_str + f" {x + w:.1f},{y + h:.1f}"
    return (
        f'<polyline points="{fill_pts}" fill="{color}" fill-opacity="0.1" stroke="none" />'
        f'<polyline points="{poly_str}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />'
    )


def format_duration_compact(minutes: float) -> str:
    total = int(round(minutes))
    hours = total // 60
    mins = total % 60
    if hours and mins:
        return f"{hours}h {mins:02d}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


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
    day_dominant_source: Dict[date, str],
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
        dominant = day_dominant_source.get(current)
        if dominant:
            pal = tool_palette(dominant)
        elif source != "combined":
            pal = tool_palette(source)
        else:
            pal = PALETTE
        fill = pal[level] if in_year else OUTSIDE_YEAR_COLOR

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

    legend_y = height - 24
    legend_nodes: List[str] = []

    active_tools = sorted(set(day_dominant_source.values())) if day_dominant_source else []
    is_combined = source == "combined" and len(active_tools) > 1

    if is_combined:
        cursor_x = 16.0
        for src in active_tools:
            color = tool_color(src)
            label = tool_label(src)
            legend_nodes.append(tool_icon_svg(src, cursor_x + 5, legend_y - 3, 10, color))
            cursor_x += 14
            legend_nodes.append(
                f'<text x="{cursor_x}" y="{legend_y}" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">{escape(label)}</text>'
            )
            cursor_x += len(label) * 6 + 10
    else:
        legend_x = width - 220
        pal = tool_palette(source) if source != "combined" else PALETTE
        legend_nodes.append(
            f'<text x="{legend_x}" y="{legend_y}" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">Less</text>'
        )
        for idx, color in enumerate(pal):
            x = legend_x + 28 + idx * (cell + 5)
            legend_nodes.append(
                f'<rect x="{x}" y="{legend_y - 9}" width="{cell}" height="{cell}" rx="2" ry="2" fill="{color}" />'
            )
        legend_nodes.append(
            f'<text x="{legend_x + 28 + len(pal) * (cell + 5) + 4}" y="{legend_y}" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">More ({INTENSITY_LABELS[intensity_mode]})</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Vibe coding heatmap">
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="#0d1117" stroke="#24493e" stroke-width="2" rx="10" />
  <text x="16" y="28" fill="#e6edf3" font-size="18" font-family="system-ui, sans-serif">{escape(title)}</text>
  {''.join(month_labels)}
  {''.join(day_label_nodes)}
  {''.join(cells)}
  {''.join(legend_nodes)}
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

    overall = summarize_tool_period(
        events=selected,
        sessions=sessions,
        event_window=event_window,
        period_start=year_start,
        period_end=year_end_exclusive,
    )
    recent = summarize_tool_period(
        events=selected,
        sessions=sessions,
        event_window=event_window,
        period_start=recent_start,
        period_end=recent_end,
    )

    overall_sparks = _sparkline_data(selected, year_start, year_end_exclusive, bucket_days=7)
    recent_sparks = _sparkline_data(selected, recent_start, recent_end, bucket_days=1)

    for row in overall:
        row["sparkline"] = overall_sparks.get(str(row["source"]), [])
    for row in recent:
        row["sparkline"] = recent_sparks.get(str(row["source"]), [])

    return {
        "overall": overall,
        "recent": recent,
        "recent_days": max(recent_days, 1),
        "recent_start": recent_start.date().isoformat(),
        "recent_end": visible_end.isoformat(),
    }


_CARD_MIN_HEIGHT = 300


def render_tool_stats_svg(
    *,
    title: str,
    subtitle: str,
    stats: Sequence[Dict[str, object]],
    empty_text: str,
    clip_id: str,
) -> str:
    display_stats = list(stats)
    if len(display_stats) > 8:
        top = display_stats[:7]
        rest = display_stats[7:]
        other_minutes = sum(float(s["active_minutes"]) for s in rest)
        other_percent = sum(float(s["percent"]) for s in rest)
        other_sessions = sum(int(s["sessions"]) for s in rest)
        other_events = sum(int(s["events"]) for s in rest)
        display_stats = top + [
            {
                "source": "other",
                "label": "Other tools",
                "color": "#8b949e",
                "active_minutes": round(other_minutes, 2),
                "sessions": other_sessions,
                "events": other_events,
                "percent": round(other_percent, 2),
                "sparkline": [],
            }
        ]

    width = 560
    bar_x = 32
    bar_y = 68
    bar_w = width - 64
    bar_h = 10

    use_two_cols = len(display_stats) > 2
    if use_two_cols:
        n_per_col = math.ceil(len(display_stats) / 2)
        col_w = 240
        col_gap = 28
    else:
        n_per_col = max(1, len(display_stats))
        col_w = width - 64
        col_gap = 0

    block_h = 44
    legend_y = bar_y + bar_h + 24
    grid_h = n_per_col * block_h
    height = max(legend_y + grid_h + 12, _CARD_MIN_HEIGHT)

    segments: List[str] = []
    cx = float(bar_x)
    for idx, stat in enumerate(display_stats):
        pct = float(stat["percent"])
        sw = bar_w * pct / 100.0
        if idx == len(display_stats) - 1:
            sw = max(0.0, bar_x + bar_w - cx)
        if sw <= 0:
            continue
        segments.append(
            f'<rect x="{cx:.2f}" y="{bar_y}" width="{sw:.2f}" height="{bar_h}" '
            f'fill="{stat["color"]}" clip-path="url(#{clip_id})" />'
        )
        cx += sw

    legend_nodes: List[str] = []
    if display_stats:
        for idx, stat in enumerate(display_stats):
            if use_two_cols:
                col = idx // n_per_col
                row = idx % n_per_col
            else:
                col = 0
                row = idx

            x_base = 32 + col * (col_w + col_gap)
            y_base = legend_y + row * block_h

            src = str(stat.get("source", ""))
            color = str(stat["color"])
            label = str(stat["label"])
            pct = float(stat["percent"])
            dur = format_duration_compact(float(stat["active_minutes"]))
            sparkline = list(stat.get("sparkline") or [])

            legend_nodes.append(tool_icon_svg(src, x_base + 6, y_base + 4, 10, color))

            legend_nodes.append(
                f'<text x="{x_base + 16}" y="{y_base + 8}" fill="#c9d1d9" font-size="12" '
                f'font-weight="600" font-family="system-ui, sans-serif">{escape(label)}</text>'
            )
            legend_nodes.append(
                f'<text x="{x_base + col_w}" y="{y_base + 8}" fill="#8b949e" font-size="11" '
                f'font-family="system-ui, sans-serif" text-anchor="end">'
                f'{pct:.0f}%  {dur}</text>'
            )

            if sparkline and len(sparkline) > 1:
                sp_x = x_base
                sp_y = y_base + 16
                sp_w = col_w - 4
                sp_h = 20
                legend_nodes.append(_render_sparkline(sparkline, sp_x, sp_y, sp_w, sp_h, color))
    else:
        legend_nodes.append(
            f'<text x="32" y="{legend_y + 8}" fill="#9aa7b6" font-size="13" '
            f'font-family="system-ui, sans-serif">{escape(empty_text)}</text>'
        )

    segment_nodes = "".join(segments)
    legend = "".join(legend_nodes)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <defs>
    <clipPath id="{clip_id}">
      <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="8" ry="8" />
    </clipPath>
  </defs>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="#0d1117" stroke="#24493e" stroke-width="2" rx="8" />
  <text x="32" y="32" fill="#5eead4" font-size="18" font-weight="700" font-family="system-ui, sans-serif">{escape(title)}</text>
  <text x="32" y="50" fill="#8b949e" font-size="11" font-family="system-ui, sans-serif">{escape(subtitle)}</text>
  <text x="{width - 32}" y="50" fill="#8b949e" font-size="11" font-family="system-ui, sans-serif" text-anchor="end">100%</text>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="#30363d" rx="8" ry="8" />
  {segment_nodes}
  {legend}
</svg>
"""


def render_token_stats_svg(
    *,
    title: str,
    subtitle: str,
    model_usage: Dict[str, Dict[str, int]],
    cache_hit_pct: float,
    total_input: int,
    total_output: int,
    clip_id: str,
) -> str:
    rows: List[Dict[str, object]] = []
    for model, usage in model_usage.items():
        total = usage.get("inputTokens", 0) + usage.get("outputTokens", 0)
        rows.append({
            "model": model,
            "label": model_label(model),
            "color": model_color(model),
            "tokens": total,
        })
    rows.sort(key=lambda r: int(r["tokens"]), reverse=True)
    grand_total = sum(int(r["tokens"]) for r in rows)

    for r in rows:
        r["percent"] = round(int(r["tokens"]) / grand_total * 100, 1) if grand_total else 0.0

    display = rows[:5]
    if len(rows) > 6:
        others = rows[5:]
        display.append({
            "model": "other",
            "label": "Other models",
            "color": "#8b949e",
            "tokens": sum(int(r["tokens"]) for r in others),
            "percent": round(sum(float(r["percent"]) for r in others), 1),
        })
    elif len(rows) == 6:
        display = rows

    width = 560
    n_rows = max(1, len(display))
    footer_y = 96 + n_rows * 28 + 8
    height = max(footer_y + 28, _CARD_MIN_HEIGHT)
    bar_x = 32
    bar_y = 58
    bar_w = width - 64
    bar_h = 10

    segments: List[str] = []
    cx = float(bar_x)
    for idx, r in enumerate(display):
        pct = float(r["percent"])
        sw = bar_w * pct / 100.0
        if idx == len(display) - 1:
            sw = max(0.0, bar_x + bar_w - cx)
        if sw <= 0:
            continue
        segments.append(
            f'<rect x="{cx:.2f}" y="{bar_y}" width="{sw:.2f}" height="{bar_h}" fill="{r["color"]}" clip-path="url(#{clip_id})" />'
        )
        cx += sw

    legend: List[str] = []
    for idx, r in enumerate(display):
        x = 42
        y = 96 + idx * 28
        text = f'{r["label"]} \u2014 {format_tokens(int(r["tokens"]))} ({float(r["percent"]):.1f}%)'
        legend.append(
            f'<circle cx="{x}" cy="{y}" r="5" fill="{r["color"]}" />'
            f'<text x="{x + 14}" y="{y + 4}" fill="#9aa7b6" font-size="13" font-family="system-ui, sans-serif">{escape(text)}</text>'
        )

    footer_parts = [f"Total: {format_tokens(grand_total)} tokens"]
    if total_input > 0:
        footer_parts.append(f"Input: {format_tokens(total_input)}")
    if total_output > 0:
        footer_parts.append(f"Output: {format_tokens(total_output)}")
    if cache_hit_pct > 0:
        footer_parts.append(f"Cache hit: {cache_hit_pct:.0f}%")
    footer_text = " \u00b7 ".join(footer_parts)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <defs>
    <clipPath id="{clip_id}">
      <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="8" ry="8" />
    </clipPath>
  </defs>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="#0d1117" stroke="#24493e" stroke-width="2" rx="8" />
  <text x="32" y="34" fill="#5eead4" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{escape(title)}</text>
  <text x="32" y="50" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">{escape(subtitle)}</text>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="#30363d" rx="8" ry="8" />
  {''.join(segments)}
  {''.join(legend)}
  <text x="32" y="{footer_y + 12}" fill="#8b949e" font-size="11" font-family="system-ui, sans-serif">{escape(footer_text)}</text>
</svg>
"""


def render_vibe_scorecard_svg(
    *,
    title: str,
    subtitle: str,
    cells: Sequence[Tuple[str, str]],
    footer: str,
) -> str:
    width = 560
    cols = 3
    rows_count = math.ceil(len(cells) / cols)
    grid_top = 66
    cell_w = 156
    cell_h = 62
    cell_gap = 12
    grid_left = 32
    grid_h = rows_count * (cell_h + cell_gap) - cell_gap
    footer_y = grid_top + grid_h + 28
    height = max(footer_y + 18, _CARD_MIN_HEIGHT)

    cell_nodes: List[str] = []
    for idx, (value, label) in enumerate(cells):
        col = idx % cols
        row = idx // cols
        cx = grid_left + col * (cell_w + cell_gap)
        cy = grid_top + row * (cell_h + cell_gap)
        cell_nodes.append(
            f'<rect x="{cx}" y="{cy}" width="{cell_w}" height="{cell_h}" rx="8" fill="#161b22" />'
            f'<text x="{cx + cell_w / 2}" y="{cy + 28}" fill="#e6edf3" font-size="22" font-weight="700" '
            f'font-family="system-ui, sans-serif" text-anchor="middle">{escape(value)}</text>'
            f'<text x="{cx + cell_w / 2}" y="{cy + 48}" fill="#8b949e" font-size="11" '
            f'font-family="system-ui, sans-serif" text-anchor="middle">{escape(label)}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="#0d1117" stroke="#24493e" stroke-width="2" rx="8" />
  <text x="32" y="34" fill="#5eead4" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{escape(title)}</text>
  <text x="32" y="50" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">{escape(subtitle)}</text>
  {''.join(cell_nodes)}
  <text x="{width / 2}" y="{footer_y}" fill="#8b949e" font-size="12" font-family="system-ui, sans-serif" text-anchor="middle">{escape(footer)}</text>
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

    day_dominant_source: Dict[date, str] = {}
    if source == "combined":
        source_names = sorted(set(e.source for e in selected))
        src_day_mins: Dict[str, Dict[date, float]] = {s: defaultdict(float) for s in source_names}
        for src in source_names:
            src_intervals = [
                (e.ts, e.ts + event_window) for e in selected if e.source == src
            ]
            for start, end in merge_intervals(src_intervals):
                for day, mins in split_interval_by_day(start, end, year_start, year_end_exclusive):
                    src_day_mins[src][day] += mins
        all_dates = set()
        for per_day in src_day_mins.values():
            all_dates.update(per_day.keys())
        for day in all_dates:
            best_src, best_mins = "", 0.0
            for src in source_names:
                m = src_day_mins[src].get(day, 0.0)
                if m > best_mins:
                    best_mins = m
                    best_src = src
            if best_src:
                day_dominant_source[day] = best_src
    else:
        for event in selected:
            if year_start <= event.ts < year_end_exclusive:
                day_dominant_source.setdefault(event.ts.date(), source)

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
        "day_dominant_source": day_dominant_source,
        "display_start": display_start,
        "display_end": display_end,
        "visible_end": visible_end,
        "days": day_rows,
    }


_VIBE_TIERS = [
    (500, "\U0001f3c6", "Vibe Transcendence"),
    (200, "\U0001f525", "Vibe Legendary"),
    (50, "\u26a1", "Full Vibe Mode"),
    (10, "\U0001f3af", "Steady Vibes"),
    (1, "\U0001f331", "Vibe Seedling"),
    (0, "\u2728", "First Vibes"),
]

_VIBE_TAGLINES = [
    "{hours}h of prompt-fu \u00b7 {sessions} AI conversations \u00b7 {days} days of pure vibe.",
    "Typed a prompt. Got a feature. Repeated {sessions} times across {days} days.",
    "{days} days, {sessions} sessions, {hours}h \u2014 not a single line written by hand. Probably.",
    "My AI pair-programmer and I shipped for {days} days. We don't talk about the detours.",
    "{sessions} prompts fired \u00b7 {days} days survived \u00b7 {hours}h of AI-assisted flow state.",
    "{hours}h in the vibe zone. {sessions} sessions where the AI understood me on the first try. Just kidding.",
    "Let the AI cook for {days} days. It served {sessions} courses across {hours}h. Chef's kiss.",
    "{days} days of \"just one more prompt\" turned into {hours}h of shipped code.",
    "Prompt engineering is a real job. {hours}h across {days} days, {sessions} sessions as proof.",
    "I describe the vibes, the AI writes the code. {days} days and {hours}h in, still working.",
]

_BADGES: List[Tuple[str, str, str, str]] = [
    ("first_vibe",   "\U0001f331", "First Vibe",      "first active day"),
    ("streak_3",     "\U0001f525", "3-Day Streak",     "3-day coding streak"),
    ("streak_7",     "\u26a1",     "Week Warrior",     "7-day coding streak"),
    ("streak_14",    "\U0001f4aa", "Fortnight Force",  "14-day coding streak"),
    ("streak_30",    "\U0001f3c6", "Monthly Master",   "30-day coding streak"),
    ("streak_100",   "\U0001f451", "Century Coder",    "100-day coding streak"),
    ("active_50",    "\U0001f5d3\ufe0f", "Fifty Days",       "50 active days"),
    ("active_200",   "\U0001f4c5", "200 Club",         "200 active days"),
    ("marathon",     "\u23f0",     "Marathon",         "8h+ single session"),
    ("sessions_500", "\U0001f680", "500 Sessions",     "500 coding sessions"),
    ("multi_tool",   "\U0001f527", "Multi-Tool",       "3+ AI tools used"),
    ("night_owl",    "\U0001f989", "Night Owl",        "peak hours after midnight"),
]


def compute_badges(
    *,
    streak: int,
    active_days: int,
    sessions: int,
    longest_session_hours: float,
    tool_count: int,
    personality_name: str,
) -> List[Dict[str, object]]:
    checks: Dict[str, bool] = {
        "first_vibe":   active_days >= 1,
        "streak_3":     streak >= 3,
        "streak_7":     streak >= 7,
        "streak_14":    streak >= 14,
        "streak_30":    streak >= 30,
        "streak_100":   streak >= 100,
        "active_50":    active_days >= 50,
        "active_200":   active_days >= 200,
        "marathon":     longest_session_hours >= 8,
        "sessions_500": sessions >= 500,
        "multi_tool":   tool_count >= 3,
        "night_owl":    personality_name in ("Night Owl", "Midnight Hacker"),
    }
    return [
        {
            "id": bid,
            "emoji": emoji,
            "name": name,
            "description": desc,
            "earned": checks.get(bid, False),
        }
        for bid, emoji, name, desc in _BADGES
    ]


def render_badges_svg(
    *,
    title: str,
    subtitle: str,
    badges: Sequence[Dict[str, object]],
) -> str:
    width = 560
    cols = 4
    rows_count = math.ceil(len(badges) / cols)
    grid_top = 66
    cell_w = 120
    cell_h = 72
    cell_gap = 12
    grid_left = (width - cols * cell_w - (cols - 1) * cell_gap) // 2
    grid_h = rows_count * (cell_h + cell_gap) - cell_gap
    height = max(grid_top + grid_h + 24, _CARD_MIN_HEIGHT)

    earned_count = sum(1 for b in badges if b.get("earned"))
    next_badge = ""
    for b in badges:
        if not b.get("earned"):
            next_badge = f"Next: {b['emoji']} {b['name']} \u2014 {b['description']}"
            break

    cell_nodes: List[str] = []
    for idx, b in enumerate(badges):
        col = idx % cols
        row = idx // cols
        cx = grid_left + col * (cell_w + cell_gap)
        cy = grid_top + row * (cell_h + cell_gap)
        earned = b.get("earned", False)
        bg = "#161b22" if earned else "#0f1218"
        emoji_txt = str(b["emoji"]) if earned else "\U0001f512"
        name_color = "#e6edf3" if earned else "#484f58"
        desc_color = "#8b949e" if earned else "#3b4048"
        opacity = "1" if earned else "0.5"
        cell_nodes.append(
            f'<g opacity="{opacity}">'
            f'<rect x="{cx}" y="{cy}" width="{cell_w}" height="{cell_h}" rx="8" fill="{bg}" />'
            f'<text x="{cx + cell_w / 2}" y="{cy + 28}" font-size="20" '
            f'font-family="Apple Color Emoji, Segoe UI Emoji, Noto Color Emoji, sans-serif" '
            f'text-anchor="middle">{emoji_txt}</text>'
            f'<text x="{cx + cell_w / 2}" y="{cy + 46}" fill="{name_color}" font-size="11" '
            f'font-weight="600" font-family="system-ui, sans-serif" text-anchor="middle">'
            f'{escape(str(b["name"]))}</text>'
            f'<text x="{cx + cell_w / 2}" y="{cy + 60}" fill="{desc_color}" font-size="9" '
            f'font-family="system-ui, sans-serif" text-anchor="middle">'
            f'{escape(str(b["description"]))}</text>'
            f'</g>'
        )

    footer_y = grid_top + grid_h + 18
    footer_text = next_badge if next_badge else f"All {len(badges)} badges unlocked!"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="#0d1117" stroke="#24493e" stroke-width="2" rx="8" />
  <text x="32" y="34" fill="#5eead4" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{escape(title)}</text>
  <text x="32" y="50" fill="#8b949e" font-size="10" font-family="system-ui, sans-serif">{escape(subtitle)}</text>
  {''.join(cell_nodes)}
  <text x="{width / 2}" y="{footer_y}" fill="#8b949e" font-size="11" font-family="system-ui, sans-serif" text-anchor="middle">{escape(footer_text)}</text>
</svg>
"""


def update_readme_block(
    *,
    readme_path: Path,
    svg_ref: str,
    tools_svg_ref: str,
    recent_tools_svg_ref: str,
    token_svg_ref: str = "",
    scorecard_svg_ref: str = "",
    badges_svg_ref: str = "",
) -> None:
    ensure_parent(readme_path)
    content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

    updated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")

    block_lines = [
        MARKER_START,
        "",
        "### \U0001f31f **VibeTrace** \u2014 AI coding heartbeat",
        "",
        "<sub>Yearly heatmap & tool usage (auto-published)</sub>",
        "",
        f"![AI coding activity heatmap]({svg_ref})",
    ]
    if tools_svg_ref and recent_tools_svg_ref:
        block_lines.extend(
            [
                "",
                '<p align="center">',
                f'  <img src="{tools_svg_ref}" alt="Vibe Tool Mix" width="49%">',
                f'  <img src="{recent_tools_svg_ref}" alt="Last 7 Days" width="49%">',
                "</p>",
            ]
        )
    elif tools_svg_ref:
        block_lines.extend(["", f'<img src="{tools_svg_ref}" alt="Vibe Tool Mix" width="58%">'])
    elif recent_tools_svg_ref:
        block_lines.extend(["", f'<img src="{recent_tools_svg_ref}" alt="Last 7 Days" width="58%">'])
    if token_svg_ref and scorecard_svg_ref:
        block_lines.extend(
            [
                "",
                '<p align="center">',
                f'  <img src="{token_svg_ref}" alt="Token Economy" width="49%">',
                f'  <img src="{scorecard_svg_ref}" alt="Vibe Scorecard" width="49%">',
                "</p>",
            ]
        )
    elif token_svg_ref:
        block_lines.extend(["", f'<img src="{token_svg_ref}" alt="Token Economy" width="58%">'])
    elif scorecard_svg_ref:
        block_lines.extend(["", f'<img src="{scorecard_svg_ref}" alt="Vibe Scorecard" width="58%">'])
    if badges_svg_ref:
        block_lines.extend(
            [
                "",
                f'<img src="{badges_svg_ref}" alt="Coding Achievements" width="58%">',
            ]
        )
    block_lines.extend(
        [
            "",
            f"<sub>Auto-published \u00b7 Last refreshed: {updated_at}</sub>",
            "",
            MARKER_END,
        ]
    )
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
        day_dominant_source=report["day_dominant_source"],
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
                title="Vibe Tool Mix",
                subtitle="All-time tool usage",
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
                title=f"Last {int(tool_stats['recent_days'])} Days",
                subtitle="Daily tool usage",
                stats=tool_stats["recent"],
                empty_text="No recent tool activity detected yet.",
                clip_id="vibe-tool-recent-bar",
            ),
            encoding="utf-8",
        )

    stats_cache_paths = list(args.stats_cache) if args.stats_cache else [
        "~/.claude/stats-cache.json",
        "~/.codefuse/engine/cc/stats-cache.json",
    ]
    stats_data = load_stats_caches(stats_cache_paths)
    model_usage = stats_data["model_usage"]

    total_input = sum(u.get("inputTokens", 0) for u in model_usage.values())
    total_output = sum(u.get("outputTokens", 0) for u in model_usage.values())
    total_cache_read = sum(u.get("cacheReadInputTokens", 0) for u in model_usage.values())
    total_cache_create = sum(u.get("cacheCreationInputTokens", 0) for u in model_usage.values())
    total_all = total_input + total_output + total_cache_read + total_cache_create
    total_billed = total_input + total_output
    cache_denominator = total_cache_read + total_input + total_cache_create
    cache_hit_pct = (total_cache_read / cache_denominator * 100) if cache_denominator else 0.0

    output_token_svg = args.output_token_svg.strip()
    if output_token_svg and model_usage:
        token_svg_path = Path(output_token_svg).expanduser()
        ensure_parent(token_svg_path)
        n_models = len(model_usage)
        token_svg_path.write_text(
            render_token_stats_svg(
                title=f"Token Economy ({args.year})",
                subtitle=f"{format_tokens(total_all)} tokens consumed across {n_models} model{'s' if n_models != 1 else ''}",
                model_usage=model_usage,
                cache_hit_pct=cache_hit_pct,
                total_input=total_input,
                total_output=total_output,
                clip_id="vibe-token-bar",
            ),
            encoding="utf-8",
        )

    streak = compute_longest_streak(report["day_minutes"])
    personality_emoji, personality_name, peak_hour = compute_vibe_personality(stats_data["hour_counts"])
    total_messages = int(stats_data["total_messages"])
    total_tool_calls = int(stats_data["total_tool_calls"])
    longest_ms = int(stats_data["longest_session_ms"])
    longest_hours = round(longest_ms / 3_600_000, 1)
    summary = report["summary"]
    active_minutes = int(summary["active_minutes"])
    sessions = int(summary["sessions"])
    vibe_power = int(
        active_minutes * 0.5
        + sessions * 3
        + total_messages * 0.1
        + total_tool_calls * 0.5
        + total_all / 10000
    )

    output_scorecard_svg = args.output_scorecard_svg.strip()
    if output_scorecard_svg:
        sc_path = Path(output_scorecard_svg).expanduser()
        ensure_parent(sc_path)
        sc_cells = [
            (format_big_number(total_messages), "messages"),
            (format_big_number(total_tool_calls), "tool calls"),
            (format_tokens(total_all), "tokens"),
            (f"{streak} days", "longest streak"),
            (f"{longest_hours}h", "longest session"),
            (f"{cache_hit_pct:.0f}%", "cache hit rate"),
        ]
        footer = f"{personality_emoji} {personality_name}  \u00b7  Peak hour: {peak_hour}:00  \u00b7  Vibe Power: {vibe_power:,}"
        sc_path.write_text(
            render_vibe_scorecard_svg(
                title=f"Vibe Scorecard ({args.year})",
                subtitle="The numbers behind the vibes",
                cells=sc_cells,
                footer=footer,
            ),
            encoding="utf-8",
        )

    tool_count = len([s for s in tool_stats.get("overall", []) if float(s.get("active_minutes", 0)) > 0])
    badges = compute_badges(
        streak=streak,
        active_days=int(summary["active_days"]),
        sessions=sessions,
        longest_session_hours=longest_hours,
        tool_count=tool_count,
        personality_name=personality_name,
    )

    output_badges_svg = args.output_badges_svg.strip()
    if output_badges_svg:
        badges_path = Path(output_badges_svg).expanduser()
        ensure_parent(badges_path)
        earned_count = sum(1 for b in badges if b["earned"])
        badges_path.write_text(
            render_badges_svg(
                title=f"Coding Achievements ({args.year})",
                subtitle=f"{earned_count} of {len(badges)} badges unlocked",
                badges=badges,
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
            "token_stats": {
                "total_tokens": total_all,
                "total_billed": total_billed,
                "total_input": total_input,
                "total_output": total_output,
                "cache_hit_pct": round(cache_hit_pct, 2),
            },
            "vibe_scorecard": {
                "total_messages": total_messages,
                "total_tool_calls": total_tool_calls,
                "longest_streak": streak,
                "longest_session_hours": longest_hours,
                "peak_hour": peak_hour,
                "personality": personality_name,
                "vibe_power": vibe_power,
            },
            "badges": [
                {"id": b["id"], "name": b["name"], "earned": b["earned"]}
                for b in badges
            ],
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

        token_svg_ref = args.token_svg_url.strip()
        if not token_svg_ref and output_token_svg:
            try:
                token_svg_ref = os.path.relpath(Path(output_token_svg).expanduser(), readme_path.parent)
            except ValueError:
                token_svg_ref = output_token_svg

        scorecard_svg_ref = args.scorecard_svg_url.strip()
        if not scorecard_svg_ref and output_scorecard_svg:
            try:
                scorecard_svg_ref = os.path.relpath(Path(output_scorecard_svg).expanduser(), readme_path.parent)
            except ValueError:
                scorecard_svg_ref = output_scorecard_svg

        badges_svg_ref = args.badges_svg_url.strip()
        if not badges_svg_ref and output_badges_svg:
            try:
                badges_svg_ref = os.path.relpath(Path(output_badges_svg).expanduser(), readme_path.parent)
            except ValueError:
                badges_svg_ref = output_badges_svg

        update_readme_block(
            readme_path=readme_path,
            svg_ref=svg_ref,
            tools_svg_ref=tools_svg_ref,
            recent_tools_svg_ref=recent_tools_svg_ref,
            token_svg_ref=token_svg_ref,
            scorecard_svg_ref=scorecard_svg_ref,
            badges_svg_ref=badges_svg_ref,
        )

    active_days = int(summary["active_days"])
    active_hours = round(active_minutes / 60, 1)

    _R = "\033[0m"
    _B = "\033[1m"
    _D = "\033[2m"
    _C = "\033[36m"
    _G = "\033[32m"
    _W = "\033[97m"

    lines: List[str] = [""]
    lines.append(f"  {_B}{_C}\u26a1 VibeTrace{_R}")
    lines.append(f"  {_D}Turn AI coding history into a GitHub profile flex{_R}")
    lines.append("")
    lines.append(
        f"  {_G}\u25cf{_R} {_B}{active_days}{_R} active days   "
        f"{_G}\u25cf{_R} {_B}{sessions}{_R} sessions   "
        f"{_G}\u25cf{_R} {_B}{active_hours}h{_R} active"
    )
    if total_messages:
        lines.append(
            f"  {_G}\u25cf{_R} {_B}{format_big_number(total_messages)}{_R} messages   "
            f"{_G}\u25cf{_R} {_B}{format_big_number(total_tool_calls)}{_R} tool calls   "
            f"{_G}\u25cf{_R} {_B}{format_tokens(total_all)}{_R} tokens"
        )

    tool_overview = tool_stats.get("overall", [])
    if isinstance(tool_overview, list) and tool_overview:
        lines.append("")
        lines.append(f"  {_B}Vibe Tool Mix{_R}")
        for stat in tool_overview[:8]:
            lbl = str(stat["label"])
            pct = float(stat["percent"])
            dur = format_duration_compact(float(stat["active_minutes"]))
            bar_n = int(pct / 5)
            bar = "\u2588" * bar_n + "\u2591" * (20 - bar_n)
            lines.append(f"  {_D}\u25cf{_R} {lbl:<16s} {pct:5.1f}%  {bar}  {dur}")

    lines.append("")
    lines.append(f"  {_G}\u2713{_R} Heatmap    {output_svg}")
    if output_tools_svg:
        lines.append(f"  {_G}\u2713{_R} Tools      {output_tools_svg}")
    if output_recent_tools_svg:
        lines.append(f"  {_G}\u2713{_R} Recent     {output_recent_tools_svg}")
    if output_token_svg:
        lines.append(f"  {_G}\u2713{_R} Tokens     {output_token_svg}")
    if output_scorecard_svg:
        lines.append(f"  {_G}\u2713{_R} Scorecard  {output_scorecard_svg}")
    if output_badges_svg:
        lines.append(f"  {_G}\u2713{_R} Badges     {output_badges_svg}")
    if output_json:
        lines.append(f"  {_G}\u2713{_R} JSON       {output_json}")
    if readme_target:
        lines.append(f"  {_G}\u2713{_R} README     {readme_target}")
    lines.append("")
    lines.append(f"  {_G}\u25cf{_R} {_B}PROFILE READY{_R}")
    lines.append("")

    print("\n".join(lines))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
