# Regional measurements v1

The regional extension uses the creek layer's identity, temporal, missingness and revision
primitives. It leaves `creek-measurements/v1`, `dist/water-state.json` schema 1, the source
SQLite store, collectors and daily routine unchanged. All commands are offline and use the
Python standard library. The browser consumes derived records, never provider fields.

## Reproduction and reader

```
python3 tools/regional_normalize.py --since 2026-09-01 --through 2026-10-03T12:15:00Z
python3 tools/regional_analytics.py
python3 -m unittest discover -s tests
```

Restore the local raw archive and the versioned `data/captures/` inputs first. A Git checkout
alone lacks current captures. Each source in `catalog.json` names its relative raw/capture
path, official URL, body hash, original retrieval time and provenance status. Missing archives
are listed; nothing fetches replacements. Historic Hydromet manifests include references to
files no longer on disk; those are gaps, not successful numeric coverage.

The ignored `data/normalized/regional-analytics/` contains a `regional-measurements/v1`
catalog, `observations.sqlite` and daily reference distributions. SQLite stores indexed
series/time/retrieval fields and zlib-compressed JSON records. `Reader(folder)` verifies its
hash and opens SQLite read-only. `reader.rows(series_id, resolved=False)` returns original
adapted records; default resolution chooses the latest retrieved capture within exactly one
series/time. Later null/rejected revisions remain authoritative. Conflicts remain flagged;
records from different sensors, operators or statistics never merge. `reader.choose` requires
a unique designated primary, or exactly one saved series. Always close the reader.

Daily USGS and TWDB reservoir observations from 2006 onward are retained for reusable
historical comparisons. Other point, rain and well observations are retained from `--since`;
the numeric audit inspects the whole available archive regardless of that retention window.
The archive audit counts original source rows, including repeated captures. The coverage
report counts resolved adapted observations. These are deliberately different denominators.
Unsupported USGS quantities remain in the archive audit. Unknown Hydromet headers remain
excluded with a reason. No raw record is edited.

## Meaning of each record

Every record retains provider, distributing feed, original site/series/field, original
value/unit/time, canonical quantity/unit, date or offset-qualified instant, statistic,
qualifiers, approval, retrieval time, source hash via the catalog and an exact body locator.
TWDB status letters remain untranslated. USGS last-modified dates and reservoir capacity
fields are retained. Date-only records never gain midnight instants. Missing, rejected,
nonfinite, negative rain/storage and ambiguous timestamps are unavailable; measured zero
remains numeric. Unknown datum, screen and continuity metadata remain unknown.

- Rain: inches; rolling 24-hour, since-midnight, cumulative counter, reported increment and
  daily total with unverified boundary are distinct series. Current rolling 24-hour records
  have explicit trailing boundaries. Native historical increments do not certify endpoints;
  no sum or reset correction is inferred. `rain_total` accepts only certified incremental,
  adjoining, complete intervals and rejects gaps, overlap, mixed sensors and negative resets.
- Discharge: ft³/s, separate from stage in feet. USGS instantaneous/daily mean and Hydromet
  reported point/hourly-unspecified remain separate. Hourly spacing never establishes a mean.
- Wells: depth below land surface and elevation are separate quantities. Increasing depth
  means a lower water level. Daily highs remain highs; point readings are not aggregated into
  days. TWDB's supplied timezone is used when present. Elevation datum and screen are unknown
  unless supplied; no historical elevation rank or pooled aquifer index is produced.
- Reservoirs: elevation, total storage, conservation storage and percent full are separate.
  The raw CSV defines percent full as conservation storage divided by conservation capacity;
  conservation storage is capped at that capacity. Capacity values are kept per date; survey
  version is unknown. Percent changes across changed capacities are withheld. No elevation
  is converted into volume, and storage change is never called measured inflow.

`change` requires compatible series, units, datum and sampling. Unknown elevation/stage
datum withholds differences; reported depth changes retain the lack of continuity certification.
`exact_day` requires that exact date; `at_or_before` never borrows a future reading or skips a
rejected latest observation and allows only 30 minutes of age by default.

## Seasonal discharge comparison

September 30, 2026 is the complete daily comparison date; it precedes the October 1 pulse.
Each daily discharge series uses its own Approved daily means in the same ±15 calendar-day
season from 2006–2025. Expected dates are enumerated in actual calendar years; February 29
exists only in leap years, and circular month/day distance handles year boundaries. A year
needs 80% coverage, the full 20-year pool needs 80%, and at least five years must qualify.
Counts and rejected years remain visible. Percentiles use midrank ties and include zero-flow
days. A zero median has no ratio. An instantaneous observation never receives a daily rank.
This describes saved daily records; it is not a trend, return period or forecast.

Groundwater, EAA springs with unknown approval, and managed reservoir elevations do not
receive this daily discharge rank. Their compatible reported levels/storage and endpoint
changes remain available, with missing endpoints and continuity limits explicit. Surface
watershed membership does not establish aquifer flow or causation.

## Reports

`docs/REGIONAL_COVERAGE.md` summarizes the generated reports. The committed
`data/model/regional-normalization-audit.json` gives full available archive numeric counts
by provider, station, field, sampling basis and year, plus gaps. `regional-coverage.json`
gives retained resolved coverage by basin (or explicitly unassigned), day, year, quantity,
quality, sampling interval and conflict. The website adds sourced surface geography without
changing measurement identities or pretending that inventory entries are observations.
