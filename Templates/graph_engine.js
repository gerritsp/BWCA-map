// Shared routing-graph construction logic, used two ways:
//   - in the browser (templates/js_template.js), loaded via a <script> tag,
//     for click-time start/end node wiring
//   - in Node (scripts/build_paddle_edges.js), via require(), to precompute
//     the fixed portage/river/lake-vertex paddle-edge graph at build time
//     instead of paying for it in every visitor's browser on every page load
//
// This file must stay the single source of truth for this logic. The two
// call sites need to compute byte-identical results (same Turf version, same
// code) or routes that exist under one and not the other reappear - see the
// reverted-optimization history in docs/graph_map_design.md for why that's
// not a hypothetical risk here.
//
// IDENTITY NOTE: lakes are keyed by `unique_guid`, not `fw_id`. fw_id is a
// DNR field that is NOT unique per lake row - confirmed against the real
// dataset: 4,515 lake rows collapse to only 1,304 unique fw_id values, a
// placeholder value (88888) is shared by 6 unrelated lakes (Saganaga, East
// Vermilion, Bearskin, Jenny x2, Gull), and most of the rest are null. Keying
// this graph's lakesById map by fw_id meant it silently kept only the
// last-loaded lake for any collided/null id, which measurably broke routing:
// 186/868 portages (21%) failed to resolve at least one endpoint, and 174
// (20%) resolved both endpoints to the same wrong lake. unique_guid is a
// true 1:1 key generated for every lake row and carried through every join
// (campsites, portages, rivers) - see CLAUDE.md and the ETL scripts for how
// it's produced and propagated.
(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.GraphEngine = factory();
    }
})(typeof self !== "undefined" ? self : this, function () {

    const ROD_TO_METERS = 5.0292;

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

    function createGraphEngine(turf, lakes, rivers) {
        // KEYED BY unique_guid - see the IDENTITY NOTE at the top of this file.
        const lakesById = new Map(lakes.features.map((f) => [f.properties.unique_guid, f]));
        const nodes = new Map(); // nodeId -> { lakeId, coord: [lon, lat] }  (lakeId is a unique_guid)
        const adjacency = new Map(); // nodeId -> [{ to, weight, kind, geometry }]
        const accessPointsByLake = new Map(); // lakeId (unique_guid) -> [nodeId, ...]

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

        // NOTE: the buffered `polygon` below is deliberately only used for the
        // containment checks (is this endpoint close enough to count as "on"
        // this lake), not for the obstruction check. Buffering the whole
        // polygon-with-holes by 25m grows the water area on *every* boundary -
        // exterior shoreline AND interior island rings alike - which erodes
        // any land feature narrower than ~2x the buffer (peninsulas, necks
        // between lobes, small islands) right out of the geometry. Confirmed
        // against real data (Newfound Lake, now identified by its
        // unique_guid rather than its collision-prone fw_id of 335): a chord
        // that crosses the true shoreline 7 times crossed the buffered
        // boundary 0 times, because the buffer had erased the narrow neck it
        // was cutting across. `rawBoundary` (unbuffered, simplified) is kept
        // separately for that check instead - see lineStaysInLake.
        const preparedLakeCache = new Map(); // lakeId -> { polygon, rawBoundary } | null
        function preparedLake(lakeId) {
            if (!preparedLakeCache.has(lakeId)) {
                const simplified = simplifiedLake(lakeId);
                if (!simplified) {
                    preparedLakeCache.set(lakeId, null);
                } else {
                    const polygon = turf.buffer(simplified, LAKE_MATCH_BUFFER_METERS / 1000, { units: "kilometers" });
                    preparedLakeCache.set(lakeId, { polygon, rawBoundary: turf.polygonToLine(simplified) });
                }
            }
            return preparedLakeCache.get(lakeId);
        }

        // A chord's endpoints are only guaranteed to be within
        // LAKE_MATCH_BUFFER_METERS of the true shoreline (that's the whole
        // reason `polygon` above is buffered for containment), so testing
        // against the *true* boundary would spuriously flag a crossing right
        // next to a near-shore endpoint that isn't actually on the polygon.
        // Test against the true boundary, but disregard any crossing that
        // falls within that same tolerance of either endpoint - that's
        // expected endpoint noise, not a real obstruction. A crossing
        // farther from both endpoints than the tolerance is real land in the
        // middle of the chord and blocks it.
        function lineStaysInLake(coordA, coordB, lakeId) {
            const prepared = preparedLake(lakeId);
            if (!prepared) return false;
            if (!turf.booleanPointInPolygon(coordA, prepared.polygon)) return false;
            if (!turf.booleanPointInPolygon(coordB, prepared.polygon)) return false;
            const line = turf.lineString([coordA, coordB]);
            const crossings = turf.lineIntersect(line, prepared.rawBoundary).features;
            return crossings.every((crossing) => {
                const pt = crossing.geometry.coordinates;
                const distA = turf.distance(pt, coordA, { units: "meters" });
                const distB = turf.distance(pt, coordB, { units: "meters" });
                return distA <= LAKE_MATCH_BUFFER_METERS || distB <= LAKE_MATCH_BUFFER_METERS;
            });
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

        function addEdge(a, b, weight, kind, geometry) {
            adjacency.get(a).push({ to: b, weight, kind, geometry });
            adjacency.get(b).push({ to: a, weight, kind, geometry });
        }

        // River-snap routing (click-time only): lets a click-time "start"/
        // "end" node join a routable river/connector polyline at its nearest
        // point, not just wherever the polyline's own two endpoints happen to
        // land. Purely additive to the graph - new nodes/edges only.
        const riverSnapNodes = new Set();
        const riverSnapBySegment = new Map(); // riverIdx -> [{snapNodeId, location, coord}], sorted by location
        const lakeBboxCache = new Map(); // lakeId -> [minX, minY, maxX, maxY] | null

        const routableRivers = rivers ? rivers.features.filter((f) => f.properties.routable) : [];
        const riverBBoxes = routableRivers.map((f) => turf.bbox(f));

        function bboxesOverlap(a, b) {
            return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
        }

        function lakeBbox(lakeId) {
            if (!lakeBboxCache.has(lakeId)) {
                const prepared = preparedLake(lakeId);
                lakeBboxCache.set(lakeId, prepared ? turf.bbox(prepared.polygon) : null);
            }
            return lakeBboxCache.get(lakeId);
        }

        function wireRiverSnapEdges(nodeId, lakeId, coord) {
            if (!lakesById.get(lakeId) || routableRivers.length === 0) return;
            const prepared = preparedLake(lakeId);
            if (!prepared) return;
            const bbox = lakeBbox(lakeId);
            if (!bbox) return;

            for (let riverIdx = 0; riverIdx < routableRivers.length; riverIdx++) {
                if (!bboxesOverlap(bbox, riverBBoxes[riverIdx])) continue;
                const feature = routableRivers[riverIdx];
                if (!turf.booleanIntersects(feature, prepared.polygon)) continue;

                const nearest = turf.nearestPointOnLine(feature, coord, { units: "meters" });
                const snapCoord = nearest.geometry.coordinates;
                if (!lineStaysInLake(coord, snapCoord, lakeId)) continue;

                const snapNodeId = `river-snap:${riverIdx}:${nodeId}`;
                nodes.set(snapNodeId, { lakeId, coord: snapCoord });
                adjacency.set(snapNodeId, []);
                riverSnapNodes.add(snapNodeId);

                const reachDist = turf.distance(coord, snapCoord, { units: "meters" });
                addEdge(nodeId, snapNodeId, reachDist, "paddle", turf.lineString([coord, snapCoord]).geometry);

                // Seed the segment's own node_a/node_b as permanent anchor
                // points (location 0 and full length) the first time any
                // click touches this segment. node_a/node_b are the
                // pre-snapped junction node IDs computed in riverCreator.py -
                // NOT lake IDs, so they don't need a unique_guid swap; they're
                // already collision-free by construction (coordinate-snapped
                // strings). Only the LAKE a segment endpoint might resolve to
                // (unid_a/unid_b in the source data, wired in at build time -
                // see scripts/build_paddle_edges.js) needed the guid fix.
                if (!riverSnapBySegment.has(riverIdx)) {
                    const anchors = [];
                    const nodeAId = feature.properties.node_a;
                    const nodeBId = feature.properties.node_b;
                    const nodeAInfo = nodeAId != null ? nodes.get(nodeAId) : null;
                    const nodeBInfo = nodeBId != null ? nodes.get(nodeBId) : null;
                    if (nodeAInfo) anchors.push({ snapNodeId: nodeAId, location: 0, coord: nodeAInfo.coord });
                    if (nodeBInfo) {
                        const fullLength = turf.length(feature, { units: "meters" });
                        anchors.push({ snapNodeId: nodeBId, location: fullLength, coord: nodeBInfo.coord });
                    }
                    riverSnapBySegment.set(riverIdx, anchors);
                }
                const points = riverSnapBySegment.get(riverIdx);
                points.push({ snapNodeId, location: nearest.properties.location, coord: snapCoord });
                points.sort((a, b) => a.location - b.location);

                for (let i = 0; i < points.length - 1; i++) {
                    const a = points[i];
                    const b = points[i + 1];
                    const sliceLine = turf.lineSlice(a.coord, b.coord, feature);
                    const sliceDist = turf.length(sliceLine, { units: "meters" });
                    addEdge(a.snapNodeId, b.snapNodeId, sliceDist, "river", sliceLine.geometry);
                }
            }
        }

        function clearRiverSnapEdges() {
            for (const snapNodeId of riverSnapNodes) {
                removeNode(snapNodeId);
            }
            riverSnapNodes.clear();
            riverSnapBySegment.clear();
        }

        return {
            lakesById,
            nodes,
            adjacency,
            accessPointsByLake,
            vertexGraphBuilt,
            simplifiedLake,
            preparedLake,
            lineStaysInLake,
            lakeBoundaryPoints,
            buildLakeVertexGraph,
            wirePaddleEdges,
            addNode,
            removeNode,
            addEdge,
            wireRiverSnapEdges,
            clearRiverSnapEdges,
        };
    }

    function dumpPrecomputed(engine) {
        const nodes = [...engine.nodes.entries()].map(([id, n]) => [id, n.lakeId, n.coord]);

        const edges = [];
        for (const [a, edgeList] of engine.adjacency.entries()) {
            for (const edge of edgeList) {
                if (a < edge.to) {
                    edges.push([a, edge.to, edge.weight, edge.kind, edge.geometry]);
                }
            }
        }

        return { nodes, edges, vertexGraphLakes: [...engine.vertexGraphBuilt] };
    }

    function loadPrecomputed(engine, data) {
        for (const [id, lakeId, coord] of data.nodes) {
            engine.nodes.set(id, { lakeId, coord });
            engine.adjacency.set(id, []);
            if (!engine.accessPointsByLake.has(lakeId)) engine.accessPointsByLake.set(lakeId, []);
            engine.accessPointsByLake.get(lakeId).push(id);
        }
        for (const [a, b, weight, kind, geometry] of data.edges) {
            engine.addEdge(a, b, weight, kind, geometry);
        }
        for (const lakeId of data.vertexGraphLakes) {
            engine.vertexGraphBuilt.add(lakeId);
        }
    }

    return { createGraphEngine, ROD_TO_METERS, dumpPrecomputed, loadPrecomputed };
});