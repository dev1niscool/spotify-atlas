#!/usr/bin/env python3
"""Build privacy-safe, equal-calendar-day comparisons from a private export.

Catalog indexes refer to site/data/history.json. The public output contains
only daily boundaries and listening aggregates, never raw events or exact
timestamps. The first observed day is not an account creation date.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TRACK_URI = re.compile(r"spotify:track:([A-Za-z0-9]{22})\Z")
WINDOW_DAYS = (30, 90, 365)


def ranked(totals):
    return sorted([[index, *pair] for index, pair in totals.items()],
                  key=lambda row: (-row[1], -row[2], row[0]))


def qualifying_events(source, catalog):
    """Yield private values in memory; publish only their aggregate counts."""
    files = sorted(source.glob("Streaming_History_Audio_*.json"))
    if not files:
        raise ValueError("No Spotify audio streaming-history files found")
    for path in files:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("Expected a JSON array in the source export")
        for row in rows:
            if not isinstance(row, dict) or row.get("incognito_mode") is not False:
                continue
            uri = row.get("spotify_track_uri")
            match = TRACK_URI.fullmatch(uri) if isinstance(uri, str) else None
            if match is None:
                continue
            ms = row.get("ms_played")
            if type(ms) is not int or ms < 30_000:
                continue
            try:
                stamp = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    continue
                day = stamp.astimezone(timezone.utc).date()
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            names = [row.get(field) for field in (
                "master_metadata_track_name", "master_metadata_album_artist_name",
                "master_metadata_album_album_name",
            )]
            if any(not isinstance(name, str) or not name.strip() for name in names):
                continue
            track_id = match.group(1)
            if track_id not in catalog:
                raise ValueError("Source contains a qualifying track missing from the public catalog; rebuild history.json first")
            yield day, catalog[track_id], ms


def aggregate(events, start, end, tracks):
    track_totals = defaultdict(lambda: [0, 0])
    artist_totals = defaultdict(lambda: [0, 0])
    active_days = set()
    for day, index, ms in events:
        if start <= day <= end:
            active_days.add(day)
            for totals, key in ((track_totals, index), (artist_totals, tracks[index]["artist"])):
                totals[key][0] += 1
                totals[key][1] += ms
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "days": (end - start).days + 1,
        "plays": sum(pair[0] for pair in track_totals.values()),
        "ms": sum(pair[1] for pair in track_totals.values()),
        "activeDays": len(active_days), "artists": ranked(artist_totals),
        "tracks": ranked(track_totals),
    }


def build(source, history):
    tracks = history["tracks"]
    catalog = {track["spotifyId"]: index for index, track in enumerate(tracks)}
    events = list(qualifying_events(source, catalog))
    if not events:
        raise ValueError("No qualifying music events found")
    start, end = min(event[0] for event in events), max(event[0] for event in events)
    if (end - start).days + 1 < max(WINDOW_DAYS):
        raise ValueError("At least 365 calendar days of export history are required")
    observed_first = aggregate(events, start, start, tracks)
    windows = []
    for days in WINDOW_DAYS:
        offset = timedelta(days=days - 1)
        windows.append({
            "days": days,
            "then": aggregate(events, start, start + offset, tracks),
            "now": aggregate(events, end - offset, end, tracks),
        })
    return {
        "meta": {
            "name": "Devin", "timezone": "UTC", "start": start.isoformat(), "end": end.isoformat(),
            "qualification": {"minMs": 30_000, "audioOnly": True,
                              "excludeIncognito": True, "validSpotifyTrackId": True},
        },
        "firstDay": {"date": start.isoformat(), "plays": observed_first["plays"],
                     "ms": observed_first["ms"], "tracks": observed_first["tracks"]},
        "windows": windows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT.parent / "Spotify Extended Streaming History")
    parser.add_argument("--history", type=Path, default=ROOT / "site/data/history.json")
    parser.add_argument("--output", type=Path, default=ROOT / "site/data/comparison.json")
    args = parser.parse_args()
    history = json.loads(args.history.read_text(encoding="utf-8"))
    data = build(args.source, history)
    from verify_comparison import verify
    verify(data, history)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"firstObserved": data["meta"]["start"], "lastObserved": data["meta"]["end"],
                      "windows": [window["days"] for window in data["windows"]],
                      "bytes": args.output.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
