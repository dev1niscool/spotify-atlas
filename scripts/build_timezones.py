#!/usr/bin/env python3
"""Build date, hour, and weekday aggregates for Central and Eastern Time.

Private export timestamps stay in memory. The public result contains only
local calendar dates and totals, with IANA timezone rules handling daylight
saving time and midnight/year boundaries.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from build_data import MIN_PLAY_MS, TRACK_URI

ROOT = Path(__file__).resolve().parents[1]
ZONE_SPECS = (
    ("America/Chicago", "Central Time", "CT"),
    ("America/New_York", "Eastern Time", "ET"),
)


def qualifying_events(source):
    """Apply the same audio-only, public-play predicate as build_data.py."""
    files = sorted(source.glob("Streaming_History_*.json"))
    if not files:
        raise ValueError("No Spotify streaming-history JSON files found")
    for path in files:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("Expected a JSON array in the source export")
        if not path.name.startswith("Streaming_History_Audio_"):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            uri = row.get("spotify_track_uri")
            if not isinstance(uri, str) or TRACK_URI.fullmatch(uri) is None:
                continue
            if row.get("incognito_mode") is not False:
                continue
            ms = row.get("ms_played")
            if type(ms) is not int or ms < MIN_PLAY_MS:
                continue
            try:
                stamp = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    continue
                stamp = stamp.astimezone(timezone.utc)
            except (ValueError, TypeError, AttributeError, KeyError):
                continue
            names = [row.get(field) for field in (
                "master_metadata_track_name", "master_metadata_album_artist_name",
                "master_metadata_album_album_name",
            )]
            if any(not isinstance(name, str) or not name.strip() for name in names):
                continue
            yield stamp, ms


def build(source):
    buckets = []
    for zone_id, label, short_label in ZONE_SPECS:
        buckets.append((
            ZoneInfo(zone_id),
            {"id": zone_id, "label": label, "shortLabel": short_label},
            defaultdict(lambda: [0, 0]),
            defaultdict(lambda: {"hours": [[0, 0] for _ in range(24)],
                                 "weekdays": [[0, 0] for _ in range(7)]}),
        ))
    for stamp, ms in qualifying_events(source):
        for timezone_info, _, days, rhythms in buckets:
            local = stamp.astimezone(timezone_info)
            for pair in (days[local.date().isoformat()],
                         rhythms[local.year]["hours"][local.hour],
                         rhythms[local.year]["weekdays"][local.weekday()]):
                pair[0] += 1
                pair[1] += ms
    zones = []
    for _, metadata, day_totals, rhythm_totals in buckets:
        if not day_totals:
            raise ValueError("No qualifying public music plays found")
        days = [[day, *pair] for day, pair in sorted(day_totals.items())]
        zones.append({
            **metadata,
            "period": {"start": days[0][0], "end": days[-1][0]},
            "years": sorted(rhythm_totals),
            "days": days,
            "rhythms": [{"year": year, **rhythm_totals[year]} for year in sorted(rhythm_totals)],
        })
    return {"defaultZone": "America/Chicago", "zones": zones}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT.parent / "Spotify Extended Streaming History")
    parser.add_argument("--history", type=Path, default=ROOT / "site/data/history.json")
    parser.add_argument("--output", type=Path, default=ROOT / "site/data/timezones.json")
    args = parser.parse_args()
    data = build(args.source.resolve())
    history = json.loads(args.history.read_text(encoding="utf-8"))
    from verify_timezones import verify
    verify(data, history)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"defaultZone": data["defaultZone"], "qualifiedPlays": history["meta"]["qualifiedEvents"],
                      "zones": [{"id": zone["id"], "activeDays": len(zone["days"]),
                                 "period": zone["period"]} for zone in data["zones"]],
                      "bytes": args.output.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
