# Regional station histories

`regional-measurements/v1` keeps a compact recent store: daily USGS, reservoir and spring records
from 2006 and everything else from September 1, 2026. That store is unchanged. This document covers
the second store beside it, which holds the whole preserved record for the pilot stations.

## Reproduction

```
python3 tools/regional_history.py select     # name the stations (writes data/model/regional-history-stations.json)
python3 tools/regional_history.py build      # data/normalized/regional-history/ (ignored; about 4 GB)
python3 tools/regional_history.py audit      # data/model/regional-history-continuity.json, docs/REGIONAL_HISTORY_TABLE.md
python3 tools/regional_history.py show '<series id>' 1952-09-11   # one stored record with its capture hash and body locator
```

All four commands are offline. `build` runs the same adapters as the compact store with the
retention gates opened (`daily_start` and `since` set to the year 1) and adaptation limited to the
named stations before any body is read. Hydromet history is limited to the daily rain windows; the
hourly flow and lake-level windows for the same sites are not adapted here. The output has the same
catalog and SQLite layout, so `regional_analytics.Reader` opens it without change.

## What it holds

179 named stations: the four pilot river gauges, the six Austin creek gauges, the six Highland Lakes reservoirs, 37 TWDB wells
whose coordinates fall inside a pilot WBD subbasin, 121 LCRA rain gauges inside those subbasins that
have a saved daily-rain history, and five springs outside the pilot watersheds kept as separate
regional context. The October 3 build holds 4,444,641 original records in 588 series.

First and last preserved values (full table: `docs/REGIONAL_HISTORY_TABLE.md`):

| Record | First | Last | Notes from the audit |
|---|---|---|---|
| Llano River near Junction, daily mean discharge | 1915-10-01 | 2026-09-30 | No values 1993-05-10 to 1997-10-01 (1,604 days) |
| Llano River at Llano, daily mean discharge | 1939-09-17 | 2026-09-30 | Longest gap 13 days (2023) |
| Pedernales River near Fredericksburg, daily mean discharge | 1979-06-28 | 2026-09-30 | No values 1993-05-03 to 1998-03-16 (1,777 days) |
| Pedernales River near Johnson City, daily mean discharge | 1939-05-04 | 2026-09-30 | No gap |
| Austin creek gauges, daily mean discharge | 1924 (Onion) to 1983 (Shoal) | 2026-09-30 | Onion lacks 16,864 days and Williamson 7,632; Shoal's daily record stops 2026-09-02 |
| Lake Buchanan storage | 1937-06-30 | 2026-10-02 | 73 stated conservation-capacity values |
| Lake Travis storage | 1940-09-30 | 2026-10-02 | 2 stated capacity values |
| Lake LBJ storage | 1951-08-01 | 2026-10-02 | 2 stated capacity values |
| Inks, Marble Falls and Lake Austin storage | 1966-01-01 | 2026-10-02 | All six lakes lack reports 2016-01-29 to 2016-03-04 |
| Comal Springs (EAA daily mean) | 1927-12-19 | 2026-10-02 | Approval unknown, so no daily rank |
| Daily rain totals, 121 gauges | 1988 (5 gauges) | 2026-10-03 | 59 gauges report by 2000, 121 by 2026 |
| TWDB wells, 26 with a captured record | 1993-01-26 | 2026-10-01 | One well reports before 2001; 21 report in 2026 |

For USGS daily discharge the provider's declared series start equals the first preserved value at
all four gauges. A first preserved value is still not the first measurement ever made at a site.

## Gaps that are named, not filled

- **Eleven pilot wells have no captured record.** TWDB lists a full record for each (2.5 to 34.6 MB),
  but the collection rule kept only wells with a daily-feed row at most seven days old. They are
  recoverable with one request each to `waterdatafortexas.org/groundwater/well/<id>.json`; the list
  with sizes is in `regional-history-continuity.json` under `unfetched_well_histories`.
- **924 Hydromet windows are named by a manifest but have no body on disk**, in 28 site and
  parameter groups (hourly flow and lake level, plus early daily rain at five sites). The manifest
  kept each window's hash and record count; the gzip was not preserved. Each is one bounded request
  through `tools/hydromet.py`. None was re-requested, and none counts as coverage. The pilot rivers
  and lakes have USGS and TWDB daily records for the same water, so the pilot does not depend on them.
- **Sensor, gauge-location and method changes** are not documented in the preserved bodies. Each
  series lists what is known (one provider series identifier across the span; stated capacity
  values and the dates they change) and what is unknown (survey versions, datum where not supplied,
  screen intervals, pumping influence). No era boundary is drawn without such a stated value.

## Summaries

`aggregate(rows, 'year' | 'month')` accepts one daily series. A period needs 90% of its calendar
days; below that it reports days and coverage and no value. Daily means produce a mean of daily
means; other daily statistics produce a median, minimum and maximum. Point readings are never
turned into daily values. Daily rain totals are never summed: the provider's day boundary is
unverified and a missing day is not zero rain.

## The baseline is fixed; the display range is free

The range of years a reader looks at never changes what "usual" means. `FixedBaseline` ranks any
date's daily mean discharge against one reference: the same series' Approved daily means within
±15 calendar days in 2006–2025, under the gates of the compact layer (80% of a year's window dates,
80% of all expected dates, five qualifying years, midrank ties, zero flow kept).

- A date **after** the reference era is ranked against all twenty years.
- A date **inside** the era is ranked against the other nineteen years. Its whole year is left out,
  so an observation is never in its own reference.
- A date **before** the era is ranked against the same fixed distribution and labelled: the
  percentile says where that day would fall among recent days at the same gauge, and continuity
  between the eras is not certified.
- A date with no measured daily mean has no rank, and `exact()` returns nothing for it. The nearest
  or latest reading is never substituted.
- Instantaneous readings, mixed sensors and series without Approved values get no rank.

`tests/test_regional_history.py` checks the fast baseline against
`regional_analytics.seasonal_reference(..., reference_years=(2006, 2025), exclude_year=...)`.

## Earlier floods at the same gauge

`tools/regional_events.py` writes `data/model/regional-events.json` for the four river gauges. It
keeps two records apart:

- **Annual peaks.** The preserved USGS peak-flow file gives one instantaneous peak per water year,
  with qualification codes whose meanings are read from the file's own header (5 and 6 mark
  regulation or diversion; gage-height code 6 marks a datum change in that year).
  `place_among_peaks` counts how many published peaks exceed one instantaneous reading. It is used
  for the storm's largest saved reading, which is the same kind of value. The count is a place in
  the record. It is not a return period, the storm's true peak may be higher than the largest
  saved reading, and the current water year's peak is not yet published.
- **Daily events.** `daily_events` lists the largest daily means, each the largest within seven
  days either side, with the daily mean three days earlier and the number of following days at or
  above half the peak. A missing day inside that count withholds it. `pair_lags` reports the date
  difference between upstream and downstream events only where exactly one upstream event lies
  within three days; daily values cannot resolve hours.

On the October 3 build: 31 of 105 published annual peaks at Llano near Junction exceed the storm's
35,000 cfs; 40 of 87 at Llano exceed 27,500 cfs; all 41 at Pedernales near Fredericksburg exceed
15.1 cfs; 85 of 86 near Johnson City exceed 105 cfs. The storm's daily means are not in the saved
record yet (the last daily mean is September 30), so it does not appear in the daily-event lists.

## Rebuilding for a later cutoff

```
python3 tools/regional_rebuild.py --through 2026-10-10T12:15:00Z
python3 -m unittest discover -s tests
python3 tools/package_regional_site.py --site-root ../hill-country-hydro-site
```

The first command reruns every offline stage for one saved-data cutoff: compact store, coverage
audit, full-history store, continuity audit, earlier floods, history partitions, geology, snapshot.
It reads only what the daily run has already captured and fetches nothing. The storm window on the
page follows the cutoff (its daily end is the last whole date before it); the seasonal view stays
on September 30. Run at the October 3 cutoff it reproduces the committed outputs. Several tests pin
October 3 values (selection counts, the 31-of-105 placement, the unranked gap dates); a later
cutoff is expected to change the first two, and those assertions should be updated to the new
audited values in the same commit.

## Browser partitions

`tools/regional_history_package.py` writes one file per station under `app/history/` and an index.
The map loads the index and then one station file on request; it never downloads the archive or the
SQLite store. A daily series with at least half its span present is a dense array with nulls for
missing days; a sparse one is dated pairs. A point series over 6,000 readings is packaged as the
last reading of each UTC date and says so; every reading remains in the offline store. Each file
carries the continuity block, yearly summaries, capture hashes and official request URLs.
