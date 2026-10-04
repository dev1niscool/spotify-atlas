# On Repeat — Devin’s listening atlas

[Open the listening atlas](https://dev1niscool.github.io/spotify-atlas/)

An interactive portrait of music listening from April 2020 to September 2026. A flowing artist timeline, year filters, top artists and searchable tracks, a daily calendar, a UTC listening clock, and a downloadable listening receipt.

## Run locally

```sh
python3 -m http.server 8765 --directory site
```

Open http://localhost:8765. The site is static HTML, CSS, and JavaScript. D3 7.9.0 is vendored, with its license, so no external scripts, fonts, analytics, cookies, API keys, or login are needed. Track links open Spotify only when selected.

## Privacy and methodology

The original Spotify exports are **not included** in this repository or the deployment. The public JSON is generated using an explicit allowlist. It retains Devin’s first name, public artist/track/album metadata and Spotify track IDs, monthly artist/track totals, daily totals, and annual hour/weekday aggregates. No individual listening-event rows are published.

Account details, IP addresses, countries, devices, exact timestamps, private-session plays, video files, and nonmusic records are excluded. No playlist records were present. Daily/hourly patterns remain publicly visible as aggregates. All dates and hours use UTC; no home location or time zone is inferred.

A qualified listen is an audio music record with a valid Spotify track ID, lasting at least 30 seconds, outside a private session. Listening time sums reported durations of qualifying records only. Short skips do not count. Track versions with different Spotify IDs are separate tracks. Partial first/last years and missing days reflect the export, not inferred activity.

The river shows the ten leading artists in the selected period by default. “Include other artists” adds the rest of the collection as one group. Layer thickness encodes the selected metric. Curves interpolate monthly observations; tooltips report actual month totals. Calendar intensity is scaled within its chosen year. The receipt always ranks by play count, regardless of the chart metric or artist selection.

## Regenerate and audit

Keep the source directory outside the repository. By default, the builder reads the sibling `Spotify Extended Streaming History` directory.

```sh
python3 scripts/build_data.py
python3 scripts/verify_data.py
```

The auditor checks an exact schema, private identifiers, catalog indices, valid dates, and consistent totals across monthly, daily, and rhythm aggregates. The GitHub Pages workflow audits the public JSON before deploying only the `site` directory. Raw source files are not needed by the workflow.

## Inspiration

- [Lee Byron & Martin Wattenberg’s Streamgraph](https://leebyron.com/streamgraph/): flowing music histories.
- [Receiptify](https://receiptify.herokuapp.com/about.html): rankings as a familiar keepsake.
- [The Pudding’s music history](https://pudding.cool/2017/03/music-history/): navigable musical timelines.
- [Dear Data](https://www.dear-data.com/theproject): expressive stories from everyday data.
- [Spotify Wrapped](https://newsroom.spotify.com/2025-12-03/2025-wrapped-user-experience/): prominent personal statistics.
- [volt.fm](https://volt.fm/): listening habits across hours and days.

Original implementation; no source code or branding copied from the references. Independent personal project, unaffiliated with Spotify.
