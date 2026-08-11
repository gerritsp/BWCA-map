import json
from pathlib import Path

import geopandas as gpd

from models.bwca_graph import bwca_graph

# Data/processed/*.parquet is written in NAD83 / UTM zone 15N (see CLAUDE.md's
# CRS gotcha) - the graph's Lake/Campsite objects carry that geometry as-is,
# with no CRS attached to the dataclass itself, so this has to match whatever
# fileCreator.py/portageCreator.py actually wrote.
SOURCE_CRS = "EPSG:26915"

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>BWCA Map</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
    <style>
        html, body, #map { height: 100%; margin: 0; font-family: system-ui, sans-serif; }
        .legend {
            background: white;
            padding: 10px 12px;
            border-radius: 6px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-size: 13px;
            line-height: 1.6;
        }
    </style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/@turf/turf@6/turf.min.js"></script>
<script>
    const lakes = __LAKES_GEOJSON__;
    const campsites = __CAMPSITES_GEOJSON__;
    const portages = __PORTAGES_GEOJSON__;
    const entryPoints = __ENTRY_POINTS_GEOJSON__;
    const burnAreas = __BURN_AREAS_GEOJSON__;

    const map = L.map("map");
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);

    const lakesLayer = L.geoJSON(lakes, {
        style: {
            color: "#2b6cb0",
            weight: 1,
            fillColor: "#63b3ed",
            fillOpacity: 0.35
        },
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            layer.bindTooltip(
                `${p.name} &mdash; ${p.acres.toFixed(1)} acres, ${p.num_campsites} campsite(s)`
            );
        }
    }).addTo(map);

    // NOTE: the new portage dataset has no lake_match_uncertain / dist_lake_a
    // / dist_lake_b fields (those were specific to the old GPX-derived
    // dataset's >25m confidence check) - single style, and any missing field
    // just falls back to "N/A" / a generic label rather than crashing.
    const PORTAGE_STYLE = { color: "#0f5c2e", weight: 3, opacity: 0.9 };

    const portagesLayer = L.geoJSON(portages, {
        style: PORTAGE_STYLE,
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            const rods = p.length_rods == null ? "N/A" : `${p.length_rods.toFixed(1)} rods`;
            const meters = p.length_meters == null ? "N/A" : `${p.length_meters.toFixed(0)} m`;
            const miles = p.length_miles == null ? "N/A" : `${p.length_miles.toFixed(2)} mi`;
            const label = p.name || `${p.lake1_name || "?"} &harr; ${p.lake2_name || "?"}`;

            layer.bindPopup(
                `<b>Portage #${p.portage_num}</b> (USFS ID ${p.usfs_id})<br>` +
                `${label} &mdash; ${rods} (${meters} / ${miles})<br>` +
                `${p.lake_a || "?"} &rarr; ${p.lake_b || "?"}<br>` +
                `<span style="font-size:11px; color:#555;">` +
                `fw_id_a=${p.fw_id_a ?? 'N/A'} &middot; fw_id_b=${p.fw_id_b ?? 'N/A'}</span>`
            );
        }
    }).addTo(map);

    const campsitesLayer = L.markerClusterGroup();
    L.geoJSON(campsites, {
        pointToLayer: function (feature, latlng) {
            return L.circleMarker(latlng, {
                radius: 4,
                color: "#c53030",
                fillColor: "#c53030",
                fillOpacity: 1
            });
        },
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            layer.bindPopup(
                `<b>Campsite:</b> ${p.camp_id}<br>` +
                `<b>Lake:</b> ${p.lake_name}<br>` +
                `<b>Status:</b> ${p.status}<br>` +
                `<b>District:</b> ${p.district}<br>` +
                `<b>Distance to matched lake:</b> ${p.distance_to_lake.toFixed(1)} m`
            );
        }
    }).addTo(campsitesLayer);
    campsitesLayer.addTo(map);

    // Entry points: small distinct marker (not clustered - there are far
    // fewer of these than campsites, and losing them into a cluster at low
    // zoom would bury a category people specifically look for).
    const entryPointsLayer = L.geoJSON(entryPoints, {
        pointToLayer: function (feature, latlng) {
            return L.marker(latlng, {
                icon: L.divIcon({
                    className: "entry-point-icon",
                    html: '<div style="background:#f59e0b;border:2px solid white;' +
                          'border-radius:50%;width:14px;height:14px;' +
                          'box-shadow:0 0 3px rgba(0,0,0,0.5);"></div>',
                    iconSize: [14, 14],
                    iconAnchor: [7, 7]
                })
            });
        },
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            layer.bindPopup(
                `<b>Entry Point ${p.code ?? ""}</b><br>` +
                `${p.name || "(unnamed)"}<br>` +
                `<span style="font-size:11px; color:#555;">Lake: ${p.lake_name || "unmatched"}</span>`
            );
        }
    }).addTo(map);

    // Burn areas: rendered but excluded from routing only when the checkbox
    // is checked (see avoidBurnAreas below). Kept as its own layer so it can
    // be toggled visually independent of the routing behavior if you ever
    // want "show but don't avoid" as a separate state.
    const BURN_AREA_STYLE = {
        color: "#9a3412",
        weight: 1.5,
        fillColor: "#ea580c",
        fillOpacity: 0.35,
        dashArray: "4 3"
    };
    const burnAreasLayer = L.geoJSON(burnAreas, {
        style: BURN_AREA_STYLE,
        onEachFeature: function (feature, layer) {
            const p = feature.properties || {};
            const label = p.name || p.fire_name || "Burn area";
            const year = p.year || p.fire_year;
            layer.bindTooltip(year ? `${label} (${year})` : label);
        }
    }).addTo(map);

    let avoidBurnAreas = false;

    const legend = L.control({ position: "bottomright" });
    legend.onAdd = function () {
        const div = L.DomUtil.create("div", "legend");
        div.innerHTML = `
            <b>Legend</b><br>
            <span style="display:inline-block;width:20px;border-top:3px solid #0f5c2e;margin-right:4px;"></span>Portage<br>
            <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#f59e0b;border:2px solid white;box-shadow:0 0 2px rgba(0,0,0,0.5);margin-right:4px;vertical-align:middle;"></span>Entry point<br>
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#c53030;margin-right:6px;vertical-align:middle;"></span>Campsite<br>
            <span style="display:inline-block;width:14px;height:10px;background:#ea580c;opacity:0.5;border:1px dashed #9a3412;margin-right:4px;vertical-align:middle;"></span>Burn area
        `;
        return div;
    };
    legend.addTo(map);

    map.fitBounds(lakesLayer.getBounds());

    // --- Route finding: portages (surveyed lines) + paddle edges across lakes ---
    // Paddle edges are a visibility-graph shortcut, not a full solve: for two
    // points on the same lake, if the straight line between them stays inside
    // the lake polygon, it's added as a paddle edge weighted by straight-line
    // distance. A chord blocked by an island (or crossing the gap between two
    // disjoint pieces of a lake split by the boundary clip - see CLAUDE.md's
    // CRS/clip gotcha) just gets no edge rather than routing around it - a
    // safe undercount, not a wrong route, and good enough for a demo.
    const ROD_TO_METERS = 5.0292;

    const lakesById = new Map(lakes.features.map((f) => [f.properties.fw_id, f]));
    const nodes = new Map(); // nodeId -> { lakeId, coord: [lon, lat] }
    const adjacency = new Map(); // nodeId -> [{ to, weight, kind, geometry }]
    const accessPointsByLake = new Map(); // lakeId -> [nodeId, ...]

    // Checked once per edge at creation time (not per-search) since burn
    // areas don't change during a session - keeps route lookups cheap even
    // though turf.booleanIntersects itself isn't free.
    function edgeCrossesBurnArea(lineGeometry) {
        if (!burnAreas.features || burnAreas.features.length === 0) return false;
        const line = turf.feature(lineGeometry);
        return burnAreas.features.some((burn) => {
            try {
                return turf.booleanIntersects(line, burn);
            } catch {
                return false; // malformed burn polygon shouldn't take down routing
            }
        });
    }

    function addEdge(a, b, weight, kind, geometry) {
        const crossesBurn = edgeCrossesBurnArea(geometry);
        adjacency.get(a).push({ to: b, weight, kind, geometry, crossesBurn });
        adjacency.get(b).push({ to: a, weight, kind, geometry, crossesBurn });
    }

    const LAKE_MATCH_BUFFER_METERS = 25;
    const MAX_LAKE_VERTICES = 24;
    const SIMPLIFY_TOLERANCE_DEG = 0.00015; // ~15m at BWCA's latitude

    const simplifiedLakeCache = new Map();
    function simplifiedLake(lakeId) {
        if (!simplifiedLakeCache.has(lakeId)) {
            const feature = lakesById.get(lakeId);
            let simplified = null;
            if (feature) {
                try {
                    simplified = turf.simplify(feature, { tolerance: SIMPLIFY_TOLERANCE_DEG, highQuality: false });
                } catch {
                    simplified = feature;
                }
            }
            simplifiedLakeCache.set(lakeId, simplified);
        }
        return simplifiedLakeCache.get(lakeId);
    }

    const preparedLakeCache = new Map(); // lakeId -> { polygon, boundary } | null
    function preparedLake(lakeId) {
        if (!preparedLakeCache.has(lakeId)) {
            const simplified = simplifiedLake(lakeId);
            if (!simplified) {
                preparedLakeCache.set(lakeId, null);
            } else {
                const polygon = turf.buffer(simplified, LAKE_MATCH_BUFFER_METERS / 1000, { units: "kilometers" });
                preparedLakeCache.set(lakeId, { polygon, boundary: turf.polygonToLine(polygon) });
            }
        }
        return preparedLakeCache.get(lakeId);
    }

    function lineStaysInLake(coordA, coordB, lakeId) {
        const prepared = preparedLake(lakeId);
        if (!prepared) return false;
        if (!turf.booleanPointInPolygon(coordA, prepared.polygon)) return false;
        if (!turf.booleanPointInPolygon(coordB, prepared.polygon)) return false;
        const line = turf.lineString([coordA, coordB]);
        return turf.lineIntersect(line, prepared.boundary).features.length === 0;
    }

    const vertexGraphBuilt = new Set();

    function lakeBoundaryPoints(lakeId) {
        const simplified = simplifiedLake(lakeId);
        if (!simplified) return [];
        const rings = simplified.geometry.type === "Polygon"
            ? simplified.geometry.coordinates
            : simplified.geometry.coordinates.flat();

        let points = rings.flatMap((ring) => ring.slice(0, -1));
        if (points.length > MAX_LAKE_VERTICES) {
            const step = Math.ceil(points.length / MAX_LAKE_VERTICES);
            points = points.filter((_, i) => i % step === 0);
        }
        return points;
    }

    function buildLakeVertexGraph(lakeId) {
        if (vertexGraphBuilt.has(lakeId)) return;
        vertexGraphBuilt.add(lakeId);
        lakeBoundaryPoints(lakeId).forEach((coord, i) => {
            addNode(`vertex:${lakeId}:${i}`, lakeId, coord);
        });
    }

    function wirePaddleEdges(nodeId, lakeId, coord) {
        if (!lakesById.get(lakeId)) return;
        const accessPoints = accessPointsByLake.get(lakeId) || [];
        if (accessPoints.length >= 1 && !vertexGraphBuilt.has(lakeId)) {
            buildLakeVertexGraph(lakeId);
        }
        for (const otherId of accessPoints) {
            const otherCoord = nodes.get(otherId).coord;
            if (lineStaysInLake(coord, otherCoord, lakeId)) {
                const distance = turf.distance(coord, otherCoord, { units: "meters" });
                addEdge(nodeId, otherId, distance, "paddle", turf.lineString([coord, otherCoord]).geometry);
            }
        }
    }

    function addNode(nodeId, lakeId, coord) {
        if (nodes.has(nodeId)) return;
        nodes.set(nodeId, { lakeId, coord });
        adjacency.set(nodeId, []);
        wirePaddleEdges(nodeId, lakeId, coord);
        if (!accessPointsByLake.has(lakeId)) accessPointsByLake.set(lakeId, []);
        accessPointsByLake.get(lakeId).push(nodeId);
    }

    function removeNode(nodeId) {
        if (!nodes.has(nodeId)) return;
        const node = nodes.get(nodeId);
        for (const edge of adjacency.get(nodeId)) {
            const neighborEdges = adjacency.get(edge.to);
            const idx = neighborEdges.findIndex((e) => e.to === nodeId);
            if (idx !== -1) neighborEdges.splice(idx, 1);
        }
        adjacency.delete(nodeId);
        nodes.delete(nodeId);
        const lakePoints = accessPointsByLake.get(node.lakeId);
        if (lakePoints) {
            const idx = lakePoints.indexOf(nodeId);
            if (idx !== -1) lakePoints.splice(idx, 1);
        }
    }

    // One portage = one edge between its two lake-side endpoints, using its
    // real surveyed geometry (not a straight line) for rendering.
    for (const feature of portages.features) {
        const p = feature.properties;
        const coords = feature.geometry.coordinates;
        const nodeA = `portage:${p.portage_num}:a`;
        const nodeB = `portage:${p.portage_num}:b`;
        addNode(nodeA, p.fw_id_a, coords[0]);
        addNode(nodeB, p.fw_id_b, coords[coords.length - 1]);
        addEdge(nodeA, nodeB, p.length_rods * ROD_TO_METERS, "portage", feature.geometry);
    }

    function findLakeAtPoint(coord) {
        for (const feature of lakes.features) {
            if (turf.booleanPointInPolygon(coord, feature)) return feature;
        }
        return null;
    }

    function nearestLake(coord) {
        let best = null;
        let bestDist = Infinity;
        let bestCoord = coord;
        for (const feature of lakes.features) {
            const boundary = turf.polygonToLine(feature);
            const nearest = turf.nearestPointOnLine(boundary, coord, { units: "meters" });
            if (nearest.properties.dist < bestDist) {
                bestDist = nearest.properties.dist;
                best = feature;
                bestCoord = nearest.geometry.coordinates;
            }
        }
        return { feature: best, coord: bestCoord, distance: bestDist };
    }

    function dijkstra(startNode, endNode) {
        const dist = new Map([[startNode, 0]]);
        const prev = new Map();
        const visited = new Set();
        const queue = [[0, startNode]];

        while (queue.length) {
            queue.sort((a, b) => a[0] - b[0]);
            const [d, u] = queue.shift();
            if (visited.has(u)) continue;
            visited.add(u);
            if (u === endNode) break;

            for (const edge of adjacency.get(u) || []) {
                if (avoidBurnAreas && edge.crossesBurn) continue;
                const alt = d + edge.weight;
                if (alt < (dist.get(edge.to) ?? Infinity)) {
                    dist.set(edge.to, alt);
                    prev.set(edge.to, u);
                    queue.push([alt, edge.to]);
                }
            }
        }

        if (!dist.has(endNode)) return null;

        const path = [endNode];
        let current = endNode;
        while (current !== startNode) {
            current = prev.get(current);
            path.push(current);
        }
        path.reverse();
        return { distance: dist.get(endNode), path };
    }

    let routeLayer = null;
    let markerStart = null;
    let markerEnd = null;

    function setStatus(text) {
        document.getElementById("route-status-text").textContent = text;
    }

    function clearRoute() {
        if (markerStart) map.removeLayer(markerStart);
        if (markerEnd) map.removeLayer(markerEnd);
        if (routeLayer) map.removeLayer(routeLayer);
        removeNode("start");
        removeNode("end");
        markerStart = null;
        markerEnd = null;
        routeLayer = null;
        setStatus("Click a point on a lake to start a route.");
    }

    function computeAndDrawRoute() {
        const result = dijkstra("start", "end");
        if (routeLayer) map.removeLayer(routeLayer);

        if (!result) {
            setStatus("No route found - these lakes aren't connected by any recorded portage.");
            return;
        }

        const segments = [];
        for (let i = 0; i < result.path.length - 1; i++) {
            segments.push(adjacency.get(result.path[i]).find((e) => e.to === result.path[i + 1]));
        }

        routeLayer = L.geoJSON(
            segments.map((s) => ({ type: "Feature", properties: { kind: s.kind }, geometry: s.geometry })),
            {
                style: (feature) => ({
                    color: feature.properties.kind === "portage" ? "#7c2d12" : "#1d4ed8",
                    weight: 5,
                    opacity: 0.9,
                    dashArray: feature.properties.kind === "portage" ? "2 6" : null
                })
            }
        ).addTo(map);

        const rods = segments
            .filter((s) => s.kind === "portage")
            .reduce((sum, s) => sum + s.weight / ROD_TO_METERS, 0);
        const paddleKm = segments
            .filter((s) => s.kind === "paddle")
            .reduce((sum, s) => sum + s.weight, 0) / 1000;

        setStatus(
            `Route found: ${(result.distance / 1000).toFixed(2)} km total ` +
            `(${rods.toFixed(0)} rods of portaging, ${paddleKm.toFixed(2)} km paddling).`
        );
    }

    const routeControl = L.control({ position: "topleft" });
    routeControl.onAdd = function () {
        const div = L.DomUtil.create("div", "legend");
        div.style.minWidth = "220px";
        div.innerHTML = `
            <b>Route finder</b><br>
            <span id="route-status-text">Click a point on a lake to start a route.</span>
            <div style="margin-top:8px; padding-top:8px; border-top:1px solid #e5e7eb;">
                <label style="display:flex; align-items:center; gap:6px; cursor:pointer; user-select:none;">
                    <input type="checkbox" id="avoid-burn-checkbox" style="accent-color:#ea580c; width:15px; height:15px;" />
                    <span>Avoid burn areas</span>
                </label>
            </div>
            <button id="route-clear-btn" style="margin-top:8px; width:100%; padding:5px 0; border:1px solid #d1d5db; border-radius:4px; background:#f9fafb; cursor:pointer;">Clear route</button>
        `;
        L.DomEvent.disableClickPropagation(div);
        return div;
    };
    routeControl.addTo(map);
    document.getElementById("route-clear-btn").addEventListener("click", clearRoute);
    document.getElementById("avoid-burn-checkbox").addEventListener("change", (e) => {
        avoidBurnAreas = e.target.checked;
        // Re-run the search on the existing endpoints if a route is already showing,
        // so toggling the box updates the route immediately instead of waiting for a new click.
        if (nodes.has("start") && nodes.has("end")) computeAndDrawRoute();
    });

    // Attached to the map AND to the portage/campsite layers: those layers
    // have their own popups/cluster-zoom click handling and swallow the
    // click before it would otherwise bubble up to the map's own listener.
    function handleRouteClick(latlng) {
        if (nodes.has("start") && nodes.has("end")) clearRoute();

        const clickCoord = [latlng.lng, latlng.lat];
        let lakeFeature = findLakeAtPoint(clickCoord);
        let snappedCoord = clickCoord;

        if (!lakeFeature) {
            const nearest = nearestLake(clickCoord);
            if (!nearest.feature || nearest.distance > 200) {
                setStatus("That's too far from any lake - click closer to the water.");
                return;
            }
            lakeFeature = nearest.feature;
            snappedCoord = nearest.coord;
        }

        const role = nodes.has("start") ? "end" : "start";
        addNode(role, lakeFeature.properties.fw_id, snappedCoord);
        const marker = L.marker([snappedCoord[1], snappedCoord[0]], {
            title: role === "start" ? "Start" : "End"
        }).addTo(map);

        if (role === "start") {
            markerStart = marker;
            setStatus("Click a second point to find a route.");
        } else {
            markerEnd = marker;
            computeAndDrawRoute();
        }
    }

    map.on("click", (e) => handleRouteClick(e.latlng));
    portagesLayer.on("click", (e) => handleRouteClick(e.latlng));
    campsitesLayer.on("click", (e) => handleRouteClick(e.latlng));
    entryPointsLayer.on("click", (e) => handleRouteClick(e.latlng));
</script>
</body>
</html>
"""


def build_graph():
    graph = bwca_graph()

    graph.load_lakes("Data/processed/bwca_lakes.parquet")
    graph.load_campsites("Data/processed/bwca_campsites.parquet")
    graph.load_portages("Data/processed/portages_final.parquet")
    graph.load_entry_points("Data/processed/entry_points_joined.parquet")
    graph.connect()

    return graph


def lakes_geojson(graph):
    lakes = list(graph.lakes.values())
    gdf = gpd.GeoDataFrame(
        {
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
    # graph.portages is a dict keyed by usfs_id - iterate .values(), not the
    # dict itself, or you get the keys (strings) instead of Portage objects.
    portages = list(graph.portages.values())
    gdf = gpd.GeoDataFrame(
        {
            "portage_num": [p.portage_num for p in portages],
            "usfs_id": [p.usfs_id for p in portages],
            "name": [p.name for p in portages],

            "lake1_name": [p.lake1_name for p in portages],
            "lake2_name": [p.lake2_name for p in portages],

            "lake_a": [
                p.lake_a.name if p.lake_a else None
                for p in portages
            ],
            "lake_b": [
                p.lake_b.name if p.lake_b else None
                for p in portages
            ],

            "fw_id_a": [
                p.lake_a.fw_id if p.lake_a else None
                for p in portages
            ],
            "fw_id_b": [
                p.lake_b.fw_id if p.lake_b else None
                for p in portages
            ],

            "length_rods": [p.length_rods for p in portages],
            "length_meters": [p.length_meters for p in portages],
            "length_miles": [p.length_miles for p in portages],
        },
        geometry=[p.geometry for p in portages],
        crs="EPSG:4326",  # portages_final.parquet is already lon/lat, unlike lakes/campsites (see CLAUDE.md)
    )
    return json.loads(gdf.to_json())


def burn_areas_geojson(path="Data/processed/burn_areas.parquet", crs=None):
    """crs: pass the CRS the parquet is actually tagged with if it differs
    from SOURCE_CRS - check with gpd.read_parquet(path).crs before trusting this."""
    burn = gpd.read_parquet(path)
    if crs:
        burn = burn.set_crs(crs, allow_override=True)
    if burn.crs is None:
        burn = burn.set_crs(SOURCE_CRS)
    return json.loads(burn.to_crs(4326).to_json())


def entry_points_geojson(graph):
    entries = list(graph.entry_points.values())
    gdf = gpd.GeoDataFrame(
        {
            "code": [e.code for e in entries],
            "name": [e.name for e in entries],
            "fw_id": [e.fw_id for e in entries],
            "lake_name": [e.lake.name if e.lake else None for e in entries],
        },
        geometry=[e.geometry for e in entries],
        crs=SOURCE_CRS,
    )
    return json.loads(gdf.to_crs(4326).to_json())


def render_map(graph, out_path="maps/bwca_graph_map.html", burn_areas_path="Data/processed/fires2026_reduced.parquet"):
    html = (
        HTML_TEMPLATE
        .replace("__LAKES_GEOJSON__", json.dumps(lakes_geojson(graph)))
        .replace("__CAMPSITES_GEOJSON__", json.dumps(campsites_geojson(graph)))
        .replace("__PORTAGES_GEOJSON__", json.dumps(portages_geojson(graph)))
        .replace("__ENTRY_POINTS_GEOJSON__", json.dumps(entry_points_geojson(graph)))
        .replace("__BURN_AREAS_GEOJSON__", json.dumps(burn_areas_geojson(burn_areas_path)))
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    render_map(build_graph())