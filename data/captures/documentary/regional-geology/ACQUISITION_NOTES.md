# RAW BUCKET — faithful pulls only

Acquisition pass for regional geology, run 2026-10-04 UTC (2026-10-03 local). Every capture below went through
`tools/regional_acquire.py <name> '<url>' --folder regional-geology`, which wrote `<name>.gz` (verbatim response bytes,
gzip) and `<name>.meta.json` (url, retrieved_at, status, sha256, bytes). Nothing here is converted, simplified or
derived. Exact URLs and checksums live in each `.meta.json`; this file describes what each response says it contains.
Statements about content come from reading the captured bytes (field lists, counts, quoted text). No statement here
says which aquifer a well taps or how any unit behaves.

Pilot bbox used in every bbox query: lon -100.3 to -97.6, lat 30.0 to 31.0 (EPSG:4326).

Totals: 40 geology/aquifer/documentary captures, plus 40 well-evidence captures (37 per-well CSVs and 3 supporting).
All 80 returned HTTP 200. Folder size 88 MB gzipped.

## 1. TWDB major and minor aquifers

| name | URL | status | bytes | what it is |
|---|---|---|---|---|
| twdb-gisdata-page | https://www.twdb.texas.gov/mapping/gisdata.asp | 200 | 68,885 | HTML landing page. States: "Major Aquifers - The 9 major aquifers of Texas as defined by the TWDB, Updated December 2006" and "Minor Aquifers - The 22 minor aquifers of Texas as defined by the TWDB, Updated December 2017". Links the two zips below and a "Map Disclaimer". |
| twdb-major-aquifers-shp-zip | https://www.twdb.texas.gov/mapping/gisdata/doc/major_aquifers.zip | 200 | 11,029,569 | Zip, statewide shapefile `NEW_major_aquifers_dd` (.shp/.shx/.dbf/.prj/.sbn/.sbx/.shp.xml) plus `NEW_major_aquifers.lyr`. HTTP Last-Modified 2007-01-03. DBF: 139 records; fields AREA, PERIMETER, AQUIFER (values 0/1/2: 30/69/40 records), AQ_NAME (SEYMOUR, OGALLALA, HUECO_BOLSON, GULF_COAST, EDWARDS-TRINITY, PECOS VALLEY, CARRIZO, TRINITY, EDWARDS). .prj: GCS_North_American_1983, decimal degrees. Metadata (.shp.xml, FGDC): source scale denominator 250000; "Lines were digitized from the Bureau of Economic Geology's Geologic Atlas Sheets (GAT) at 1:250,000 scale"; publication date 199708, revised for the 2007 State Water Plan; keywords include "outcrop subcrop". Reuse, quoted from the metadata: "There are no restrictions nor legal prerequisites for accessing the data set." and "There are no restrictions nor legal prerequisites for using the data set after access is granted." The metadata gives no definition for the AQUIFER code values (attribute definitions are empty). The binary `.lyr` contains label strings such as "Trinity (subcrop)", "Edwards - Trinity Plateau (outcrop)" and value strings such as "TRINITY, 1", "TRINITY, 2". |
| twdb-minor-aquifers-shp-zip | https://www.twdb.texas.gov/mapping/gisdata/doc/minor_aquifers.zip | 200 | 7,863,821 | Zip, statewide shapefile `Minor_Aquifers` plus `Minor_Aquifers.lyr`. HTTP Last-Modified 2017-12-15; file dates 2017-10-04. DBF: 463 records; fields AQU_NAME, AQUIFER (values 1/2: 241/222 records), Area_AQ, minorArea. AQU_NAME counts include HICKORY 164, ELLENBURGER-SAN SABA 157, MARBLE FALLS 48. .prj: projected "GAM" Albers, GCS NAD83, central meridian -100, standard parallels 27.5/35.0, latitude of origin 31.25, false easting 4921250, false northing 19685000, unit Foot_US. Metadata is a thin ESRI stub (7.6 KB) with no use constraints, no scale and no attribute definitions. `.lyr` contains labels such as "Ellenburger - San Saba (outcrop)", "Ellenburger - San Saba (subcrop)", "Hickory (subcrop)" and value strings "HICKORY, 1", "HICKORY, 2". |
| twdb-map-disclaimer | https://www3.twdb.texas.gov/apps/waterdatainteractive/Home/Disclaimer | 200 | 19,825 | HTML. The "Map Disclaimer" linked from the GIS page. Quote: "The TWDB provides information via this web site as a public service. Neither the State of Texas nor the TWDB assumes any legal liability or responsibility or makes any guarantees or warranties as to the accuracy, completeness or suitability of the information for any particular purpose." |
| twdb-baselayer-major-aquifers-layer | https://services.twdb.texas.gov/arcgis/rest/services/Base/BaseLayerQueryService/MapServer/1?f=json | 200 | 3,511 | ArcGIS Server 10.91 layer description, "Major Aquifers", polygon. Fields: AquiferName, MajorAquiferId (OID), AquiferNumName. Native SR wkid 102100 (3857). maxRecordCount 1000, supports pagination, formats JSON/geoJSON/PBF. `description` and `copyrightText` are empty strings. |
| twdb-baselayer-minor-aquifers-layer | …/MapServer/2?f=json | 200 | 3,511 | Same shape for "Minor Aquifers". Fields: AquiferName, MinorAquiferId (OID), AquiferNumName. `description` and `copyrightText` empty. |
| twdb-major-aquifers-bbox | …/MapServer/1/query?where=1=1&geometry=<bbox>&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&orderByFields=MajorAquiferId&f=geojson | 200 | 24,886,440 | GeoJSON FeatureCollection, 15 features, no `exceededTransferLimit` flag. Service count probe for the same bbox returned 15. Output coordinates requested in EPSG:4326. Features are whole polygons that intersect the bbox, not clipped to it (hence the size). (AquiferName, AquiferNumName) pairs present: Carrizo-Wilcox/1CARRIZO ×1; Edwards (Balcones Fault Zone)/1EDWARDS ×2, /2EDWARDS ×1; Edwards-Trinity (Plateau)/1EDWARDS-TRINITY ×1; Trinity/1TRINITY ×6, /2TRINITY ×4. The service does not define the leading 1/2 in AquiferNumName. |
| twdb-minor-aquifers-bbox | …/MapServer/2/query?…&orderByFields=MinorAquiferId&f=geojson | 200 | 3,337,195 | GeoJSON, 316 features, no `exceededTransferLimit`. Count probe returned 316. Pairs present: Ellenburger-San Saba/1ELLENBURGER-SAN SABA ×52, /2ELLENBURGER-SAN SABA ×70; Hickory/1HICKORY ×81, /2HICKORY ×82; Marble Falls/1MARBLE FALLS ×30; Lipan/2LIPAN ×1 (MultiPolygon). |

## 2. Mapped geology: units and faults

### 2a. TWDB BaseLayerQueryService (attributes carry Geologic Atlas of Texas sheet names)

| name | URL | status | bytes | what it is |
|---|---|---|---|---|
| twdb-gat-index-page | https://www.twdb.texas.gov/groundwater/aquifer/GAT/index.asp | 200 | 76,878 | HTML. TWDB "Geologic Atlas of Texas" page: "A geologic atlas displays various geological features and shows the surface extent of geologic formations (and aquifers)." Links to TxGIO's GAT collection, the TWDB Groundwater Data Viewer, a USGS GAT viewer (txpub.usgs.gov/txgeology), and per-sheet pages (austin.htm, llano.htm, …). No rights statement on the page. |
| twdb-baselayer-rockunit-layer | …/MapServer/11?f=json | 200 | 4,191 | Layer description "Rock Unit", polygon. Fields: ObjectId, RockUnitId, RockUnitName, RockUnitCode, SheetName, Period, EpochOrSeries, GroupName, Description, SheetNameUrl. Native SR 102100. maxRecordCount 1000. `description`/`copyrightText` empty. |
| twdb-baselayer-member-layer | …/MapServer/12?f=json | 200 | 4,088 | Layer description "Member", polygon. Fields: ObjectId, MemberId, MemberName, MemberCode, RockUnitName, RockUnitCode, SheetName, Description, SheetNameUrl. |
| twdb-baselayer-structure-layer | …/MapServer/13?f=json | 200 | 3,501 | Layer description "Structure", polyline. Fields: ObjectId, FaultType, FaultLengthInFeet, FaultLengthInMeters. A distinct-values probe on the bbox returned FaultType values: Normal, Inferred Normal, Concealed Normal, Thrust, Unspecified. |
| twdb-gat-structure-bbox-p1 | …/MapServer/13/query?…&orderByFields=ObjectId&resultOffset=0&resultRecordCount=1000&f=geojson | 200 | 552,135 | GeoJSON LineStrings, 1000 features, `exceededTransferLimit: true`. ObjectId 3080–8611. |
| twdb-gat-structure-bbox-p2 | …resultOffset=1000… | 200 | 365,610 | GeoJSON, 593 features, no transfer-limit flag. ObjectId 8612–9634. Pages total 1,593, matching the count probe (1,593). |
| twdb-gat-member-bbox | …/MapServer/12/query?…resultOffset=0&resultRecordCount=1000&f=geojson | 200 | 236,323 | GeoJSON polygons, 143 features, no transfer-limit flag (count probe 143). |
| twdb-gat-rockunit-bbox-p01 | …/MapServer/11/query?…&orderByFields=ObjectId&resultOffset=0&resultRecordCount=500&f=geojson | 200 | 11,274,129 | GeoJSON polygons, 500 features, `exceededTransferLimit: true`. ObjectId 6710–71844. First feature's properties, as an example of the schema: RockUnitId "Kbc_AU", RockUnitName "Bee Cave Marl", RockUnitCode "Kbc", SheetName "Austin", Period "Cretaceous", EpochOrSeries "Comanchean", GroupName "Fredericksburg Group", Description (free text), SheetNameUrl "http://www.twdb.texas.gov/groundwater/aquifer/GAT/austin.htm". |
| twdb-gat-rockunit-bbox-p02 | …resultOffset=500&resultRecordCount=1000… | 200 | 22,002,520 | 1000 features, flag true. ObjectId 71845–88211. |
| twdb-gat-rockunit-bbox-p03 | …resultOffset=1500… | 200 | 8,899,073 | 1000 features, flag true. ObjectId 88212–90759. |
| twdb-gat-rockunit-bbox-p04 | …resultOffset=2500… | 200 | 4,060,851 | 1000 features, flag true. ObjectId 90760–92246. |
| twdb-gat-rockunit-bbox-p05 | …resultOffset=3500… | 200 | 5,460,323 | 1000 features, flag true. ObjectId 92247–94218. |
| twdb-gat-rockunit-bbox-p06 | …resultOffset=4500… | 200 | 5,950,207 | 1000 features, flag true. ObjectId 94219–95671. |
| twdb-gat-rockunit-bbox-p07 | …resultOffset=5500… | 200 | 9,700,523 | 1000 features, flag true. ObjectId 95672–97045. |
| twdb-gat-rockunit-bbox-p08 | …resultOffset=6500… | 200 | 30,496,332 | 785 features, no flag (last page). ObjectId 97046–116864. |

Rock-unit pagination check: 8 pages hold 7,285 features with 7,285 distinct ObjectIds; the count probe and the
`returnIdsOnly` probe for the same bbox both returned 7,285. Page 1 is 500 records and pages 2–8 are 1000 records
(page size was raised after page 1 measured 11 MB). All pages are ordered by ObjectId with `outSR=4326`.
The service itself states no version date, no scale and no reuse terms for layers 11–13. The only provenance on the
features is the `SheetName` / `SheetNameUrl` attribute pointing at TWDB's Geologic Atlas of Texas sheet pages.

| name | URL | status | bytes | what it is |
|---|---|---|---|---|
| txgio-gat-collection-json | https://api.tnris.org/api/v1/collections/e28d8df6-cd30-4e89-bf0f-833e1ed0e670 | 200 | 5,029 | JSON metadata for the TxGIO DataHub collection "Geologic Atlas of Texas" (the collection TWDB's GAT page links to). States: "Scanned and geo-referenced version of the UT BEG Geologic sheets"; "38 hard copy map sheets depicting surface geology for the entire state of Texas at a scale of 1:250,000"; source "Bureau of Economic Geology"; file_type "JPG,MrSID"; spatial_reference "4326"; acquisition_date 2014-02-01; publication_date 2019-04-01; license_name "Creative Commons Zero v1.0 Universal" (CC0-1.0, https://spdx.org/licenses/CC0-1.0.html). This license statement is for the scanned raster sheets in that collection; the JSON does not mention the vector layers served by TWDB. |

### 2b. USGS State Geologic Map Compilation (SGMC), second source

| name | URL | status | bytes | what it is |
|---|---|---|---|---|
| usgs-sgmc-state-page | https://mrdata.usgs.gov/geology/state/ | 200 | 25,181 | HTML. "Geologic maps of US states". Lists per-state downloads (`shp/TX.zip`, `kml/txgeol.kmz`), a WFS (`services/wfs/sgmc2`), and the citation: Horton, J.D., 2017, The State Geologic Map Compilation (SGMC) geodatabase of the conterminous United States (ver. 1.1, August 2017), USGS data release, https://doi.org/10.5066/F7WH2N65. |
| usgs-sgmc-metadata-txt | https://mrdata.usgs.gov/geology/state/USGS_SGMC_Metadata.txt | 200 | 66,189 | FGDC metadata text. Publication_Date 20170818, Edition "Version 1.1". Horizontal datum D_North_American_1983. Access_Constraints: "None." Use_Constraints (quote): "These data are intended for use at approximately 1:1,000,000 scale or smaller. There is no guarantee concerning the accuracy of the data. Any user who modifies the data is obligated to describe the types of modifications they perform. … Acknowledgment of the U.S. Geological Survey would be appreciated in products derived from these data." |
| usgs-sgmc-wfs-structure-bbox | https://mrdata.usgs.gov/services/wfs/sgmc2?service=WFS&version=1.1.0&request=GetFeature&typeName=Structure&bbox=30.0,-100.3,31.0,-97.6,urn:ogc:def:crs:EPSG::4326 | 200 | 939,141 | GML 3.1.1 (MapServer WFS), 1,066 `Structure` features; a `resultType=hits` probe reported 1,066. Geometry srsName EPSG:4326 with coordinates written latitude-first. Fields: state, descript (e.g. "Normal fault, certain"), misc, ref_id ("TX001"), src_url (https://pubs.usgs.gov/ds/2005/170/). |
| usgs-sgmc-wfs-lithology-bbox | …typeName=Lithology&bbox=30.0,-100.3,31.0,-97.6,urn:ogc:def:crs:EPSG::4326 | 200 | 10,431,717 | GML 3.1.1, 1,817 `Lithology` polygon features; hits probe reported 1,817. Fields: state, orig_label (e.g. "Kh"), sgmc_label, unit_link (e.g. "TXKh;0"), ref_id, generalize (e.g. "Sedimentary, carbonate"), src_url, url (per-unit page `https://mrdata.usgs.gov/geology/state/sgmc2-unit.php?unit=…`). Unit names and ages are not in the feature attributes; they sit behind `unit_link`. |

## 3. Cross-sections and stratigraphic order

### 3a. USGS Ground Water Atlas of the United States, HA 730-E (Oklahoma, Texas), Paul D. Ryder, 1996

| name | URL | status | bytes | what it is |
|---|---|---|---|---|
| usgs-ha730e-text8-edwards-trinity | https://pubs.usgs.gov/ha/ha730/ch_e/E-text8.html | 200 | 45,858 | HTML text, "Edwards-Trinity aquifer system", with links to figures 78–116. Contains the text on the three aquifers of the system, the statement "The Edwards aquifer overlies the Trinity aquifer", the formations composing the Trinity aquifer (Hosston, Sligo, Travis Peak or Pearsall, Glen Rose, Paluxy, Twin Mountains by area) and the Hill Country passages. |
| usgs-ha730e-text10-minor-aquifers | https://pubs.usgs.gov/ha/ha730/ch_e/E-text10.html | 200 | 23,586 | HTML text, "Minor aquifers in Texas". Contains the Marble Falls, Ellenburger-San Saba and Hickory paragraphs, including: Marble Falls Limestone "of Pennsylvanian age, which crops out along the flanks of the Llano Uplift"; Ellenburger-San Saba "crop out in a circular pattern around the Llano Uplift and dip radially into the subsurface"; Hickory "is underlain by Precambrian rocks and is overlain and separated from the Ellenburger-San Saba aquifer by the Cap Mountain Limestone and the Lion Mountain Sandstone Members of the Riley Formation." |
| usgs-ha730e-fig078 | …/ch_e/gif/E078.GIF | 200 | 47,126 | GIF 628×606. Caption in image: "Figure 78. The Edwards–Trinity aquifer system extends over a wide arcuate area of central Texas and southeastern Oklahoma. Three major aquifers constitute the aquifer system." Map with numbered physiographic regions (1 Trans-Pecos, 2 Edwards Plateau, 3 Balcones Fault Zone, 4 Hill Country, 5 East-central Texas, 6 Northeastern Texas/southeastern Oklahoma). Credit in image: "Modified from Barker, R.A., Bush, P.W., and Baker, E.T., Jr., 1994, … U.S. Geological Survey Water-Resources Investigations Report 94-4039". Scale 1:7,500,000. |
| usgs-ha730e-fig079 | …/gif/E079.GIF | 200 | 10,356 | GIF 455×492. Caption in image: "Figure 79. A diagrammatic section through the Edwards–Trinity aquifer system shows how the three aquifers relate to each other and to contiguous rocks." Section labelled Northwest to Southeast across "Edwards Plateau", "Llano Uplift", "Hill Country", "Balcones Fault Zone"; marked "NOT TO SCALE"; no mapped section line. Credit in image: "Modified from E.L. Kuniansky, U.S. Geological Survey, written communication, 1990". |
| usgs-ha730e-fig080 | …/gif/E080.GIF | 200 | 31,730 | GIF 652×801. Correlation chart. Caption in image: "Figure 80. Many different geologic formations of Cretaceous age compose the Edwards–Trinity aquifer system. … The gray area represents missing rocks. Number refers to map above." Columns by region including "Hill Country (4)" and "Balcones Fault Zone (3)". Credit lists eight sources (Brand and Deford 1958; Lozo and Smith 1964; Stricklin and others 1971; Rose 1972; Loucks 1977; Klemt and others 1975; Smith and Brown 1983; Nordstrom 1982). |
| usgs-ha730e-fig108 | …/gif/E108.GIF | 200 | 35,366 | GIF 534×515. Map. Caption in image: "Figure 108. The Trinity aquifer underlies a large area that extends from south-central Texas to southeastern Oklahoma. …" Explanation includes "A–A' Line of hydrogeologic section"; lines A–A', B–B', C–C' are drawn on the map. Scale 1:7,500,000. |
| usgs-ha730e-fig110 | …/gif/E110.GIF | 200 | 12,304 | GIF. Section A–A'. Caption in image: "Figure 110. In southeastern Oklahoma, water in the Trinity aquifer becomes confined downdip from the outcrop area. … The line of the hydrogeologic section is shown in figure 108." Modified from Hart and Davis, 1981 (Oklahoma Geological Survey Circular 81). |
| usgs-ha730e-fig111 | …/gif/E111.GIF | 200 | 17,986 | GIF. Section B–B' with county ticks (Erath, Bosque, Hill, McLennan, Limestone, as legible in the 72 ppi image). Caption: "Figure 111. In central Texas, the 1967 potentiometric surface of the Trinity aquifer … The line of the hydrogeologic section is shown in figure 108." Modified from Klemt, Perkins and Alvarez, 1975 (TWDB Report 195). |
| usgs-ha730e-fig112 | …/gif/E112.GIF | 200 | 14,507 | GIF 685×425. Section C–C' with county ticks (Gillespie, Kendall, Bexar) and labels "Pedernales River", "Guadalupe River", "Rocks of the Fredericksburg Group", "Approximate potentiometric surface, 1975"; vertical scale in feet, "VERTICAL SCALE GREATLY EXAGGERATED". Caption in image: "Figure 112. In the Hill Country of south-central Texas, the southward-dipping Trinity aquifer is juxtaposed with the highly permeable Edwards aquifer as a result of faulting. The line of the hydrogeologic section is shown in figure 108." Credit in image: "Modified from Ashworth, J.B., 1983, Ground-water availability of the Lower Cretaceous formations in the Hill Country of south-central Texas: Texas Department of Water Resources Report 273". |
| usgs-copyrights-and-credits-page | https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits | 200 | 88,963 | HTML. USGS policy page. Quote: "USGS-authored or produced data and information are considered to be in the U.S. Public Domain. While the content of most USGS websites is in the U.S. Public Domain, not all information, illustrations, or photographs on our site are." The HA 730 pages themselves carry no rights statement; this is the general USGS statement. Figures 110–112 are each marked "Modified from" a non-USGS source. |

### 3b. TWDB numbered reports

| name | URL | status | bytes | what it is |
|---|---|---|---|---|
| twdb-r346-paleozoic-aquifers-central-texas-pdf | https://www.twdb.texas.gov/publications/reports/numbered_reports/doc/R346/R346.pdf | 200 | 3,840,829 | PDF, 95 pages (scanned with OCR text layer). TWDB Report 346, "The Paleozoic and Related Aquifers of Central Texas", March 1996. Rights, PDF page 3 (quote): "Authorization for use or reproduction of any original material contained in this publication, i.e., not obtained from other sources, is freely granted. The Board would appreciate acknowledgement." Figures found by text search (PDF page numbers): p15 "Figure 3. Idealized geologic cross-section, Llano Uplift" (marked not to scale); p16 "Figure 4. Generalized geologic cross-section A-A' across the Llano uplift (adapted from Mount and others, 1967)" with a location map; p17 "Figure 5. Cross-section 8-8' adapted from Jackson and Tyber (1993)" (OCR reads "8-8'", likely B-B'; Gillespie County label); p18 "Figure 6. Cross section C-C' (adapted from Pettigrew, 1991)" and "Figure 7. Cross-section 0-0' (adapted from Pettigrew, 1991)" (OCR reads "0-0'", likely D-D'; San Saba County label). p20: "Table 1. Geologic and hydrogeologic units in the study area" (Era / System / Group / Formation / Member or Unit / Hydrogeologic Units). OCR quality is poor in figure areas; captions were read from the OCR layer. Figures 4–7 are each marked "adapted from" another source, which the rights sentence excludes. |
| twdb-r377-hill-country-trinity-gam-pdf | https://www.twdb.texas.gov/publications/reports/numbered_reports/doc/R377_HillCountryGAM.pdf | 200 | 18,887,691 | PDF, 176 pages (born-digital). TWDB Report 377, "Groundwater Availability Model: Hill Country Portion of the Trinity Aquifer in Texas" (title as listed in the TWDB numbered-reports index), Jones, Anaya, Wade, June 2011. Rights, PDF page 5 (quote): "The Texas Water Development Board freely grants permission to copy and distribute its materials. The agency would appreciate acknowledgment." PDF p27: "Figure 3-14. Stratigraphic and hydrostratigraphic column of the Hill Country area." PDF p31: "Figure 3-17. Geologic cross sections through the study area (modified from Ashworth, 1983; Mace and others, 2000). Inset map shows cross-section line A-A´." Text pages that mention Hammett together with Upper/Middle/Lower Trinity: PDF pp 11, 34, 38, 64, 99, 105, 116, 166. |

## 4. Well evidence for the 37 TWDB state well numbers

Door chosen: `https://www3.twdb.texas.gov/apps/reports/GWDB/WellData?StateWellNumber=<id>&rs:Format=CSV`
(one CSV per well, no login, 4 s pause between requests, no refusals). Each CSV starts with the GWDB disclaimer, then
blocks separated by blank lines:

1. `StateWellNumber, County, RiverBasin, GMA, RWPA, GCD, LatitudeDD, LatitudeDMS, LongitudeDD, LongitudeDMS, CoordinateSource, AquiferCode, Aquifer, AquiferPickMethod, LandSurfaceElevation, LandSurfaceElevationMethod, WellDepth, WellDepthSource, DrillingStartDate, DrillingEndDate, DrillingMethod, BoreholeCompletion`
2. `WellType, WellUse, WaterLevelObs, WaterQualityAvailable, Pump, PumpDepth, PowerType, AnnularSealMethod, SurfaceCompletion, Owner, Driller, OtherDataAvailable, WellReportTrackingNum, PlugReportTrackingNum, USGSSiteNumber, TCEQSourceId, GCDWellNumber, OwnerWellNumber, OtherWellNumber, PreviousStateWellNumber, ReportingAgency, CreatedDate, LastUpdateDate`
3. `WellRemarks`
4. `CASING, CasDiameter, CasingType, CasingMaterial, Schedule, Gauge, CasTopDepth, CasBottomDepth`
5. `WELL_TESTS`, `LITHOLOGY (LithTopDepth, LithBottomDepth, LithDescription)`, `ANNULAR_SEAL_RANGE`, `BOREHOLE (BoreDiameter, BoreTopDepth, BoreBottomDepth)`, `PLUGGED_BACK`, `FILTER (FilterMaterial, FilterTopDepth, FilterBottomDepth, FilterSize)`, `PACKERS`
6. Water-level measurements (`StatusCode, MeasureDate, …`), lookup tables, then water-quality samples (`SampleDate, …, SampledAquiferCode, SampledInterval, …`).

In all 37 files the main row's StateWellNumber equals the requested id, and WellDepth and AquiferCode are non-empty.
The table gives the number of data rows present in each completion-related block (0 means the header is there and no
rows follow). The CSVs include an `Owner` column with owner names as TWDB publishes them.

| name | status | bytes | CASING rows | LITHOLOGY rows | BOREHOLE rows | FILTER rows | ANNULAR_SEAL rows | PLUGGED_BACK rows | PACKERS rows | WELL_TESTS rows |
|---|---|---|---|---|---|---|---|---|---|---|
| gwdb-welldata-5621401 | 200 | 167721 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5630102 | 200 | 47320 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5634504 | 200 | 141213 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5634505 | 200 | 186827 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5642403 | 200 | 207958 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5643901 | 200 | 86218 | 4 | 19 | 2 | 0 | 3 | 0 | 0 | 1 |
| gwdb-welldata-5644901 | 200 | 231014 | 3 | 10 | 2 | 0 | 2 | 0 | 0 | 2 |
| gwdb-welldata-5652704 | 200 | 89469 | 3 | 27 | 0 | 1 | 5 | 0 | 0 | 2 |
| gwdb-welldata-5659201 | 200 | 233420 | 3 | 12 | 2 | 1 | 2 | 0 | 0 | 0 |
| gwdb-welldata-5664301 | 200 | 73429 | 2 | 11 | 2 | 1 | 1 | 0 | 0 | 2 |
| gwdb-welldata-5664302 | 200 | 60825 | 3 | 11 | 2 | 1 | 2 | 0 | 0 | 2 |
| gwdb-welldata-5714604 | 200 | 243750 | 2 | 6 | 2 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5722505 | 200 | 265050 | 1 | 10 | 2 | 0 | 0 | 0 | 0 | 1 |
| gwdb-welldata-5723406 | 200 | 14714 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5745822 | 200 | 383493 | 3 | 0 | 3 | 1 | 0 | 0 | 0 | 1 |
| gwdb-welldata-5747310 | 200 | 49535 | 5 | 8 | 2 | 2 | 0 | 0 | 0 | 1 |
| gwdb-welldata-5747312 | 200 | 212963 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5747314 | 200 | 193178 | 2 | 11 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5748109 | 200 | 148896 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5748505 | 200 | 230594 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5748811 | 200 | 243605 | 2 | 21 | 1 | 0 | 0 | 0 | 0 | 1 |
| gwdb-welldata-5750108 | 200 | 405178 | 3 | 7 | 0 | 0 | 0 | 0 | 0 | 1 |
| gwdb-welldata-5750324 | 200 | 342389 | 2 | 9 | 0 | 0 | 0 | 0 | 0 | 1 |
| gwdb-welldata-5751407 | 200 | 285561 | 2 | 23 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5755405 | 200 | 280919 | 2 | 10 | 1 | 1 | 2 | 3 | 0 | 1 |
| gwdb-welldata-5755607 | 200 | 304624 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5755803 | 200 | 31233 | 2 | 7 | 1 | 1 | 0 | 0 | 1 | 1 |
| gwdb-welldata-5756702 | 200 | 68897 | 12 | 21 | 0 | 0 | 1 | 0 | 0 | 0 |
| gwdb-welldata-5756716 | 200 | 276659 | 2 | 17 | 0 | 0 | 0 | 0 | 0 | 1 |
| gwdb-welldata-5758203 | 200 | 240682 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5764502 | 200 | 252488 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5835811 | 200 | 197895 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5841406 | 200 | 26361 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5849326 | 200 | 184567 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5850120 | 200 | 297522 | 2 | 12 | 2 | 0 | 1 | 0 | 0 | 0 |
| gwdb-welldata-5850301 | 200 | 364195 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| gwdb-welldata-5857502 | 200 | 228278 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

26 of the 37 files have at least one CASING row; 11 have none (5621401, 5630102, 5634504, 5634505, 5642403, 5723406,
5747312, 5748109, 5748505, 5764502, 5857502).

Supporting captures:

| name | URL | status | bytes | what it is |
|---|---|---|---|---|
| gwdb-featureserver-37-wells | https://services.twdb.texas.gov/arcgis/rest/services/Public/TWDB_Groundwater_database/FeatureServer/0/query?where=StateWellNumber IN (<37 quoted ids>)&outFields=*&orderByFields=StateWellNumber&f=json | 200 | 18,597 | Esri JSON, 37 point features, SR 4326, no transfer-limit flag. Fields: ObjectId, StateWellNumber (string), OwnerName, PrimaryWaterUse, Elevation, WaterLevelObservationType, WaterQualityAvailable, AquiferCodeName (e.g. "367ELBG - Ellenburger Group"), CoordDDLat, CoordDDLong, CountyName, WellType, WellDepth. No completion-interval fields. |
| gwdb-featureserver-layer | …/FeatureServer/0?f=json | 200 | 7,227 | Layer description "TWDB Groundwater Data", point, SR 4326, maxRecordCount 1000. `description`/`copyrightText` empty. Service-level description (seen in a probe, not captured): "Texas Water Development Board's (TWDB) Groundwater Database. This database contains information on selected water wells, springs, oil/gas tests, water levels and water quality." |
| twdb-gwdb-reports-page | https://www.twdb.texas.gov/groundwater/data/gwdbrpt.asp | 200 | 103,470 | HTML. GWDB reports and downloads page. States the bulk downloads are "Pipe "\|" delimited text files … updated nightly" and carries the GWDB disclaimer: "Except where noted, all of the information provided in the GWDB is believed to be accurate and reliable; however, the TWDB assumes no responsibility for any errors … users of these data are responsible for checking the accuracy, completeness, currency and/or suitability of all information themselves." Also: "most of the locations of wells in this database are not verified by State staff and may be inaccurate." |

## Probed, not captured

| source | URL | why not captured |
|---|---|---|
| USGS SGMC Texas shapefile | https://mrdata.usgs.gov/geology/state/shp/TX.zip | Size: Content-Length 52,545,132 (over the 40 MB limit). Last-Modified 2022-01-12. The bbox WFS pulls above were taken instead. |
| USGS mrdata Texas state page (URL given in the brief) | https://mrdata.usgs.gov/geology/state/state.php?state=TX | Dead link, HTTP 404. The live index is https://mrdata.usgs.gov/geology/state/ (captured). |
| USGS mrdata SGMC directory | https://mrdata.usgs.gov/sgmc/ | Refusal, HTTP 403 on the first request. Not retried. |
| USGS SGMC unit tables (unit names and ages keyed by unit_link) | https://www.sciencebase.gov/catalog/file/get/5888bf4fe4b05ccb964bab9d?name=USGS_SGMC_Tables_CSV.zip (also …Shapefiles.zip, …Geodatabase.zip) | Host `sciencebase.gov` is not on the helper allowlist. Owner: USGS ScienceBase. Size not probed. |
| USGS SGMC per-unit pages | https://mrdata.usgs.gov/geology/state/sgmc2-unit.php?unit=TXKh;0 (pattern from the `url` field) | Not probed and not captured: one request per distinct unit, capture budget spent. Allowlisted host. |
| USGS SGMC WFS, lon-lat bbox order | …/services/wfs/sgmc2?…&bbox=-100.3,30.0,-97.6,31.0,EPSG:4326 | Returned HTTP 200 with an empty FeatureCollection (`<gml:Null>missing</gml:Null>`), no error. The service wants latitude-first order for WFS 1.1.0 EPSG:4326; the captures use `bbox=30.0,-100.3,31.0,-97.6,urn:ogc:def:crs:EPSG::4326`. WFS output formats offered are GML only (no GeoJSON). |
| USGS DS 170, Geologic Map Database of Texas | https://pubs.usgs.gov/ds/2005/170/ (downloads/, downloads/TX_meta.txt, downloads/readme.html) | Probed the landing page only. Page text: "a digital geologic map database of the Barnes 1992 Geologic Map of Texas … prepared in cooperation with the Texas Bureau of Economic Geology … originally printed as four 1:500,000-scale sheets … The merged layers are still at 1:500,000 scale". This is the source cited in the SGMC features' `src_url`. Download sizes not probed; budget spent. Allowlisted host. |
| TxGIO Geologic Atlas of Texas sheet downloads | https://data.geographic.texas.gov/e28d8df6-cd30-4e89-bf0f-833e1ed0e670/resources/utbeg-geology-atlas_3098a1_gat.zip (Llano sheet) and 45 others, listed by https://api.tnris.org/api/v1/resources/?collection_id=e28d8df6-cd30-4e89-bf0f-833e1ed0e670 | Size: Llano sheet 74,045,414 bytes; other sheets 46–107 MB each. Scanned raster (JPG/MrSID), not vector. |
| TxGIO catalog search for vector geology or aquifer layers | https://api.tnris.org/api/v1/collections_catalog/?search=geolog and ?search=aquifer | "geolog" returned 0 results; "aquifer" returned 4 unrelated collections (two agency placeholder entries, two lidar). No vector geology collection found by these two searches. |
| TxGIO imagery WMS for GAT | https://imagery.geographic.texas.gov/server/services/Geologic_Atlas_Texas_250k/Geologic_Atlas_Texas_Collarless/ImageServer/WMSServer | Not probed. Raster image service; no bbox vector query. |
| TxGIO GAT interactive maps | https://portal.geographic.texas.gov/portal/apps/experiencebuilder/experience/?id=1f42c084217947c7b2d2f1b212c25b40 | Not probed. Web app, not a data endpoint. |
| USGS GAT viewer linked from TWDB | https://txpub.usgs.gov/txgeology/ | Not probed. Web app. |
| BEG | https://www.beg.utexas.edu/research/programs/statemap | A guessed URL; returned BEG's "Page not found" page. BEG was not audited further. |
| TWDB service root and folders | https://services.twdb.texas.gov/arcgis/rest/services?f=json | Probed only. Folders: Base, GAMs, Operational, Public, PWS, Surface, Utilities. `Base/BaseLayerQueryService` layer list: 1 Major Aquifers, 2 Minor Aquifers, 3 RWPA, 4 GMA, 5 GCD, 6 River Basins, 7 USGS Grid, 8 State Grid, 9 Counties, 10 Bracs Study Areas, 11 Rock Unit, 12 Member, 13 Structure. `GAMs/MajorGAMSBoundaries` has one layer, "Major GAM Boundaries". Not captured to save budget; the per-layer descriptions were captured. |
| TWDB ArcGIS guesses | https://www3.twdb.texas.gov/arcgis/rest/services (404 page), https://gis.twdb.texas.gov/…, https://maps.twdb.texas.gov/… (no response) | Do not exist. |
| TWDB Report 380, Aquifers of Texas (2011) | https://www.twdb.texas.gov/publications/reports/numbered_reports/doc/R380_AquifersofTexas.pdf | Size: 50,255,685 bytes (over 40 MB). |
| TWDB Llano Uplift GAM conceptual model report (2016) | https://www.twdb.texas.gov/groundwater/models/gam/llano/Llano_Uplift_Conceptual_Model_Report_Final.pdf | Size: 52,160,987 bytes (over 40 MB). Listed on https://www.twdb.texas.gov/groundwater/models/gam/llano/llano.asp. |
| TWDB contracted report 0604830614, Llano Uplift Aquifers (2008) | https://www.twdb.texas.gov/publications/reports/contracted_reports/doc/0604830614_LlanoUpliftAquifers.pdf | 25,815,090 bytes; under the size limit but not captured, budget spent. |
| TWDB Report 353, Trinity Aquifer Hill Country numerical simulations (2000) | https://www.twdb.texas.gov/publications/reports/numbered_reports/doc/R353/Report353.pdf | 13,637,315 bytes; not captured, budget spent (R377 is the later model report and cites it). |
| Other TWDB numbered reports seen in the index | https://www.twdb.texas.gov/publications/reports/numbered_reports/index.asp | Index probed only. Relevant titles seen: 388 (Brackish Groundwater in the Hill Country Trinity, 2022), 360 (Aquifers of the Edwards Plateau, 2004), 345 (Aquifers of Texas, 1995), 339 (Paleozoic and Cretaceous Aquifers in the Hill Country, 1992), 273 (Lower Cretaceous Formations in the Hill Country, 1983, the source of HA 730-E fig. 112), 174 Blanco, 102 Kerr, 95 Kimble, 60 Kendall county reports. Sizes not probed. |
| HA 730-E other files | https://pubs.usgs.gov/ha/ha730/ch_e/index.html, E-edwards_trin.html, E-edwards_trin4.html, E-text9.html, pub/ch_e/E-text.ascii (188,194 bytes), pub/ch_e/E0xx.eps.gz | Probed. index and figure-list pages hold titles only (captions are inside the GIFs). E-text9 is "Aquifers in Paleozoic rocks". E-text.ascii holds the full chapter text without figure links. EPS versions of each figure exist (E112.eps.gz listed as 33K). Not captured, budget spent. The HA 730 home page (https://pubs.usgs.gov/ha/ha730/) has no rights statement. |
| GWDB per-well report viewer | https://www3.twdb.texas.gov/apps/waterdatainteractive/GetReports.aspx?Num=5621401&Type=GWDB | Returns an HTML ReportViewer shell (30 KB) that needs scripted postbacks, not a PDF. The `apps/reports/GWDB/WellData?…&rs:Format=CSV` door was used instead. |
| GWDB bulk downloads | https://www.twdb.texas.gov/groundwater/data/GWDBDownload.zip, …/GWDBDownloadSQL.zip | Size: 83,284,472 and 93,998,530 bytes (over 40 MB). Statewide pipe-delimited tables, updated nightly (Last-Modified 2026-10-03). |
| GWDB well-location shapefile | https://www.twdb.texas.gov/mapping/gisdata/doc/well/TWDB_Groundwater.zip | 6,708,238 bytes, updated nightly. Not captured: the 37-well feature-service query carries the same kind of location/depth/aquifer attributes. |
| Water Data for Texas well page | https://waterdatafortexas.org/groundwater/well/5621401 | Probed once: HTML page, 120,665 bytes, with an inline base64 chart image and a `/groundwater/download` link. Not explored further once the TWDB CSV door answered. |

## Things the bytes show that a reader might not expect

- TWDB's aquifer layers come in three coordinate systems: the major-aquifer shapefile is geographic NAD83; the
  minor-aquifer shapefile is a custom "GAM" Albers projection in US feet; the map service is native Web Mercator
  (102100) and was asked for EPSG:4326 output.
- Neither the service nor the shapefile metadata defines the outcrop/subsurface code (shapefile `AQUIFER` = 0/1/2;
  service `AquiferNumName` prefix 1/2). The only place the words "(outcrop)" and "(subcrop)" sit next to the code
  values is the binary `.lyr` file in each zip. The major-aquifer DBF also has 30 records with `AQUIFER` = 0.
- The service's bbox responses return whole intersecting polygons, so the 15 major-aquifer features are 24.9 MB.
- The two geology sources are different maps. TWDB layer 11 features carry Geologic Atlas of Texas sheet names
  (the atlas is 1:250,000 per the TxGIO metadata). USGS SGMC features cite DS 170, which its landing page describes
  as the 1:500,000 Barnes 1992 Geologic Map of Texas, and the SGMC metadata says to use the data "at approximately
  1:1,000,000 scale or smaller". Feature counts for the same bbox: TWDB 7,285 unit polygons and 1,593 structure
  lines; SGMC 1,817 lithology polygons and 1,066 structure lines.
- TWDB's ArcGIS layers have empty `description` and `copyrightText`; no version date or reuse terms are stated on
  the service for aquifers or geology.
