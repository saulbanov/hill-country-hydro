# IDEAS — what this data layer could carry

Companion to **[`hill-country-hydro-system.md`](hill-country-hydro-system.md)** (purpose, layers, decisions,
open items). Everything below is a possible build, not a plan; nothing here is scheduled. Each idea names
the data it needs so it can be checked against the record described in the system document's
"What the record holds" section. Saul's framing, 2026-10-01: "what are some things I could build with this
new data layer, especially assuming I can get historical data."

The record today: 68 flow histories (Onion Creek at US 183 from 1924), 126 non-flow daily series (stage,
lake elevation, precipitation, well depth, water temperature), 22 wells with full records (J-17 from 1932),
ten lakes with full records (Lake Austin from 1940), the Edwards Aquifer Authority's wells and rain gauges
(history arriving slowly), NWS alerts and flood categories, and per-station event ledgers.

## Reporting products that could run on today's data

| Idea | What it shows | Needs | Notes |
|---|---|---|---|
| **Dry index** (daily) | Every gauge against its own same-date record; the headline "N of 68 gauges below their 10th percentile for this week"; a regional map colored by percentile | `hydro_context.py` seasonal percentile for the history tier; a page that groups by basin | The one most other ideas build on. The percentile is the station's, so no judgment is added. |
| **Spring and aquifer watch** | Jacob's Well dry-day counter; Comal and San Marcos spring flow beside J-17; Barton Springs beside Lovelady; the EAA critical-period stages beside the J-17 level | `app/groundwater.json`, `app/eaa.json`, the Comal, San Marcos, Jacob's Well and Barton series; the EAA stage table captured from their site | A restriction story with sourced numbers. The stage table and the 10-day averages are now captured daily (`eaa.py conditions`); the bundle's `eaa.critical_period` block carries the implied stage beside the EAA's stated one. |
| **Lake storage ledger** | Travis, Buchanan, Canyon, Medina percent full, 30-day change, and how far inflows run behind | `app/reservoirs.json` and the full lake CSVs; the Llano and Pedernales flows as inflow proxies | The lake records are daily back to the 1940s; 2011 and 2022 are the comparison droughts, and any date can be compared. |
| **Flood anatomy, per event** | When a creek crosses its threshold: the hydrograph, the peak, its rank in the station's whole record, time from rain to peak | event ledgers; the instantaneous captures (daily means hide peaks); EAA and USGS rain gauges | The July 2026 floods are already in the data and would be the first case. |
| **Water temperature notes** | The 8 live temperature series; Barton Springs' constancy against creek swings | `usgs_series_history.py` temperature series | Heat-season context. |

## What the history unlocks

| Idea | What it answers | Needs | Caveat |
|---|---|---|---|
| **Event catalog** | Every rise above its station's 95th percentile since records began, searchable by creek and year | `event_ledger.py` over all history-tier stations; a small browser | "Worst since" claims become checkable. Thresholds are per station, so events are comparable within a station, not across. |
| **Recession curves** | After a one-inch rain, how many days until Bull Creek is back to zero; whether that has shortened by decade | ledger events + rain gauges; daily means | Also the engine behind the swim lens's hypotheses. |
| **Zero-flow trends** | Annual count of dry days per creek by decade | the daily CSVs (`value == 0` rows, with missing days kept absent) | Station moves and rating changes must be read from the manifests first. |
| **Aquifer-to-spring lag** | How many weeks the J-17 level leads Comal's flow; Lovelady vs Barton Springs | well records + spring/river daily means; a cross-correlation by lag | Measured, not assumed; report the lag with its strength. |
| **Urban flashiness** | Rise-and-fall speed of Walnut, Shoal, Williamson across the decades Austin grew | the Austin-tier daily means and instantaneous windows | Needs the station history (rebuilds, channel work) alongside. |
| **Return periods** | Flood-frequency estimates for peaks at long-record stations | annual peak series from the daily or instantaneous records | State the method; expect it to be contested, which is the point. |
| **First-dry-day tracker** | The date each creek first reads zero each year, and how it moves | daily CSVs | Simple, visual, and tied to the dry index. |
| **Well recovery times** | How long after a wet month a well regains a foot | the 22 full well records + rain | Per aquifer; Trinity and Edwards behave differently. |

## Infrastructure products

- **Station pages**: one static page per site (218) with record span, percentile, events, data health, sources. A public reference people can link to. Generated from the bundle and the ledgers.
- **Threshold-crossing feed**: the ledgers already define event starts and ends; an RSS/JSON feed of crossings would need Saul's authorization because the project bans notifications until then.
- **The bundle as a public dataset**: `dist/water-state.json` and the history CSVs served statically for other maps and newsrooms.
- **A "same day in" explorer**: this date against 2011, 2022, any year, per station.
- **The swim lens's hypothesis list**: generated from the ledgers' and relationships' gaps (described in the swim repo's plan).

## Caveats that apply to all of it

- USGS daily values stay provisional for months; ratings get revised; a number can change after it is cited.
- Daily means hide peaks; flood stories must use the instantaneous captures.
- Stations move and get rebuilt; a long trend needs the station's own history read from USGS before it is trusted.
- The EAA server throttles bulk pulls, so its history arrives over weeks, not hours.
- Nothing here measures bacteria or safety. A lens that claims either must bring its own evidence.

## If only one thing gets built

The dry index map and the event catalog. The first is the daily product; the second is the historical spine the others reuse.
