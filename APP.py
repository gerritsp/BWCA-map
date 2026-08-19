import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd

from models.bwca_graph import bwca_graph

# Data/processed/*.parquet is written in NAD83 / UTM zone 15N (see CLAUDE.md's
# CRS gotcha) - the graph's Lake/Campsite objects carry that geometry as-is,
# with no CRS attached to the dataclass itself, so this has to match whatever
# fileCreator.py/portageCreator.py actually wrote.
SOURCE_CRS = "EPSG:26915"

REPO_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = REPO_ROOT / "templates"
HTML_TEMPLATE = (TEMPLATES_DIR / "html_template.html").read_text()
JS_TEMPLATE = (TEMPLATES_DIR / "js_template.js").read_text()
ENGINE_TEMPLATE = (TEMPLATES_DIR / "graph_engine.js").read_text()


def build_graph():
    graph = bwca_graph()

    graph.load_lakes("Data/processed/bwca_lakes.parquet")
    graph.load_campsites("Data/processed/bwca_campsites.parquet")
    graph.connect_campsites()

    graph.load_portages("Data/processed/bwca_portages.parquet")
    graph.connect_portages()

    graph.load_rivers("Data/processed/bwca_rivers.parquet")
    graph.connect_rivers()

    # ADDED: entry points weren't in this rewrite yet - wiring them back in
    # using the same unique_guid-keyed pattern as everything else.
    graph.load_entry_points("Data/processed/entry_points_joined.parquet")
    graph.connect_entry_points()

    return graph


def lakes_geojson(graph):
    lakes = list(graph.lakes.values())
    gdf = gpd.GeoDataFrame(
        {
            # unique_guid ADDED - this is the real identity key the routing
            # graph (graph_engine.js) now looks up lakes by. fw_id is kept
            # only because other code/popups may still reference it for
            # display; it is NOT safe to use for lake identity (fw_id=88888
            # alone collides 6 unrelated lakes - Saganaga, East Vermilion,
            # Bearskin, Jenny x2, Gull - and most other rows have a null
            # fw_id). See graph_engine.js's IDENTITY NOTE.
            "unique_guid": [lake.unique_guid for lake in lakes],
            "fw_id": [lake.fw_id for lake in lakes],
            "name": [lake.name for lake in lakes],
            "acres": [lake.acres for lake in lakes],
            "shoreline_miles": [lake.shoreline_miles for lake in lakes],
            "num_campsites": [len(lake.campsites) for lake in lakes],
        },
        geometry=[lake.geometry for lake in lakes],
        crs=SOURCE_CRS,
    )
    return json.loads(gdf.to_crs(4326).to_json())


def campsites_geojson(graph):
    campsites = list(graph.campsites.values())
    gdf = gpd.GeoDataFrame(
        {
            "camp_id": [c.camp_id for c in campsites],
            "lake_name": [c.lake_name for c in campsites],
            "status": [c.status for c in campsites],
            "district": [c.district for c in campsites],
            "distance_to_lake": [c.distance_to_lake for c in campsites],
        },
        geometry=[c.geometry for c in campsites],
        crs=SOURCE_CRS,
    )
    return json.loads(gdf.to_crs(4326).to_json())


def portages_geojson(graph):
    portages = graph.portages
    gdf = gpd.GeoDataFrame(
        {
            "portage_number": [p.portage_number for p in portages],
            "usfs_id": [p.usfs_id for p in portages],
            "waterbody": [p.waterbody for p in portages],
            "lake_a": [p.lake_a.name for p in portages],
            "lake_b": [p.lake_b.name for p in portages],
            # unique_guid_a/b ADDED - the real routing keys. fw_id_a/b are
            # kept for the debug popup display only (see js_template.js) -
            # they must never be used to look anything up in the graph.
            "unique_guid_a": [p.lake_a.unique_guid for p in portages],
            "unique_guid_b": [p.lake_b.unique_guid for p in portages],
            "fw_id_a": [p.lake_a.fw_id for p in portages],
            "fw_id_b": [p.lake_b.fw_id for p in portages],
            "length_rods": [p.length_rods for p in portages],
            "dist_lake_a": [p.dist_lake_a for p in portages],
            "dist_lake_b": [p.dist_lake_b for p in portages],
            "lake_match_uncertain": [bool(p.lake_match_uncertain) for p in portages],
        },
        geometry=[p.geometry for p in portages],
        crs=SOURCE_CRS,
    )
    return json.loads(gdf.to_crs(4326).to_json())


def rivers_geojson(graph):
    rivers = graph.rivers
    gdf = gpd.GeoDataFrame(
        {
            "name": [r.name if isinstance(r.name, str) else None for r in rivers],
            "strm_type": [r.strm_type for r in rivers],
            "routable": [bool(r.routable) for r in rivers],
            "node_a": [r.node_a for r in rivers],
            "node_b": [r.node_b for r in rivers],
            # unique_guid_a/b ADDED - same reasoning as portages_geojson above.
            "unique_guid_a": [r.lake_a.unique_guid if r.lake_a else None for r in rivers],
            "unique_guid_b": [r.lake_b.unique_guid if r.lake_b else None for r in rivers],
            "fw_id_a": [r.lake_a.fw_id if r.lake_a else None for r in rivers],
            "fw_id_b": [r.lake_b.fw_id if r.lake_b else None for r in rivers],
            "length_m": [r.length_m for r in rivers],
        },
        geometry=[r.geometry for r in rivers],
        crs=SOURCE_CRS,
    )
    return json.loads(gdf.to_crs(4326).to_json())


def entry_points_geojson(graph):
    """ADDED - entry points weren't part of this rewrite yet. Follows the
    same unique_guid-keyed pattern as everything else; connect_entry_points()
    (already in your bwca_graph.py, keyed by lake_unid) fills in e.lake."""
    entries = list(graph.entry_points.values())
    gdf = gpd.GeoDataFrame(
        {
            "code": [e.code for e in entries],
            "name": [e.name for e in entries],
            "unique_guid": [e.lake_unid for e in entries],
            "fw_id": [e.fw_id for e in entries],
            "lake_name": [e.lake.name if e.lake else None for e in entries],
        },
        geometry=[e.geometry for e in entries],
        crs=SOURCE_CRS,
    )
    return json.loads(gdf.to_crs(4326).to_json())


def build_paddle_edges(stem_path):
    """Runs scripts/build_paddle_edges.js to precompute the fixed portage/
    river/lake-vertex paddle-edge mesh, replaying graph_engine.js's exact
    client-side wiring logic once at build time instead of once per page
    load - see docs/graph_map_design.md's "Paddle-edge precomputation"
    section. Requires `npm install` to have been run (package.json pins
    @turf/turf to the same major version the browser loads from CDN)."""
    result = subprocess.run(
        ["node", "scripts/build_paddle_edges.js", str(stem_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise RuntimeError(
            "scripts/build_paddle_edges.js failed - run `npm install` from the "
            "repo root if @turf/turf isn't installed yet."
        )
    print(result.stdout.strip())


def render_map(graph, out_path="maps/bwca_graph_map.html"):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    js_filename = out_path.stem + ".js"
    engine_filename = out_path.stem + "_engine.js"
    lakes_filename = out_path.stem + "_lakes.json"
    campsites_filename = out_path.stem + "_campsites.json"
    portages_filename = out_path.stem + "_portages.json"
    rivers_filename = out_path.stem + "_rivers.json"
    entry_points_filename = out_path.stem + "_entry_points.json"  # ADDED
    paddle_edges_filename = out_path.stem + "_paddle_edges.json"

    html = (
        HTML_TEMPLATE
        .replace("__JS_FILENAME__", js_filename)
        .replace("__ENGINE_FILENAME__", engine_filename)
    )
    js = (
        JS_TEMPLATE
        .replace("__LAKES_URL__", lakes_filename)
        .replace("__CAMPSITES_URL__", campsites_filename)
        .replace("__PORTAGES_URL__", portages_filename)
        .replace("__RIVERS_URL__", rivers_filename)
        .replace("__ENTRY_POINTS_URL__", entry_points_filename)  # ADDED
        .replace("__PADDLE_EDGES_URL__", paddle_edges_filename)
    )

    written = [out_path, out_path.parent / js_filename, out_path.parent / engine_filename]
    out_path.write_text(html)
    written[1].write_text(js)
    written[2].write_text(ENGINE_TEMPLATE)

    for filename, data in (
        (lakes_filename, lakes_geojson(graph)),
        (campsites_filename, campsites_geojson(graph)),
        (portages_filename, portages_geojson(graph)),
        (rivers_filename, rivers_geojson(graph)),
        (entry_points_filename, entry_points_geojson(graph)),  # ADDED
    ):
        data_path = out_path.parent / filename
        data_path.write_text(json.dumps(data))
        written.append(data_path)

    build_paddle_edges(out_path.parent / out_path.stem)
    written.append(out_path.parent / paddle_edges_filename)

    print("Wrote " + ", ".join(str(p) for p in written))


if __name__ == "__main__":
    render_map(build_graph())