#!/usr/bin/env python3
"""Verify comparison privacy, public aggregate consistency, and optional source.

The source audit recomputes the comparison independently from the private
export without importing the builder. Private records are never printed.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re

from verify_data import keys, number, require, valid_pair, verify as verify_history

ROOT = Path(__file__).resolve().parents[1]


def calendar_date(value, label):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
            f"{label} must contain a date only")
    return date.fromisoformat(value)


def rank_rows(mapping):
    return sorted([[index, *pair] for index, pair in mapping.items()],
                  key=lambda row: (-row[1], -row[2], row[0]))


def validate_rows(rows, size, label):
    require(isinstance(rows, list), f"{label} must be an array")
    seen = set()
    for row in rows:
        require(isinstance(row, list) and len(row) == 3, f"{label} rows must be [index, plays, ms]")
        index, plays, ms = row
        number(index, label + " index")
        require(index < size and index not in seen, f"{label} has an invalid or repeated index")
        seen.add(index)
        valid_pair([plays, ms], label, allow_empty=False)
    require(rows == sorted(rows, key=lambda row: (-row[1], -row[2], row[0])),
            f"{label} must be ranked by plays, then duration, then index")
    return [sum(row[1] for row in rows), sum(row[2] for row in rows)]


def daily_totals(history, start, end):
    days = [row for row in history["days"] if start <= row[0] <= end]
    return [sum(row[1] for row in days), sum(row[2] for row in days), len(days)]


def verify(data, history):
    verify_history(history)
    keys(data, "meta firstDay windows", "comparison root")
    meta = data["meta"]
    keys(meta, "name timezone start end qualification", "comparison meta")
    require(meta["name"] == "Devin", "Only the authorized name Devin may be published")
    require(meta["timezone"] == "UTC", "Comparison boundaries must be explicitly UTC")
    first = calendar_date(meta["start"], "first observed day")
    last = calendar_date(meta["end"], "last observed day")
    require(meta["start"] == history["meta"]["period"]["start"] and
            meta["end"] == history["meta"]["period"]["end"],
            "Comparison date range must match the public listening history")
    qualification = meta["qualification"]
    keys(qualification, "minMs audioOnly excludeIncognito validSpotifyTrackId", "qualification")
    require(type(qualification["minMs"]) is int and qualification["minMs"] == 30_000,
            "Qualifying duration must remain 30 seconds")
    for field in ("audioOnly", "excludeIncognito", "validSpotifyTrackId"):
        require(qualification[field] is True, f"Qualification {field} must remain enabled")

    first_day = data["firstDay"]
    keys(first_day, "date plays ms tracks", "firstDay")
    require(first_day["date"] == meta["start"], "First-day date must match the first observed day")
    valid_pair([first_day["plays"], first_day["ms"]], "first-day totals", allow_empty=False)
    require(validate_rows(first_day["tracks"], len(history["tracks"]), "first-day tracks") ==
            [first_day["plays"], first_day["ms"]], "First-day track totals do not reconcile")
    require([first_day["plays"], first_day["ms"]] == daily_totals(history, meta["start"], meta["start"])[:2],
            "First-day totals do not reconcile with public daily history")

    require(isinstance(data["windows"], list) and len(data["windows"]) == 3,
            "Exactly three comparison windows are required")
    for expected_days, window in zip((30, 90, 365), data["windows"]):
        keys(window, "days then now", "window")
        number(window["days"], "window days", 1)
        require(window["days"] == expected_days, "Window sizes must be 30, 90, and 365 days")
        for side in ("then", "now"):
            value = window[side]
            keys(value, "start end days plays ms activeDays artists tracks", side)
            start = calendar_date(value["start"], side + " start")
            end = calendar_date(value["end"], side + " end")
            number(value["days"], side + " days", 1)
            require(value["days"] == expected_days == (end - start).days + 1,
                    "Comparison windows must have exact equal calendar-day duration")
            require(first <= start <= end <= last, "Comparison window is outside observed history")
            expected_start = first if side == "then" else last - timedelta(days=expected_days - 1)
            expected_end = first + timedelta(days=expected_days - 1) if side == "then" else last
            require((start, end) == (expected_start, expected_end), "Comparison window has incorrect boundaries")
            valid_pair([value["plays"], value["ms"]], side + " totals")
            number(value["activeDays"], side + " active days")
            require(value["activeDays"] <= expected_days, "Too many active days in comparison window")
            require([value["plays"], value["ms"], value["activeDays"]] ==
                    daily_totals(history, value["start"], value["end"]),
                    "Comparison totals do not reconcile with public daily history")
            track_totals = validate_rows(value["tracks"], len(history["tracks"]), side + " tracks")
            artist_totals = validate_rows(value["artists"], len(history["artists"]), side + " artists")
            require(track_totals == artist_totals == [value["plays"], value["ms"]],
                    "Comparison track and artist totals do not reconcile")
            derived_artists = defaultdict(lambda: [0, 0])
            for index, plays, ms in value["tracks"]:
                artist = history["tracks"][index]["artist"]
                derived_artists[artist][0] += plays
                derived_artists[artist][1] += ms
            require(value["artists"] == rank_rows(derived_artists), "Artist aggregates do not match catalog attribution")
    return True


def verify_source(data, history, source):
    """Independently reconstruct each output field from qualified private rows."""
    files = sorted(source.glob("Streaming_History_*.json"))
    require(bool(files), "No source export files found")
    track_indexes = {track["spotifyId"]: index for index, track in enumerate(history["tracks"])}
    # Each record contains only the date, public track index, and duration.
    records = []
    for path in files:
        if not path.name.startswith("Streaming_History_Audio_"):
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(rows, list), "Source files must contain JSON arrays")
        for row in rows:
            if not isinstance(row, dict):
                continue
            uri = row.get("spotify_track_uri")
            if not isinstance(uri, str) or not re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", uri):
                continue
            if row.get("incognito_mode") is not False:
                continue
            ms = row.get("ms_played")
            if type(ms) is not int or ms < 30_000:
                continue
            try:
                timestamp = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    continue
                day = timestamp.astimezone(timezone.utc).date().isoformat()
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            if any(not isinstance(row.get(field), str) or not row[field].strip() for field in (
                "master_metadata_track_name", "master_metadata_album_artist_name", "master_metadata_album_album_name",
            )):
                continue
            require(uri[14:] in track_indexes, "Qualifying source track is missing from public catalog")
            records.append((day, track_indexes[uri[14:]], ms))
    require(bool(records), "Source has no qualifying records")
    require([min(row[0] for row in records), max(row[0] for row in records)] ==
            [data["meta"]["start"], data["meta"]["end"]], "Observed endpoints do not match source")
    require(len(records) == history["meta"]["qualifiedEvents"] and
            sum(row[2] for row in records) == history["meta"]["totalMs"],
            "Source qualification does not reconcile with the published history")
    sections = [(data["firstDay"]["date"], data["firstDay"]["date"], data["firstDay"])]
    for window in data["windows"]:
        sections.extend((window[side]["start"], window[side]["end"], window[side]) for side in ("then", "now"))
    for start, end, section in sections:
        selected = [row for row in records if start <= row[0] <= end]
        expected_tracks = defaultdict(lambda: [0, 0])
        for _, index, ms in selected:
            expected_tracks[index][0] += 1
            expected_tracks[index][1] += ms
        require(section["tracks"] == rank_rows(expected_tracks), "Published track aggregates do not match source")
        require([section["plays"], section["ms"]] == [len(selected), sum(row[2] for row in selected)],
                "Published totals do not match source")
        if "activeDays" in section:
            require(section["activeDays"] == len({row[0] for row in selected}), "Published active days do not match source")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=ROOT / "site/data/comparison.json")
    parser.add_argument("--history", type=Path, default=ROOT / "site/data/history.json")
    parser.add_argument("--source", type=Path, help="Also independently audit against the private source directory")
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    history = json.loads(args.history.read_text(encoding="utf-8"))
    verify(data, history)
    if args.source:
        verify_source(data, history, args.source)
    print("PASS: comparison privacy allowlist, equal UTC windows, catalog attribution, and all aggregate totals verified."
          + (" Independent private-source audit passed." if args.source else ""))


if __name__ == "__main__":
    main()
