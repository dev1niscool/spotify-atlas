#!/usr/bin/env python3
"""Regression checks for timezone boundaries and public aggregate safety."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from build_data import build as build_history
from build_timezones import build
from verify_timezones import verify, verify_source


def event(stamp, **overrides):
    return {
        "ts": stamp, "ms_played": 30_000, "incognito_mode": False,
        "spotify_track_uri": "spotify:track:" + "a" * 22,
        "master_metadata_track_name": "Fixture track",
        "master_metadata_album_artist_name": "Fixture artist",
        "master_metadata_album_album_name": "Fixture album",
        **overrides,
    }


class TimezoneTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name)

    def make(self, events):
        (self.source / "Streaming_History_Audio_test.json").write_text(json.dumps(events), encoding="utf-8")
        history = build_history(self.source)
        result = build(self.source)
        verify(result, history)
        return result, history

    def test_spring_forward_skips_missing_hour(self):
        cases = (
            (("2026-03-08T07:59:59Z", "2026-03-08T08:00:00Z"), {1: 1, 3: 1}, {3: 1, 4: 1}),
            (("2026-03-08T06:59:59Z", "2026-03-08T07:00:00Z"), {0: 1, 1: 1}, {1: 1, 3: 1}),
        )
        for stamps, central, eastern in cases:
            with self.subTest(stamps=stamps):
                data, _ = self.make([event(stamp) for stamp in stamps])
                for zone, expected in zip(data["zones"], (central, eastern)):
                    hours = zone["rhythms"][0]["hours"]
                    self.assertEqual({i: pair[0] for i, pair in enumerate(hours) if pair[0]}, expected)
                    self.assertEqual(hours[2], [0, 0])

    def test_fall_back_counts_both_repeated_hours(self):
        cases = (
            (("2026-11-01T06:30:00Z", "2026-11-01T07:30:00Z"), {1: 2}, {1: 1, 2: 1}),
            (("2026-11-01T05:30:00Z", "2026-11-01T06:30:00Z"), {0: 1, 1: 1}, {1: 2}),
        )
        for stamps, central, eastern in cases:
            with self.subTest(stamps=stamps):
                data, _ = self.make([event(stamp) for stamp in stamps])
                for zone, expected in zip(data["zones"], (central, eastern)):
                    hours = zone["rhythms"][0]["hours"]
                    self.assertEqual({i: pair[0] for i, pair in enumerate(hours) if pair[0]}, expected)
                    self.assertEqual(sum(pair[1] for pair in hours), 60_000)

    def test_local_midnight_and_year_change_dates_and_weekdays(self):
        data, _ = self.make([event("2025-01-01T05:30:00Z"), event("2026-07-04T04:30:00Z")])
        central, eastern = data["zones"]
        self.assertEqual(central["days"], [["2024-12-31", 1, 30_000], ["2026-07-03", 1, 30_000]])
        self.assertEqual(eastern["days"], [["2025-01-01", 1, 30_000], ["2026-07-04", 1, 30_000]])
        self.assertEqual(central["years"], [2024, 2026])
        self.assertEqual(eastern["years"], [2025, 2026])
        for zone, weekdays in ((central, (1, 4)), (eastern, (2, 5))):
            for rhythm, weekday in zip(zone["rhythms"], weekdays):
                self.assertEqual(rhythm["weekdays"][weekday], [1, 30_000])
                self.assertEqual(sum(pair[0] for pair in rhythm["weekdays"]), 1)

    def test_qualification_matches_history_and_private_fields_stay_private(self):
        stamp = "2026-07-04T04:30:00Z"
        valid = event(stamp, private_fixture_field="must never be published")
        rows = [valid, event(stamp, ms_played=60_000)]
        rows += [event(stamp, **change) for change in (
            {"incognito_mode": True}, {"incognito_mode": None}, {"incognito_mode": 0},
            {"ms_played": 29_999}, {"ms_played": True}, {"ms_played": -1}, {"ms_played": "30000"},
            {"spotify_track_uri": "spotify:episode:" + "a" * 22},
            {"spotify_track_uri": "spotify:track:" + "a" * 22 + "\n"},
            {"ts": "invalid"}, {"ts": "2026-07-04T04:30:00"}, {"ts": None},
            {"master_metadata_track_name": " "}, {"master_metadata_album_artist_name": None},
            {"master_metadata_album_album_name": 10},
        )]
        rows += [None, "not a record"]
        (self.source / "Streaming_History_Video_test.json").write_text(json.dumps([valid]), encoding="utf-8")
        data, history = self.make(rows)
        self.assertEqual(history["meta"]["qualifiedEvents"], 2)
        self.assertEqual(history["meta"]["totalMs"], 90_000)
        verify_source(data, history, self.source)
        serialized = json.dumps(data)
        self.assertNotIn("private_fixture_field", serialized)
        self.assertNotIn("must never be published", serialized)
        self.assertNotIn(stamp, serialized)

    def test_verifier_rejects_private_fields_and_inconsistent_buckets(self):
        data, history = self.make([event("2026-07-04T04:30:00Z")])
        mutations = (
            lambda value: value.update({"private_field": "forbidden"}),
            lambda value: value["zones"][0].update({"label": "Unexpected label"}),
            lambda value: value["zones"][0]["period"].update({"start": "2026-07-03T23:30:00"}),
            lambda value: value["zones"][0]["rhythms"][0]["hours"].__setitem__(0, [1, 30_000]),
            lambda value: value["zones"][0]["rhythms"][0].update({"weekdays": [[1, 30_000]] + [[0, 0]] * 6}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                changed = deepcopy(data)
                mutate(changed)
                with self.assertRaises(ValueError):
                    verify(changed, history)


if __name__ == "__main__":
    unittest.main()
