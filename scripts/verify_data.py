#!/usr/bin/env python3
"""Audit the published dataset's privacy allowlist and aggregate consistency."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PRECISE_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
TRACK_ID = re.compile(r"[A-Za-z0-9]{22}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def keys(value, expected, label):
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == set(expected.split()), f"{label} violates the key allowlist")


def number(value, label, minimum=0):
    require(type(value) is int and value >= minimum, f"{label} must be an integer >= {minimum}")


def catalog_text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label} must contain text")
    require(not any(pattern.search(value) for pattern in (EMAIL, IPV4, PRECISE_TIMESTAMP)),
            f"{label} contains an email, IP address, or precise timestamp")


def valid_pair(value, label, allow_empty=True):
    require(isinstance(value, list) and len(value) == 2, f"{label} must be [plays, ms]")
    number(value[0], label + " plays", 0 if allow_empty else 1)
    number(value[1], label + " duration")
    require(value[1] >= value[0] * 30_000, f"{label} includes an under-threshold duration")
    require(value[0] > 0 or value[1] == 0, f"{label} has duration without any plays")


def verify(data):
    keys(data, "meta artists tracks months days rhythms", "root")
    meta = data["meta"]
    keys(meta, "name timezone minPlayMs weekdayOrder period years sourceEvents qualifiedEvents totalMs activeDays excluded playlists", "meta")
    require(meta["name"] == "Devin", "Only the authorized name Devin may be published")
    require(meta["timezone"] == "UTC", "Listening rhythms must be explicitly UTC")
    require(meta["minPlayMs"] == 30_000, "Qualifying duration must remain 30 seconds")
    require(meta["weekdayOrder"] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], "Weekday labels are incorrect")
    require(meta["playlists"] == [], "This export has no playlists")
    keys(meta["period"], "start end", "period")
    for value in meta["period"].values():
        require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "Period must use dates only")
        date.fromisoformat(value)
    for field in ("sourceEvents", "qualifiedEvents", "totalMs", "activeDays"):
        number(meta[field], field)
    keys(meta["excluded"], "video nonMusic incognito under30Seconds invalidDuration invalidTimestamp missingMetadata", "excluded")
    for reason, value in meta["excluded"].items():
        number(value, "excluded " + reason)
    require(meta["sourceEvents"] == meta["qualifiedEvents"] + sum(meta["excluded"].values()), "Source exclusions do not reconcile")

    artists, tracks = data["artists"], data["tracks"]
    require(isinstance(artists, list) and bool(artists), "Artists must be a nonempty array")
    for name in artists:
        catalog_text(name, "artist name")
    require(len(set(artists)) == len(artists), "Duplicate artist index entries")
    require(isinstance(tracks, list) and bool(tracks), "Tracks must be a nonempty array")
    track_ids = set()
    for track in tracks:
        keys(track, "title artist album spotifyId", "track")
        catalog_text(track["title"], "track title")
        catalog_text(track["album"], "album title")
        number(track["artist"], "track artist index")
        require(track["artist"] < len(artists), "Track artist index is out of range")
        require(isinstance(track["spotifyId"], str) and TRACK_ID.fullmatch(track["spotifyId"]), "Invalid catalog Spotify track ID")
        require(track["spotifyId"] not in track_ids, "Duplicate Spotify track ID")
        track_ids.add(track["spotifyId"])

    require(isinstance(data["months"], list) and bool(data["months"]), "Months must be a nonempty array")
    month_totals = {}
    year_totals = defaultdict(lambda: [0, 0])
    indexed_tracks = set()
    indexed_artists = set()
    previous = None
    for month in data["months"]:
        keys(month, "month plays ms artists tracks", "month")
        label = month["month"]
        require(isinstance(label, str) and re.fullmatch(r"\d{4}-\d{2}", label), "Month must use YYYY-MM")
        date.fromisoformat(label + "-01")
        require(previous is None or previous < label, "Months must be unique and sorted")
        previous = label
        valid_pair([month["plays"], month["ms"]], "month totals")
        derived_artists = defaultdict(lambda: [0, 0])
        derived_totals = [0, 0]
        last_index = -1
        require(isinstance(month["tracks"], list), "Month tracks must be an array")
        for row in month["tracks"]:
            require(isinstance(row, list) and len(row) == 3, "Month track row must be [index, plays, ms]")
            index, plays, ms = row
            number(index, "month track index")
            require(last_index < index < len(tracks), "Month tracks must have sorted, unique valid indexes")
            last_index = index
            valid_pair([plays, ms], "month track", allow_empty=False)
            artist = tracks[index]["artist"]
            derived_artists[artist][0] += plays
            derived_artists[artist][1] += ms
            derived_totals[0] += plays
            derived_totals[1] += ms
            indexed_tracks.add(index)
            indexed_artists.add(artist)
        require(derived_totals == [month["plays"], month["ms"]], "Month track totals do not reconcile")
        expected = [[index, *totals] for index, totals in sorted(derived_artists.items())]
        require(month["artists"] == expected, "Month artist totals do not reconcile")
        month_totals[label] = derived_totals
        year_totals[int(label[:4])][0] += derived_totals[0]
        year_totals[int(label[:4])][1] += derived_totals[1]
    require(indexed_tracks == set(range(len(tracks))), "Unreferenced track metadata")
    require(indexed_artists == set(range(len(artists))), "Unreferenced artist metadata")

    day_month_totals = defaultdict(lambda: [0, 0])
    weekday_totals = defaultdict(lambda: [[0, 0] for _ in range(7)])
    require(isinstance(data["days"], list) and bool(data["days"]), "Days must be a nonempty array")
    previous = None
    for row in data["days"]:
        require(isinstance(row, list) and len(row) == 3, "Daily row must be [date, plays, ms]")
        label, plays, ms = row
        require(isinstance(label, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", label), "Daily aggregation must use dates only")
        day = date.fromisoformat(label)
        require(previous is None or previous < label, "Days must be unique and sorted")
        previous = label
        valid_pair([plays, ms], "day", allow_empty=False)
        day_month_totals[label[:7]][0] += plays
        day_month_totals[label[:7]][1] += ms
        weekday_totals[day.year][day.weekday()][0] += plays
        weekday_totals[day.year][day.weekday()][1] += ms
    require(len(data["days"]) == meta["activeDays"], "Active day count does not reconcile")
    require(meta["period"] == {"start": data["days"][0][0], "end": data["days"][-1][0]}, "Period does not match daily aggregation")
    for month, totals in month_totals.items():
        require(totals == day_month_totals[month], "Daily and monthly totals do not reconcile")
    require(set(day_month_totals) <= set(month_totals), "Daily data exists outside monthly range")
    years = sorted(year for year, totals in year_totals.items() if totals[0])
    require(meta["years"] == years, "Year list does not reconcile")
    require(sum(total[0] for total in year_totals.values()) == meta["qualifiedEvents"], "Published play counts do not reconcile")
    require(sum(total[1] for total in year_totals.values()) == meta["totalMs"], "Published durations do not reconcile")
    require(isinstance(data["rhythms"], list) and len(data["rhythms"]) == len(years), "Rhythms must contain each year")
    for expected_year, rhythm in zip(years, data["rhythms"]):
        keys(rhythm, "year weekdays hours", "rhythm")
        require(rhythm["year"] == expected_year, "Rhythms must have sorted, unique years")
        for field, size in (("weekdays", 7), ("hours", 24)):
            require(isinstance(rhythm[field], list) and len(rhythm[field]) == size, f"Invalid {field} dimension")
            for value in rhythm[field]:
                valid_pair(value, field)
            totals = [sum(row[0] for row in rhythm[field]), sum(row[1] for row in rhythm[field])]
            require(totals == year_totals[expected_year], f"{field} totals do not reconcile")
        require(rhythm["weekdays"] == weekday_totals[expected_year], "Weekday totals do not match UTC dates")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=ROOT / "site/data/history.json")
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    verify(data)
    print(f"PASS: privacy allowlist, catalog metadata, and all aggregate totals verified ({data['meta']['qualifiedEvents']:,} plays).")


if __name__ == "__main__":
    main()
