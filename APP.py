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

    const CONFIDENT_PORTAGE_STYLE = { color: "#0f5c2e", weight: 3, opacity: 0.9 };
    const UNCERTAIN_PORTAGE_STYLE = { color: "#dc2626", weight: 3, opacity: 0.9, dashArray: "8 6" };

    const portagesLayer = L.geoJSON(portages, {
        style: (feature) =>
            feature.properties.lake_match_uncertain ? UNCERTAIN_PORTAGE_STYLE : CONFIDENT_PORTAGE_STYLE,
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            const waterbody = p.waterbody || "(unnamed in source data)";
            const confidence = p.lake_match_uncertain
                ? '<span style="color:#dc2626;">Uncertain match</span>'
                : '<span style="color:#0f5c2e;">Confident match</span>';
            layer.bindPopup(
                `<b>Portage #${p.portage_number}</b> (USFS ID ${p.usfs_id})<br>` +
                `${waterbody} &mdash; ${p.length_rods.toFixed(1)} rods<br>` +
                `${p.lake_a} &rarr; ${p.lake_b}<br>` +
                `${confidence}<br>` +
                `<span style="font-size:11px; color:#555;">` +
                `fw_id_a=${p.fw_id_a} (${p.dist_lake_a.toFixed(1)}m) &middot; ` +
                `fw_id_b=${p.fw_id_b} (${p.dist_lake_b.toFixed(1)}m)</span>`
            );
        }
    }).addTo(map);

    const legend = L.control({ position: "bottomright" });
    legend.onAdd = function () {
        const div = L.DomUtil.create("div", "legend");
        div.innerHTML = `
            <b>Portage match confidence</b><br>
            <span style="display:inline-block;width:20px;border-top:3px solid #0f5c2e;margin-right:4px;"></span>Confident<br>
            <span style="display:inline-block;width:20px;border-top:3px dashed #dc2626;margin-right:4px;"></span>Uncertain (&gt;25m from lake)
        `;
        return div;
    };
    legend.addTo(map);

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

    map.fitBounds(lakesLayer.getBounds());

    // --- Route finding: portages (surveyed lines) + paddle edges across lakes ---
    // Paddle edges are a visibility-graph shortcut, not a full solve: for two
    // points on the same lake, if the straight line between them stays inside
    // the lake polygon, it's added as a paddle edge weighted by straight-line
    // distance. A chord blocked by an island (or crossing the gap between two
    // disjoint pieces of a lake split by the boundary clip - see CLAUDE.md's
    // CRS/clip gotcha) just gets no edge rather than routing around it - a
    // safe undercount, not a wrong route, and good enough for a demo.
    // NOTE: fw_id 88888 is a reused DNR placeholder shared by several
    // unrelated lakes (see CLAUDE.md) - the graph only keeps the last one
    // loaded, so routing near those lakes may be attached to the wrong polygon.
    const ROD_TO_METERS = 5.0292;

    const lakesById = new Map(lakes.features.map((f) => [f.properties.fw_id, f]));
    const nodes = new Map(); // nodeId -> { lakeId, coord: [lon, lat] }
    const adjacency = new Map(); // nodeId -> [{ to, weight, kind, geometry }]
    const accessPointsByLake = new Map(); // lakeId -> [nodeId, ...]

    function addEdge(a, b, weight, kind, geometry) {
        adjacency.get(a).push({ to: b, weight, kind, geometry });
        adjacency.get(b).push({ to: a, weight, kind, geometry });
    }

    // Portage endpoints are only guaranteed to be within ~25m of their matched
    // lake (portageCreator.py's own "confident match" threshold), not strictly
    // inside its polygon - buffer by that same tolerance before doing
    // containment/line-of-sight checks, or every off-polygon endpoint would be
    // stranded with zero paddle edges. Simplify first so the buffer (which
    // adds rounding vertices at every corner) stays cheap on large/complex
    // lake polygons, and cache both the buffered polygon AND its boundary-as-
    // a-line - line-of-sight gets called many times per lake once vertex
    // waypoints are involved, and re-deriving the boundary from scratch each
    // call (instead of caching it) is what made the first version of this
    // freeze the page on anything but the smallest lakes.
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

    // A straight chord between two shore points only works for convex lakes -
    // any point/peninsula between them blocks it even with open water all
    // around. This is a real visibility graph, not just the chord shortcut:
    // once a lake has 2+ access points, add its own (simplified) boundary
    // vertices as extra waypoint nodes, wired in the same line-of-sight way,
    // so Dijkstra can hop shore-to-shore around a peninsula instead of
    // requiring one unobstructed line. Built lazily per lake (only lakes that
    // end up with 2+ access points need it) and cached.
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
        const nodeA = `portage:${p.portage_number}:a`;
        const nodeB = `portage:${p.portage_number}:b`;
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
        div.innerHTML = `
            <b>Route finder</b><br>
            <span id="route-status-text">Click a point on a lake to start a route.</span><br>
            <button id="route-clear-btn" style="margin-top:6px;">Clear route</button>
        `;
        L.DomEvent.disableClickPropagation(div);
        return div;
    };
    routeControl.addTo(map);
    document.getElementById("route-clear-btn").addEventListener("click", clearRoute);

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
</script>
</body>
</html>
"""


def build_graph():
    graph = bwca_graph()

    graph.load_lakes("Data/processed/bwca_lakes.parquet")
    graph.load_campsites("Data/processed/bwca_campsites.parquet")
    graph.connect_campsites()

    graph.load_portages("Data/processed/processed_portages_interim.parquet")
    graph.connect_portages()

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
    portages = graph.portages
    gdf = gpd.GeoDataFrame(
        {
            "portage_number": [p.portage_number for p in portages],
            "usfs_id": [p.usfs_id for p in portages],
            "waterbody": [p.waterbody for p in portages],

            "lake_a": [
                p.Lake_a.name if p.Lake_a else None
                for p in portages
            ],

            "lake_b": [
                p.Lake_b.name if p.Lake_b else None
                for p in portages
            ],

            "fw_id_a": [
                p.Lake_a.fw_id if p.Lake_a else None
                for p in portages
            ],

            "fw_id_b": [
                p.Lake_b.fw_id if p.Lake_b else None
                for p in portages
            ],

            "length_rods": [p.length_rods for p in portages],

            "dist_lake_a": [p.dist_lake_a for p in portages],
            "dist_lake_b": [p.dist_lake_b for p in portages],

            "lake_match_uncertain": [
                bool(p.lake_match_uncertain)
                for p in portages
            ],
        },
        geometry=[p.geometry for p in portages],
        crs=SOURCE_CRS,
    )
    return json.loads(gdf.to_crs(4326).to_json())


def render_map(graph, out_path="maps/bwca_graph_map.html"):
    html = (
        HTML_TEMPLATE
        .replace("__LAKES_GEOJSON__", json.dumps(lakes_geojson(graph)))
        .replace("__CAMPSITES_GEOJSON__", json.dumps(campsites_geojson(graph)))
        .replace("__PORTAGES_GEOJSON__", json.dumps(portages_geojson(graph)))
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    render_map(build_graph())