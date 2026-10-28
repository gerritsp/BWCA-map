# BWCA site finder

## Run the current map

From the project root:

```sh
python -m pip install -r requirements-app.txt
npm ci
python APP.py
python -m http.server 8000 --directory maps
```

Open http://localhost:8000/lake_search.html or
http://localhost:8000/bwca_graph_map.html. APP.py generates the interactive map
and precomputes its routing graph. Keep the HTTP server running while browsing.
Use the layers button in the map's upper-right corner to switch to USGS Topo or
hide map overlays. Lake search can also limit results from an entry point by
cumulative portage rods, portage count and lake-to-lake transitions. Entry
markers use the checked-in 2026 Forest Service layer; routing connectors leave
the official point in place and show how it was attached to the local graph.

## Project layout

| Location | Purpose |
| --- | --- |
| APP.py | Current map builder |
| models/ | Active data models and lake identifiers |
| Templates/ | Editable map HTML, JavaScript, and routing engine |
| Scripts/ | Lake-data synchronization, source reconciliation, search/access indexes, routing build |
| Data/entry_points/ | Checked-in official Forest Service entry-point snapshot |
| Data/processed/ | Active input datasets; preserve names and paths |
| Data/SOURCES.md | Data provenance and refresh details |
| maps/ | Generated map assets, lake bundles, and search page |
| processing/ | Data preparation scripts; retained at existing paths |
| tests/ | Automated checks |
| archive/ | Historical map and graph experiments |

Edit map templates rather than generated bwca_graph_map files, then rebuild.
Some older preparation scripts require datasets that are not tracked by Git.
Run `python Scripts/sync_entry_points.py` only when intentionally refreshing the
official entry snapshot, then review changed coordinates and routing confidence
before rebuilding with `python APP.py`.

## Validation

```sh
python -m unittest discover -s tests -v
python Scripts/validate_lake_bundles.py
python Scripts/compare_stealing_fish.py ../Stealing-fish
node tests/test_lake_popup.js
```

## Local files and worktrees

This cleanup was performed on the GitHub repository, not the Windows working
folder. Untracked Windows files have not been inspected or moved. Similar names
are not proof of identical content; compare hashes and references before archiving.

Data/BWCA-map-test is a known linked Git worktree on the user's computer.
Do not move or delete it as an ordinary directory. Inspect `git worktree list`
and its status first. A future relocation should use `git worktree move` after
saving its changes. Keep the original project and its local datasets until that
review is complete.
