# Lake data sources and reproducibility

Project joins use `Data/processed/bwca_lakes.parquet`, with polygon `unique_guid`
strings and canonical eight-digit Minnesota Division of Waters IDs (`dowlknum`).
The input includes 4,515 polygons; 3,154 have no DOW identifier and cannot be
joined to official lake records. Those polygons remain visible on the map with
a missing-data message. The 1,361 identified polygons represent 1,332 DOW lakes.
Multiple polygons with the same DOW receive separate bundles sharing observations.

## Official sources

- [DNR LakeFinder metadata](https://services.dnr.state.mn.us/api/lakefinder/by_id/v1/usage.html): `?id=<DOW>`; morphology, species, regulations, invasives and resource availability.
- [DNR LakeFinder survey details](https://maps.dnr.state.mn.us/cgi-bin/lakefinder/detail.cgi): `?type=lake_survey&id=<DOW>`; surveys, sampled fish lengths in inches, catch per unit effort (CPUE), average weight in pounds, clarity in feet, access and plants.
- [DNR species reference](https://maps.dnr.state.mn.us/lakefinder/lib/lakefinder.js): `fish_species` dictionary, exported as `species.json`.
- [MPCA assessment API documentation](https://services.pca.state.mn.us/api/doc/v1/surfacewater/assessments): request `/api/v1/surfacewater/assessments?format=json&huc8=<HUC8>` for 09030001, 09030002, 09030003 and 04010101. Join lake `wid`/`auid` values after removing separators; stream IDs are excluded. `format=json` is explicit because requests without it returned an HTML browser challenge in this environment.
- [DNR basin morphology](https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_dnr/water_lake_basin_morphology/FeatureServer/1): retain official attributes with source field names; values are not silently assigned guessed units.
- [DNR surveyed-lakes inventory](https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_dnr/env_lakes_surveyed_by_mndnr/MapServer): layer 0 joins by DOW; table 1 joins through layer 0 `fw_id`. Both are paginated in object-ID order with field-type-aware epoch date conversion. Inventory records indicate survey history, not necessarily available catch observations.
- [DNR data/software license](https://www.dnr.state.mn.us/sitetools/data_software_license.html).

## Rebuild

```sh
python -m pip install -r requirements-app.txt
npm install
python Scripts/sync_lake_bundles.py
python Scripts/build_search_index.py
python Scripts/validate_lake_bundles.py
python -m unittest discover -s tests -v
python APP.py
```

Responses are cached beneath `.cache/lake-data/` by full URL, with content SHA256.
`--refresh` downloads new responses. Bundles record request URLs and hashes plus
the project parquet hash. Output uses sorted keys and deduplicated, sorted
observation arrays. Builds from identical cached inputs are byte-reproducible.
Source failures stop normal publication without replacing bundles. An explicitly
requested `--allow-incomplete` diagnostic build is marked incomplete and rejected
by the release validator; it must not be mistaken for a complete snapshot.

Cleaning preserves zero, converts textual nulls to JSON null, normalizes dates,
strips narrative HTML, upgrades DNR links to HTTPS, removes invalid links and
non-positive fish-length bins. DNR `averageWeight` becomes `average_weight_lb`;
raw `totalWeight` is excluded because its interpretation is ambiguous. Search
lengths are maximum observed bins, not guaranteed fish size. Search CPUE is an
arithmetic mean of reported records; popup CPUE retains gear and survey date.

## Stealing-fish reconciliation

`Scripts/compare_stealing_fish.py` verifies the cleaned Stealing-fish snapshot at
commit `0d2e770d36694141b65ab700893aa379b605511d` against the normalized official
bundles. The project lake parquet is byte-identical in both repositories. After
applying the production cleaning rules, Stealing-fish had no additive survey,
catch, positive fish-length, clarity, access, plant, surveyed-lake inventory or
survey-inventory records. The official bundles contain six newer survey rows,
five newer catch rows and eight newer clarity rows. All 31,169 positive length
rows, 751 access rows, 283 plant rows, 556 inventory lakes and 1,807 inventory
surveys match exactly. Forty-five zero-length or zero-count fish bins were
correctly excluded. Both sources cover the same 499 lake-info DOW IDs; 43
Stealing-fish rows contain older differing values, so they are not imported.

Run the reconciliation from this repository with a local checkout path:

```sh
python Scripts/compare_stealing_fish.py ../Stealing-fish
```

The script exits nonzero if a future Stealing-fish snapshot contains additive
records not present in the official bundles.

## Application

`APP.py` resolves paths from the repository root and always loads the project
lake file. Missing campsites, portages, rivers, entry points and fires produce
empty FeatureCollections. Missing routing inputs produce a valid empty graph.
Serve `maps/` over HTTP; search links use encoded polygon GUIDs in the map hash.
The search index refreshes campsite counts from the same processed campsite file
on every application build. `lake_access_index.json` stores Pareto-optimal trip
states from each matched entry lake: cumulative portage rods, portage count and
lake-to-lake transitions. The entry lake is zero lakes in. The map is framed by
the repository's Minnesota DNR legal BWCA boundary and offers USGS Topo as a
switchable basemap.

## Verified snapshot (2026-10-26)

| Measure | Count |
| --- | ---: |
| Polygon bundles and search entries | 1,361 |
| Distinct DOW lakes | 1,332 |
| Lakes with detailed surveys | 499 |
| Lakes with fish observations | 479 |
| Lakes with clarity readings | 360 |
| Lakes with inventory history | 556 |
| Inventory records | 1,807 |

All expected snapshot counts matched. Source collection completed without failures.
A second build from the response cache produced byte-identical bundles and indexes.
The 15-test suite includes every encoded bundle URL and all 15 application assets,
identifier cleaning, observation deduplication, source-cache refresh, exact search
correspondence, campsite counts, entry-point access states, boundary geometry and
executable popup/cache behavior. JavaScript syntax and `git diff --check` passed.

An additional DOM integration check loaded the actual search page and Leaflet map
scripts, selected Crow Lake (`16028700`), zoomed to level 14 and opened a matching
popup with fish observations, clarity and four MPCA assessments. A visual browser
check could not run because the Chromium download returned an invalid archive.
This limitation is distinct from the passing DOM and HTTP checks.
