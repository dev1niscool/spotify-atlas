#!/usr/bin/env python3
"""Build the public, aggregated music dataset from a private Spotify export.

The export stays outside the repository. No raw rows, precise timestamps,
network/device details, or other personal account information are published.
Only audio-file music plays with valid track URIs, non-incognito mode, and
at least 30 seconds played contribute to the public counts and duration.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_URI = re.compile(r"spotify:track:([A-Za-z0-9]{22})\Z")
MIN_PLAY_MS = 30_000
EXCLUDED_REASONS = (
    "video", "nonMusic", "incognito", "under30Seconds", "invalidDuration",
    "invalidTimestamp", "missingMetadata",
)


def pair() -> list[int]:
    return [0, 0]


def add(bucket: list[int], ms: int) -> None:
    bucket[0] += 1
    bucket[1] += ms


def calendar_months(first: str, last: str):
    year, month = map(int, first.split("-"))
    while f"{year:04d}-{month:02d}" <= last:
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month == 13:
            year += 1
            month = 1


def build(source: Path) -> dict:
    files = sorted(source.glob("Streaming_History_*.json"))
    if not files:
        raise ValueError("No Spotify streaming-history JSON files found in source directory")

    source_events = 0
    excluded = Counter({reason: 0 for reason in EXCLUDED_REASONS})
    metadata = defaultdict(Counter)
    month_tracks = defaultdict(lambda: defaultdict(pair))
    day_totals = defaultdict(pair)
    rhythm_totals = defaultdict(lambda: {"weekdays": [pair() for _ in range(7)],
                                         "hours": [pair() for _ in range(24)]})

    for path in files:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"Expected a JSON array in {path.name}")
        is_audio_file = path.name.startswith("Streaming_History_Audio_")
        for row in rows:
            source_events += 1
            if not is_audio_file:
                excluded["video"] += 1
                continue
            if not isinstance(row, dict):
                excluded["nonMusic"] += 1
                continue
            uri = row.get("spotify_track_uri")
            match = TRACK_URI.fullmatch(uri) if isinstance(uri, str) else None
            if match is None:
                excluded["nonMusic"] += 1
                continue
            # Include only an explicit false flag; unknown/private stays private.
            if row.get("incognito_mode") is not False:
                excluded["incognito"] += 1
                continue
            ms = row.get("ms_played")
            if isinstance(ms, bool) or not isinstance(ms, int) or ms < 0:
                excluded["invalidDuration"] += 1
                continue
            if ms < MIN_PLAY_MS:
                excluded["under30Seconds"] += 1
                continue
            try:
                stamp = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError("Timestamp must specify a timezone")
                stamp = stamp.astimezone(timezone.utc)
            except (ValueError, TypeError, AttributeError, KeyError):
                excluded["invalidTimestamp"] += 1
                continue
            names = tuple(row.get(key) for key in (
                "master_metadata_track_name", "master_metadata_album_artist_name",
                "master_metadata_album_album_name",
            ))
            if any(not isinstance(name, str) or not name.strip() for name in names):
                excluded["missingMetadata"] += 1
                continue

            track_id = match.group(1)
            metadata[track_id][names] += 1
            add(month_tracks[stamp.strftime("%Y-%m")][track_id], ms)
            add(day_totals[stamp.strftime("%Y-%m-%d")], ms)
            add(rhythm_totals[stamp.year]["weekdays"][stamp.weekday()], ms)
            add(rhythm_totals[stamp.year]["hours"][stamp.hour], ms)

    if not month_tracks:
        raise ValueError("No qualifying public music plays found")

    # Use the most common catalog metadata for each Spotify track ID; sorting
    # breaks ties deterministically. This also keeps artist/track totals aligned.
    canonical = {
        track_id: sorted(variants, key=lambda names: (-variants[names], names))[0]
        for track_id, variants in metadata.items()
    }
    artists = sorted({names[1] for names in canonical.values()}, key=lambda name: (name.casefold(), name))
    artist_index = {name: index for index, name in enumerate(artists)}
    track_ids = sorted(canonical)
    track_index = {track_id: index for index, track_id in enumerate(track_ids)}
    tracks = [
        {"title": canonical[track_id][0], "artist": artist_index[canonical[track_id][1]],
         "album": canonical[track_id][2], "spotifyId": track_id}
        for track_id in track_ids
    ]

    months = []
    for month in calendar_months(min(month_tracks), max(month_tracks)):
        artist_totals = defaultdict(pair)
        track_rows = []
        for track_id, (plays, ms) in sorted(month_tracks[month].items()):
            index = track_index[track_id]
            track_rows.append([index, plays, ms])
            artist = tracks[index]["artist"]
            artist_totals[artist][0] += plays
            artist_totals[artist][1] += ms
        months.append({
            "month": month,
            "plays": sum(row[1] for row in track_rows),
            "ms": sum(row[2] for row in track_rows),
            "artists": [[index, *totals] for index, totals in sorted(artist_totals.items())],
            "tracks": track_rows,
        })

    days = [[day, *totals] for day, totals in sorted(day_totals.items())]
    qualified = sum(month["plays"] for month in months)
    data = {
        "meta": {
            "name": "Devin", "timezone": "UTC", "minPlayMs": MIN_PLAY_MS,
            "weekdayOrder": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "period": {"start": days[0][0], "end": days[-1][0]},
            "years": sorted(rhythm_totals),
            "sourceEvents": source_events, "qualifiedEvents": qualified,
            "totalMs": sum(month["ms"] for month in months), "activeDays": len(days),
            "excluded": dict(excluded), "playlists": [],
        },
        "artists": artists, "tracks": tracks, "months": months, "days": days,
        "rhythms": [{"year": year, **rhythm_totals[year]} for year in sorted(rhythm_totals)],
    }
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PROJECT_ROOT.parent / "Spotify Extended Streaming History")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "site/data/history.json")
    args = parser.parse_args()
    data = build(args.source.resolve())
    # Validate before saving so a future export cannot silently expand the
    # public schema or introduce private fields.
    from verify_data import verify
    verify(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    meta = data["meta"]
    print(json.dumps({
        "qualifiedPlays": meta["qualifiedEvents"], "hours": round(meta["totalMs"] / 3_600_000, 2),
        "artists": len(data["artists"]), "tracks": len(data["tracks"]),
        "activeDays": meta["activeDays"], "period": meta["period"],
        "excluded": meta["excluded"], "bytes": args.output.stat().st_size,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, AssertionError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
