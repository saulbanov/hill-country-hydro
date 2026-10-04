# Regional geography evidence

Surface geography for the pilot comes from two U.S. Geological Survey services, captured verbatim on
October 3–4, 2026 (UTC) into `data/captures/documentary/regional-water/` with a `.meta.json` beside
each body (URL, retrieval time, HTTP status, SHA-256, byte count). `tools/regional_geography.py`
derives everything below from those bytes and makes no request. Both products are in the public domain.

| Capture | Service | Holds |
|---|---|---|
| `regional-channels-ordered`, `regional-channels-page2` | NHD high-resolution map service, flowline layer | Llano, North Llano, South Llano, Pedernales and Colorado rivers and Sandy Creek, by GNIS name |
| `reservoir-channel-paths` | same layer | Artificial paths inside the reference lake polygons, by NHD waterbody identifier |
| `regional-basins` | Watershed Boundary Dataset, HUC8 layer | Six subbasins with codes beginning 120902 |
| `regional-lakes`, `regional-other-lakes` | NHD waterbody layer | Named reference lake outlines |
| `nhd-service`, `nhd-flow-layer`, `wbd-service`, `wbd-basin-layer` | service and layer descriptions | Field definitions, including flow direction |

## What was derived

- **2,712 channel pieces**, all with NHD flow direction 1 (with the digitized direction).
- **Six surface subbasins**: North Llano (12090202), South Llano (12090203), Llano (12090204),
  Pedernales (12090206), Buchanan–Lyndon B. Johnson Lakes (12090201), Austin–Travis Lakes (12090205).
- **Five reference lake outlines**: Buchanan, Lyndon B. Johnson, Marble Falls, Travis, Austin. The
  named waterbody responses hold no Inks Lake polygon, and none was drawn.

## Connectivity

Pieces connect only where saved endpoints match to six decimal places. Nothing is bridged. The
network has 453 junctions of three or more pieces and five connected components:

| Pieces | Contents | Reading |
|---:|---|---|
| 2,656 | Llano system, Pedernales, Colorado, reservoir paths, Sandy Creek | The connected pilot network |
| 28 | Sandy Creek, HUC 12090204 | A different stream of the same name inside the Llano subbasin; its connecting tributaries were not requested |
| 25 | Sandy Creek, HUC 12090109 | A stream of the same name outside the pilot |
| 2 and 1 | Colorado River, HUC 12090205 and 12090201 | Short pieces whose endpoints match no other saved piece |

The four small components are unresolved, drawn as context, and carry no gauge.

## Gauge positions

Each pilot gauge is associated with a channel piece only when the provider's station name contains
the river name, the gauge lies inside one WBD subbasin, and a piece of that name in that subbasin
lies within 250 m. All four qualify, at 21.4 to 95.1 m (`data/model/regional-gauge-associations.json`).
The association is a position. It does not extend the reading along the reach.

## Receiving reservoirs

`downstream_route` walks the saved pieces from each gauge's piece, start to end, and stops at a
divergence, a dead end or a loop. A reservoir is named only where the walk enters an artificial path
carrying the NHD waterbody identifier of a saved reference lake outline.

| Gauge | Pieces walked | First reference lake reached | Then |
|---|---:|---|---|
| Llano River near Junction (08150000) | 649 | Lake Lyndon B. Johnson | Marble Falls, Travis, Austin |
| Llano River at Llano (08151500) | 341 | Lake Lyndon B. Johnson | Marble Falls, Travis, Austin |
| Pedernales River near Fredericksburg (08152900) | 531 | Lake Travis | Austin |
| Pedernales River near Johnson City (08153500) | 289 | Lake Travis | Austin |

No walk met a divergence. Each ended at the downstream edge of the saved network on the Colorado
River. The walk establishes the mapped route. It says nothing about travel time, losses along the
way, or how much of a reservoir's storage change came from that river. A walk started inside Lake
Buchanan reaches Lake Lyndon B. Johnson next, so Buchanan lies upstream on the same saved network and
no pilot gauge's route enters it. Inks Lake has no saved outline, so its place on the route is not
derived here.

## Austin creeks: a named group

The six gauged creeks of the Austin prototype (Bull, Barton, Shoal, Walnut, Williamson, Onion) are
on the same map as a named group. It is not a watershed outline: no creek-level WBD polygon is
captured. USGS station metadata places all six gauges in HUC8 12090205. Their channel lines are the
OpenStreetMap ways of the creek prototype, and each gauge's position evidence (7.4 to 76.2 m from
its named way) comes from `data/model/creek-gauge-associations.json`. Those ways are not part of the
captured NHD network, so no downstream route or receiving reservoir is derived for them. The rain
gauges shown with the group are the City of Austin network, grouped by operator.

## Gauge strokes

`gauge_stroke` draws at most 500 m each side of a gauge along the one saved line the gauge is
associated with. It stops at the end of that line and never continues onto another piece. The
stroke's width and color come from `data/model/regional-display-policy.json`: the largest saved
instantaneous reading in the storm window minus the same gauge's seasonal median daily mean, in one
band per factor of ten. It marks the gauge. It is not a measured or inferred reach, and the
contrast is not a rank of the peak.

## Dam labels

Reservoir labels sit at the LCRA Hydromet dam site whose own site name states the lake in
parentheses (for example "Mansfield Dam (Lake Travis)"). An earlier draft keyed them to hand-typed
site numbers that named other gauges; `tests/test_regional_pilot.py` now checks each pairing.

## Limits

The NHD service is a legacy product and not a current channel survey. WBD polygons are surface
drainage and are not aquifer boundaries. Lake outlines are reference shapes and not today's water
extent. Line width and color on the map are symbols and do not show channel width, depth or flooding.
