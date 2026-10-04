# Regional source coverage

Saved-data cutoff: 2026-10-03T12:15:00Z. Seasonal comparison: 2026-09-30. Generated offline; counts distinguish retained normalized records from full archive inspection.

| Provider | Quantity / sampling | Series | Numeric records | Unavailable |
|---|---|---:|---:|---:|
| EAA | discharge / daily_mean | 2 | 15159 | 1 |
| EAA | groundwater_depth / daily_high | 58 | 1480 | 0 |
| EAA | groundwater_elevation / daily_high | 58 | 1480 | 0 |
| Hydromet | discharge / hourly_unspecified | 10 | 7789 | 0 |
| Hydromet | discharge / reported_point | 130 | 18244 | 55839 |
| Hydromet | rain / cumulative_counter | 134 | 69568 | 0 |
| Hydromet | rain / daily_total_boundary_unverified | 124 | 4090 | 0 |
| Hydromet | rain / reported_increment | 134 | 69568 | 0 |
| Hydromet | rain / rolling_24h | 335 | 668 | 2 |
| Hydromet | rain / since_midnight | 335 | 668 | 2 |
| Hydromet | stage / hourly_unspecified | 10 | 7789 | 0 |
| Hydromet | stage / reported_point | 194 | 74193 | 18 |
| TWDB | conservation_storage / daily_report | 10 | 75526 | 1 |
| TWDB | groundwater_depth / daily_high | 128 | 300 | 0 |
| TWDB | groundwater_depth / reported_point | 89 | 85283 | 0 |
| TWDB | groundwater_elevation / daily_high | 1 | 30 | 0 |
| TWDB | percent_full / daily_report | 10 | 75526 | 1 |
| TWDB | reservoir_elevation / daily_report | 10 | 75503 | 24 |
| TWDB | storage / daily_report | 10 | 75526 | 1 |
| USGS | discharge / daily_mean | 67 | 444308 | 13 |
| USGS | discharge / instantaneous | 132 | 103189 | 0 |
| USGS | groundwater_depth / daily_mean | 3 | 12394 | 0 |
| USGS | groundwater_depth / instantaneous | 12 | 2981 | 0 |
| USGS | groundwater_depth / unknown_daily | 6 | 20993 | 0 |
| USGS | rain / daily_sum | 6 | 9230 | 0 |
| USGS | rain / unknown | 107 | 47220 | 1446 |
| USGS | reservoir_elevation / daily_mean | 30 | 140751 | 0 |
| USGS | reservoir_elevation / instantaneous | 35 | 10549 | 0 |
| USGS | stage / daily_mean | 80 | 409705 | 9 |
| USGS | stage / instantaneous | 191 | 141327 | 544 |

Full station, basin, date, year, spacing, quality and conflict distributions: `data/model/regional-coverage.json`. Original numeric source-row counts and source failures: `data/model/regional-normalization-audit.json`. Unassigned basin means no verified surface watershed association yet; aquifer connection is never inferred.

Rainfall event sums are withheld where interval boundaries are unverified. Rolling 24-hour observations stay separate. EAA rain/stream inventories are not measured coverage. Missing original EAA retrieval metadata is retained as a provenance gap. No local pilot spring is borrowed from another basin.
