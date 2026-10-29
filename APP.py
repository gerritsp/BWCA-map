import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from models.bwca_graph import bwca_graph
from Scripts.build_entry_points import build_entry_points
from Scripts.build_lake_access_index import build_access_index, write_access_index
from Scripts.repair_routing_graph import repair_routing_graph
from Scripts.river_topology import river_component_labels

# Data/processed/*.parquet is written in NAD83 / UTM zone 15N (see CLAUDE.md's
# CRS gotcha) - the graph's Lake/Campsite objects carry that geometry as-is,
# with no CRS attached to the dataclass itself, so this has to match whatever
# fileCreator.py/portageCreator.py actually wrote.
SOURCE_CRS = "EPSG:26915"
PORTAGE_LAKE_TOLERANCE_M = 25.0
MIN_PORTAGE_GEOMETRY_M = 0.5
BOUNDARY_PATH = (
    "Data/Boundaries/bdry_boundary_waters_canoe_area/"
    "bdry_boundary_waters_canoe_area.gdb"
)
BOUNDARY_LAYER = "boundary_waters_canoe_area_wilderness"
PORTAGE_CORRECTIONS_PATH = "Data/portage_geometry_corrections.geojson"

REPO_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = REPO_ROOT / "Templates"
HTML_TEMPLATE = (TEMPLATES_DIR / "html_template.html").read_text(encoding="utf-8")
JS_TEMPLATE = (TEMPLATES_DIR / "js_template.js").read_text(encoding="utf-8")
ENGINE_TEMPLATE = (TEMPLATES_DIR / "graph_engine.js").read_text(encoding="utf-8")


def build_graph():
    graph = bwca_graph()

    graph.load_lakes(REPO_ROOT / "Data/processed/bwca_lakes.parquet")
    for dataset, load, connect in (
        ("bwca_campsites_river", graph.load_campsites, graph.connect_campsites),
        ("portages_final_snapped", graph.load_portages, graph.connect_portages),
        ("bwca_rivers_lines", graph.load_rivers, graph.connect_rivers),
    ):
        path = REPO_ROOT / "Data/processed" / (dataset + ".parquet")
        if path.exists():
            load(path)
            if dataset == "portages_final_snapped":
                _apply_portage_geometry_corrections(graph)
            connect()
        else:
            print(f"Optional layer unavailable: {dataset}")

    return graph


def _apply_portage_geometry_corrections(graph):
    """Apply small, source-traceable fixes without rewriting source parquet."""
    for portage in graph.portages.values():
        portage.geometry_source = "processed_portage_layer"

    path = REPO_ROOT / PORTAGE_CORRECTIONS_PATH
    if not path.exists():
        return
    corrections = gpd.read_file(path)
    if corrections.crs is None:
        raise ValueError(f"Portage correction file has no CRS: {path}")
    corrections = corrections.to_crs(SOURCE_CRS)
    for _, correction in corrections.iterrows():
        number = int(correction["portage_number"])
        portage = graph.portages.get(number)
        if portage is None:
            raise ValueError(f"Portage correction references missing portage {number}")
        if str(int(portage.usfs_id)) != str(int(correction["usfs_id"])):
            raise ValueError(f"Portage correction USFS ID mismatch for {number}")
        if correction.geometry.is_empty or not correction.geometry.is_valid:
            raise ValueError(f"Portage correction has invalid geometry for {number}")
        def correction_guid(value):
            if value is None or (isinstance(value, float) and value != value):
                return None
            return str(value)

        start_guid = correction_guid(correction.get("start_lake_guid"))
        end_guid = correction_guid(correction.get("end_lake_guid"))
        for guid in (start_guid, end_guid):
            if guid is not None and guid not in graph.lakes:
                raise ValueError(
                    f"Portage correction references an unknown lake for {number}"
                )

        portage.geometry = correction.geometry
        portage.start_unid = start_guid
        portage.end_unid = end_guid
        portage.start_snapped = False
        portage.end_snapped = False
        portage.geometry_source = "usfs_trail_correction"


def lakes_geojson(graph):
    lakes = list(graph.lakes.values())
    gdf = gpd.GeoDataFrame(
        {
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


def _portage_endpoint_routes(graph, portages):
    """Resolve portage landings only when geometry supports the connection.

    The legacy portage preparation assigned every endpoint to its nearest lake,
    even when that lake was kilometres away.  Those IDs remain available for
    labels and source reconciliation, but routing uses a lake only within the
    same 25 m tolerance as the browser.  Otherwise a nearby mapped river is a
    valid anchor; anything else is explicitly left for review.
    """
    rivers = [river for river in graph.rivers.values() if river.routable]
    river_gdf = gpd.GeoDataFrame(
        {"river_id": [river.river_id for river in rivers]},
        geometry=[river.geometry for river in rivers],
        crs=SOURCE_CRS,
    )
    river_index = river_gdf.sindex if not river_gdf.empty else None

    def resolve(point, lake):
        lake_distance = point.distance(lake.geometry) if lake is not None else None
        if lake is not None and lake_distance <= PORTAGE_LAKE_TOLERANCE_M:
            return {
                "type": "lake",
                "lake_guid": lake.unique_guid,
                "river_id": None,
                "offset_m": round(float(lake_distance), 1),
                "issue": None,
            }

        if river_index is not None:
            nearest = list(river_index.nearest(point, return_all=False))[1]
            if len(nearest):
                river = river_gdf.iloc[int(nearest[0])]
                river_distance = float(point.distance(river.geometry))
                if river_distance <= PORTAGE_LAKE_TOLERANCE_M:
                    return {
                        "type": "river",
                        "lake_guid": None,
                        "river_id": int(river.river_id),
                        "offset_m": round(river_distance, 1),
                        "issue": None,
                    }

        return {
            "type": "unresolved",
            "lake_guid": None,
            "river_id": None,
            "offset_m": round(float(lake_distance), 1)
            if lake_distance is not None else None,
            "issue": "no_nearby_water",
        }

    result = []
    for portage in portages:
        coords = list(portage.geometry.coords)
        geometry_valid = (
            portage.geometry.is_valid
            and len(coords) >= 2
            and float(portage.geometry.length) >= MIN_PORTAGE_GEOMETRY_M
        )
        if not geometry_valid:
            unresolved = {
                "type": "unresolved",
                "lake_guid": None,
                "river_id": None,
                "offset_m": None,
                "issue": "invalid_geometry",
            }
            result.append((unresolved.copy(), unresolved.copy()))
            continue
        result.append((
            resolve(Point(coords[0]), portage.lake_a),
            resolve(Point(coords[-1]), portage.lake_b),
        ))
    return result


def portages_geojson(graph):
    portages = list(graph.portages.values())
    endpoint_routes = _portage_endpoint_routes(graph, portages)
    gdf = gpd.GeoDataFrame(
        {
            "portage_number": [p.portage_num for p in portages],
            "usfs_id": [p.usfs_id for p in portages],
            "name": [p.name for p in portages],
            "lake_a": [p.lake_a.name if p.lake_a else p.lake1_name for p in portages],
            "lake_b": [p.lake_b.name if p.lake_b else p.lake2_name for p in portages],
            "unique_guid_a": [p.lake_a.unique_guid if p.lake_a else None for p in portages],
            "unique_guid_b": [p.lake_b.unique_guid if p.lake_b else None for p in portages],
            "fw_id_a": [p.lake_a.fw_id if p.lake_a else None for p in portages],
            "fw_id_b": [p.lake_b.fw_id if p.lake_b else None for p in portages],
            "length_rods": [p.length_rods for p in portages],
            "start_snapped": [bool(p.start_snapped) for p in portages],
            "end_snapped": [bool(p.end_snapped) for p in portages],
            "geometry_source": [p.geometry_source for p in portages],
            "routing_type_a": [route[0]["type"] for route in endpoint_routes],
            "routing_type_b": [route[1]["type"] for route in endpoint_routes],
            "routing_lake_guid_a": [route[0]["lake_guid"] for route in endpoint_routes],
            "routing_lake_guid_b": [route[1]["lake_guid"] for route in endpoint_routes],
            "routing_river_id_a": [route[0]["river_id"] for route in endpoint_routes],
            "routing_river_id_b": [route[1]["river_id"] for route in endpoint_routes],
            "routing_offset_m_a": [route[0]["offset_m"] for route in endpoint_routes],
            "routing_offset_m_b": [route[1]["offset_m"] for route in endpoint_routes],
            "routing_issue_a": [route[0]["issue"] for route in endpoint_routes],
            "routing_issue_b": [route[1]["issue"] for route in endpoint_routes],
            "routing_geometry_valid": [
                all(side["issue"] != "invalid_geometry" for side in route)
                for route in endpoint_routes
            ],
            "routing_status": [
                "connected" if all(side["type"] != "unresolved" for side in route)
                else "review"
                for route in endpoint_routes
            ],
        },
        geometry=[p.geometry for p in portages],
        crs=SOURCE_CRS,
    )
    return json.loads(gdf.to_crs(4326).to_json())


def rivers_geojson(graph):
    rivers = list(graph.rivers.values())
    routable_rows = [
        {
            "river_id": river.river_id,
            "node_a": river.node_a,
            "node_b": river.node_b,
            "geometry": river.geometry,
        }
        for river in rivers if river.routable
    ]
    component_by_id = river_component_labels(routable_rows)
    gdf = gpd.GeoDataFrame(
        {
            "river_id": [r.river_id for r in rivers],
            "name": [r.name if isinstance(r.name, str) else None for r in rivers],
            "strm_type": [r.strm_type for r in rivers],
            "routable": [bool(r.routable) for r in rivers],
            "node_a": [r.node_a for r in rivers],
            "node_b": [r.node_b for r in rivers],
            "routing_component": [component_by_id.get(r.river_id) for r in rivers],
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


def fires_geojson(path="Data/processed/fires2026.parquet", simplify_tolerance=0.0003):
    """ADDED - burn-area polygons for the "avoid burn areas" routing toggle.
    You mentioned your fires data is already simplified/loading quickly, so
    pass simplify_tolerance=None here if re-simplifying is unnecessary or
    unwanted - left the parameter in in case a future, un-simplified fire
    file gets swapped in."""
    path = REPO_ROOT / path
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    fires = gpd.read_parquet(path)
    if fires.crs is None:
        fires = fires.set_crs(SOURCE_CRS)
    fires = fires.to_crs(4326)
    if simplify_tolerance:
        fires["geometry"] = fires.geometry.simplify(simplify_tolerance, preserve_topology=True)
    return json.loads(fires.to_json())


def boundary_geojson(path=BOUNDARY_PATH, simplify_tolerance=0.0001):
    """Return the legal BWCA units used to frame and constrain the map."""
    path = REPO_ROOT / path
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    boundary = gpd.read_file(path, layer=BOUNDARY_LAYER).to_crs(4326)
    boundary = boundary[["BWCA_UNIT", "geometry"]].rename(
        columns={"BWCA_UNIT": "unit"}
    )
    if simplify_tolerance:
        boundary["geometry"] = boundary.geometry.simplify(
            simplify_tolerance, preserve_topology=True
        )
    return json.loads(boundary.to_json())


def build_paddle_edges(stem_path):
    """Runs scripts/build_paddle_edges.js to precompute the fixed portage/
    river/lake-vertex paddle-edge mesh, replaying graph_engine.js's exact
    client-side wiring logic once at build time instead of once per page
    load - see docs/graph_map_design.md's "Paddle-edge precomputation"
    section. Requires `npm install` to have been run (package.json pins
    @turf/turf to the same major version the browser loads from CDN).
    Also reads <stem>_fires.json (written by render_map() before this is
    called) so every precomputed edge gets a crossesBurn flag - see
    graph_engine.js's burn-area awareness note."""
    result = subprocess.run(
        ["node", "Scripts/build_paddle_edges.js", str(stem_path)],
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
    out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    js_filename = out_path.stem + ".js"
    engine_filename = out_path.stem + "_engine.js"
    lakes_filename = out_path.stem + "_lakes.json"
    campsites_filename = out_path.stem + "_campsites.json"
    portages_filename = out_path.stem + "_portages.json"
    rivers_filename = out_path.stem + "_rivers.json"
    entry_points_filename = out_path.stem + "_entry_points.json"
    boundary_filename = out_path.stem + "_boundary.json"
    fires_filename = out_path.stem + "_fires.json"  # ADDED
    paddle_edges_filename = out_path.stem + "_paddle_edges.json"
    access_index_filename = "lake_access_index.json"

    html = (
        HTML_TEMPLATE
        .replace("__JS_FILENAME__", js_filename)
        .replace("__ENGINE_FILENAME__", engine_filename)
    )
    js = (
        JS_TEMPLATE
        .replace("__LAKES_URL__", lakes_filename)
        .replace("__LAKE_BUNDLES_URL__", "fisheries/")
        .replace("__CAMPSITES_URL__", campsites_filename)
        .replace("__PORTAGES_URL__", portages_filename)
        .replace("__RIVERS_URL__", rivers_filename)
        .replace("__ENTRY_POINTS_URL__", entry_points_filename)
        .replace("__BOUNDARY_URL__", boundary_filename)
        .replace("__FIRES_URL__", fires_filename)  # ADDED
        .replace("__PADDLE_EDGES_URL__", paddle_edges_filename)
    )

    written = [out_path, out_path.parent / js_filename, out_path.parent / engine_filename]
    out_path.write_text(html, encoding="utf-8")
    written[1].write_text(js, encoding="utf-8")
    written[2].write_text(ENGINE_TEMPLATE, encoding="utf-8")

    rendered_layers = {}
    for layer_name, filename, data in (
        ("lakes", lakes_filename, lakes_geojson(graph)),
        ("campsites", campsites_filename, campsites_geojson(graph)),
        ("portages", portages_filename, portages_geojson(graph)),
        ("rivers", rivers_filename, rivers_geojson(graph)),
        ("boundary", boundary_filename, boundary_geojson()),
        ("fires", fires_filename, fires_geojson()),  # ADDED
    ):
        data_path = out_path.parent / filename
        data_path.write_text(json.dumps(data), encoding="utf-8")
        written.append(data_path)
        rendered_layers[layer_name] = data

    entry_points = build_entry_points(
        rendered_layers["lakes"],
        rendered_layers["portages"],
        rendered_layers["rivers"],
        rendered_layers["boundary"],
    )
    entry_points_path = out_path.parent / entry_points_filename
    entry_points_path.write_text(json.dumps(entry_points), encoding="utf-8")
    written.append(entry_points_path)
    rendered_layers["entry_points"] = entry_points

    access_index = build_access_index(
        rendered_layers["portages"],
        rendered_layers["rivers"],
        rendered_layers["entry_points"],
    )
    searchable_entry_codes = {entry["code"] for entry in access_index["entries"]}
    for feature in entry_points["features"]:
        properties = feature["properties"]
        if properties["code"] not in searchable_entry_codes:
            properties["routing_status"] = "review"
            properties["routing_issue"] = "no_verified_lake_route"
    entry_points_path.write_text(json.dumps(entry_points), encoding="utf-8")
    access_index_path = out_path.parent / access_index_filename
    written.extend(write_access_index(access_index, access_index_path))

    # build_paddle_edges.js reads <stem>_fires.json too now - it must exist
    # by this point, which it does since the loop above already wrote it.
    build_paddle_edges(out_path.parent / out_path.stem)
    repair_routing_graph(out_path.parent / out_path.stem)
    written.append(out_path.parent / paddle_edges_filename)

    print("Wrote " + ", ".join(str(p) for p in written))


if __name__ == "__main__":
    render_map(build_graph())
    # Refresh search counts from the same local campsite dataset after every build.
    subprocess.run([sys.executable, str(REPO_ROOT / "Scripts/build_search_index.py")],
                   cwd=REPO_ROOT, check=True)
