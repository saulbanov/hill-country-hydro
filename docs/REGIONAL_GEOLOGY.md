# Regional geology evidence

Everything in the geology layer is mapped or published interpretation. None of it is an instrument
reading, and the map keeps it visually apart from gauge observations and from the surface
watersheds. `tools/regional_geology.py` derives it offline from 80 verbatim captures in
`data/captures/documentary/regional-geology/` (each with URL, retrieval time, status, SHA-256 and
size); `ACQUISITION_NOTES.md` in that folder lists every capture and every source that was probed
and not captured, with the reason.

## Sources and their stated terms

| Layer | Source | Scale, date, terms as stated by the source |
|---|---|---|
| Aquifer extents | TWDB major and minor aquifer layers, queried for the pilot rectangle | Major aquifers "Updated December 2006", minor "Updated December 2017" on the TWDB GIS data page; the major-aquifer shapefile metadata states source scale 1:250,000 and no use restrictions. The ArcGIS layers themselves state no date, scale or terms. |
| Faults and surface rock units | Geologic Atlas of Texas (Bureau of Economic Geology 1:250,000 sheets) as digitized and served by TWDB | 1,593 fault lines and 7,285 unit polygons in the pilot rectangle; the Texas Geographic Information Office lists the scanned atlas sheets as CC0-1.0 |
| Cross-sections and quoted relationships | USGS Ground Water Atlas of the United States, HA 730-E (Ryder, 1996) | USGS-authored information is in the U.S. public domain (captured USGS copyrights-and-credits page) |
| Well depth, aquifer code, casing | TWDB Groundwater Database well reports, one per pilot well | TWDB disclaimer captured with each report |

## Outcrop and subsurface

TWDB codes each aquifer polygon 1 or 2 and does not say in the layer or shapefile metadata what the
codes mean. Before using them the tool checked them against the atlas: for every coded polygon of
the three Llano Uplift minor aquifers it took a point inside the polygon and read the surface rock
unit mapped there. **109 of 163 code-1 polygons sit on a surface unit of the aquifer's own
formations; 0 of 152 code-2 polygons do.** The layer therefore treats 1 as outcrop and 2 as
subsurface extent, and the counts ride in `data/model/regional-geology.json`.

## Wells

For each of the 37 pilot wells the tool keeps TWDB's aquifer assignment (the measurement feed's
name and the Groundwater Database code agree for all 37), the well depth and its source, and every
casing row. A screen or open interval is documented for 23 wells. Three have casing rows and no such
interval. Eleven have no completion rows at all, and no interval is assumed for them. Owner and
driller names in the captured reports are not carried into any derived file.

Each well also gets the rock unit mapped at the surface at its coordinates, labelled as surface
rock. It is often a different unit from the aquifer: well 5750108 is assigned to the
Ellenburger-San Saba aquifer with an open hole from 112 to 360 ft, and the rock mapped at the
surface there is Cretaceous Hensell Sand. The surface polygon never sets or changes an assignment.

## What changes with the selected station

The geology panel follows the station chosen on either map. For each of the 445 catalogued
stations with coordinates inside the pilot rectangle the tool looks up the surface rock unit (from
the unsimplified atlas polygons) and every TWDB aquifer extent that covers the point (from the
extents simplified to about 150 m, so a point near a boundary may fall on the wrong side). The
panel also says whether a reproduced section crosses the station's watershed: figure 112 is tagged
to the Pedernales, and its section line is not captured as geometry, so no distance is given.

For a well the panel draws a depth diagram from that well's own Groundwater Database report: the
driller's log bands with their recorded descriptions, casing rows, any screen or open interval,
total depth, and the latest saved water level from the measurement record. Nothing in the diagram
is inferred; a well with no completion rows shows only what was recorded. Being on an aquifer's
mapped extent does not connect a station to that aquifer.

## Sections

Two published USGS figures are reproduced unaltered from the captured files:

- **HA 730-E figure 112**, section C–C′ through Gillespie, Kendall and Bexar counties, crossing the
  Pedernales River, modified by USGS from Ashworth (1983). Vertical scale greatly exaggerated;
  potentiometric surface dated 1975.
- **HA 730-E figure 79**, a diagrammatic northwest–southeast section across the Edwards Plateau,
  Llano Uplift, Hill Country and Balcones Fault Zone, marked not to scale.

Six sentences from HA 730-E on the order of the units are quoted on the page. The build stops if
any of them is not found word for word in its capture.

## Evidence gaps

- No reproducible section through the Llano River watershed. TWDB Report 346 (1996) has Llano
  Uplift sections in figures 3–7, adapted from other authors, and its reuse grant covers original
  material; the report is linked and its figures are not reproduced.
- No recharge-zone or confining-unit polygons were acquired. Confining relationships appear only as
  quoted USGS sentences.
- BEG mapping was audited only as the atlas sheets served by TWDB. USGS statewide downloads over
  40 MB, TWDB Report 380 and the Llano Uplift model report were found and not captured.
- No underground connection between a well, a spring, a stream or a reservoir is stated anywhere in
  this layer. Position inside a watershed, position on an outcrop and similar timing are not evidence
  of one.
