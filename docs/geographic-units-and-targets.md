# Geographic units and prediction targets

Status: accepted. Code: `src/ashaway/geo.py`, `src/ashaway/targets.py`.

## Units

| Purpose | Unit | Identifier |
|---|---|---|
| Model training | 1 km grid cell x day | EEA reference grid id, e.g. `1kmE5400N1800` (EPSG:3035, lower-left corner in km) |
| Product and evaluation | municipality (δήμος) x day | 4-character code, `LAU_CODE[:4]` |

The model learns on cell-days because fire behaviour depends on local fuel, terrain and weather. Kondylatos et al. (2022) and the Mesogeos datacube use the same 1 km daily grid, so we can reuse their features and compare against their baselines. Travellers do not book a grid cell. They pick a town, so the app reports one score per municipality per day. Cell probabilities are aggregated to the municipality: the maximum is the headline score (one high-risk cell is enough to spoil a holiday), and the mean is kept as context. Evaluation runs on municipality-day rows because that is what users see.

Coordinates arrive in WGS84 and are projected to ETRS89-LAEA (EPSG:3035). `geo.py` uses pyproj when installed and otherwise falls back to the ellipsoidal LAEA formula from IOGP Guidance Note 7-2, tested against the EPSG worked example to 1 cm.

## Municipalities: 332, not 333

Greece has 332 municipalities under Kleisthenis I (L.4555/2018, in force since September 2019). Eurostat/GISCO LAU units for Greece are local communities (δημοτικές κοινότητες), one level below. Grouping LAU codes by their first four characters gives 333 groups: the 332 municipalities plus Mount Athos. Athos is an autonomous monastic state with restricted entry and no holiday market, so AshAway excludes it. `load_municipalities_from_gisco` dissolves LAU polygons into municipalities and drops Athos by default.

## Targets

**Product target, `affected`.** For municipality m and issue date d, `affected = 1` if any of these happens on days d+1 to d+7 inclusive:

1. A NASA FIRMS VIIRS active-fire detection within 20 km of m's centroid.
2. An EFFIS burnt-area perimeter that intersects m and whose fire started in the window.
3. A Hellenic Fire Service incident recorded in m with severity at or above `min_severity`.

Day d itself is excluded: the forecast is issued on d and covers the following week. The label table keeps one boolean column per condition so every positive can be traced to its source. A PM2.5 smoke condition is planned and left as a documented TODO in `targets.py`.

**Training target, `ignition`.** A cell-day is positive if any fire occurs in that cell on day d+1, following Mesogeos.

## Temporal split

Mesogeos Track A, by calendar year of the issue date: train 2006 to 2019, validation 2020, test 2021 to 2022. Rows are never shuffled across splits, since neighbouring days share weather and fires.

## Known limitations

- The 20 km FIRMS test uses the municipality centroid. Large or elongated municipalities (for example on Evia or Crete) can have fires inside their borders more than 20 km from the centroid. Measuring distance to the polygon would fix this once geopandas is part of the pipeline.
- The 7-day horizon means issue dates in the last week of one split see events from the first days of the next split. Purge those rows when leakage matters.
- FIRMS detects thermal anomalies, including some agricultural burning and industrial heat sources. EFFIS maps fires from about 30 ha upward, so small fires appear only in FIRMS or HFS.
- HFS severity is an ordinal scale defined during ingestion. The default threshold counts every incident until we calibrate it.
- The Mount Athos code prefix (`MOUNT_ATHOS_CODE`) must be checked against the GISCO release we download.
- Municipality boundaries before 2019 (Kallikratis, 325 municipalities) differ. All years are labelled on the 2019 boundaries.
