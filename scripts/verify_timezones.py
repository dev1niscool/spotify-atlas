#!/usr/bin/env python3
"""Audit timezone aggregates, their privacy allowlist, and optional private source.

The default audit needs only public files and runs in CI. The source audit
independently reconstructs each local date/hour bucket from private rows;
no exact timestamps or private source fields are printed or published.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from verify_data import keys, number, require, valid_pair, verify as verify_history

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ZONES = (
    ("America/Chicago", "Central Time", "CT"),
    ("America/New_York", "Eastern Time", "ET"),
)


def calendar_date(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
            "Timezone dates must contain YYYY-MM-DD only")
    return date.fromisoformat(value)


def verify(data, history):
    verify_history(history)
    keys(data, "defaultZone zones", "timezone root")
    require(data["defaultZone"] == "America/Chicago", "Central Time must be the default")
    require(isinstance(data["zones"], list) and len(data["zones"]) == len(EXPECTED_ZONES),
            "Exactly Central and Eastern timezone aggregates are required")
    expected_global = [history["meta"]["qualifiedEvents"], history["meta"]["totalMs"]]
    for zone, expected in zip(data["zones"], EXPECTED_ZONES):
        keys(zone, "id label shortLabel period years days rhythms", "timezone")
        require(tuple(zone[field] for field in ("id", "label", "shortLabel")) == expected,
                "Timezone metadata must match the fixed allowlist")
        keys(zone["period"], "start end", "timezone period")
        calendar_date(zone["period"]["start"])
        calendar_date(zone["period"]["end"])
        require(isinstance(zone["days"], list) and bool(zone["days"]), "Timezone days must be a nonempty array")
        year_totals = defaultdict(lambda: [0, 0])
        weekday_totals = defaultdict(lambda: [[0, 0] for _ in range(7)])
        previous = None
        for row in zone["days"]:
            require(isinstance(row, list) and len(row) == 3, "Timezone day rows must be [date, plays, ms]")
            label, plays, ms = row
            day = calendar_date(label)
            require(previous is None or previous < label, "Timezone days must be unique and sorted")
            previous = label
            valid_pair([plays, ms], "timezone day", allow_empty=False)
            for pair in (year_totals[day.year], weekday_totals[day.year][day.weekday()]):
                pair[0] += plays
                pair[1] += ms
        require(zone["period"] == {"start": zone["days"][0][0], "end": zone["days"][-1][0]},
                "Timezone period does not match local daily aggregation")
        years = sorted(year_totals)
        require(isinstance(zone["years"], list), "Timezone years must be an array")
        for year in zone["years"]:
            number(year, "timezone year", 1)
        require(zone["years"] == years, "Timezone years do not match local dates")
        require([sum(pair[i] for pair in year_totals.values()) for i in range(2)] == expected_global,
                "Timezone totals do not reconcile with the public listening history")
        require(isinstance(zone["rhythms"], list) and len(zone["rhythms"]) == len(years),
                "Timezone rhythms must contain every local year")
        for year, rhythm in zip(years, zone["rhythms"]):
            keys(rhythm, "year hours weekdays", "timezone rhythm")
            number(rhythm["year"], "rhythm year", 1)
            require(rhythm["year"] == year, "Timezone rhythms must have sorted, unique local years")
            for field, size in (("hours", 24), ("weekdays", 7)):
                require(isinstance(rhythm[field], list) and len(rhythm[field]) == size,
                        f"Invalid timezone {field} dimension")
                for pair in rhythm[field]:
                    valid_pair(pair, "timezone " + field)
                require([sum(pair[i] for pair in rhythm[field]) for i in range(2)] == year_totals[year],
                        f"Timezone {field} totals do not reconcile with local-year daily totals")
            require(rhythm["weekdays"] == weekday_totals[year],
                    "Timezone weekday totals do not match local dates")
    return True


def verify_source(data, history, source):
    """Independent source audit; intentionally does not import the builder."""
    files = sorted(source.glob("Streaming_History_*.json"))
    require(bool(files), "No source export files found")
    # One bucket per local date and hour, containing aggregates only.
    local_buckets = {zone_id: defaultdict(lambda: [0, 0]) for zone_id, _, _ in EXPECTED_ZONES}
    timezone_infos = {zone_id: ZoneInfo(zone_id) for zone_id in local_buckets}
    source_totals = [0, 0]
    for path in files:
        rows = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(rows, list), "Source files must contain JSON arrays")
        if not path.name.startswith("Streaming_History_Audio_"):
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get("incognito_mode") is not False:
                continue
            uri = row.get("spotify_track_uri")
            if not isinstance(uri, str) or not re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", uri):
                continue
            ms = row.get("ms_played")
            if type(ms) is not int or ms < 30_000:
                continue
            try:
                timestamp = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    continue
                timestamp = timestamp.astimezone(timezone.utc)
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            if any(not isinstance(row.get(field), str) or not row[field].strip() for field in (
                "master_metadata_track_name", "master_metadata_album_artist_name", "master_metadata_album_album_name",
            )):
                continue
            source_totals[0] += 1
            source_totals[1] += ms
            for zone_id, timezone_info in timezone_infos.items():
                local = timestamp.astimezone(timezone_info)
                bucket = local_buckets[zone_id][(local.date(), local.hour)]
                bucket[0] += 1
                bucket[1] += ms
    require(source_totals == [history["meta"]["qualifiedEvents"], history["meta"]["totalMs"]],
            "Timezone source qualification does not reconcile with public history")
    for zone in data["zones"]:
        days = defaultdict(lambda: [0, 0])
        hours = defaultdict(lambda: [[0, 0] for _ in range(24)])
        weekdays = defaultdict(lambda: [[0, 0] for _ in range(7)])
        for (day, hour), totals in local_buckets[zone["id"]].items():
            for bucket in (days[day.isoformat()], hours[day.year][hour], weekdays[day.year][day.weekday()]):
                bucket[0] += totals[0]
                bucket[1] += totals[1]
        require(zone["days"] == [[day, *pair] for day, pair in sorted(days.items())],
                "Timezone daily aggregates do not match the private source")
        expected_rhythms = [{"year": year, "hours": hours[year], "weekdays": weekdays[year]} for year in sorted(hours)]
        require(zone["rhythms"] == expected_rhythms,
                "Timezone hourly or weekday aggregates do not match the private source")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=ROOT / "site/data/timezones.json")
    parser.add_argument("--history", type=Path, default=ROOT / "site/data/history.json")
    parser.add_argument("--source", type=Path, help="Also independently audit against the private source directory")
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    history = json.loads(args.history.read_text(encoding="utf-8"))
    verify(data, history)
    if args.source:
        verify_source(data, history, args.source)
    print("PASS: timezone privacy allowlist, Central/Eastern dates, and daily/hourly/weekday totals verified."
          + (" Independent private-source audit passed." if args.source else ""))


if __name__ == "__main__":
    main()
