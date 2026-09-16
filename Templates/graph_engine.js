// Shared routing-graph construction logic - see graph_map_design.md for the
// full build-time/runtime split. This version adds burn-area awareness:
// every edge (portage, paddle, river) gets a `crossesBurn` boolean computed
// via turf.booleanIntersects against the fires FeatureCollection. Like the
// rest of this file's expensive geometry work, crossesBurn is computed ONCE
// per edge and reused - for precomputed edges (portages/rivers/lake-vertex
// mesh) that means computed once at build time and shipped as a flag in the
// dump, not recomputed by every visitor's browser. Only click-time edges
// (start/end wiring, river-snap edges) compute it live, since those are new
// edges the precompute step couldn't have known about in advance - and that
// live cost is tiny (a handful of edges per click, not the whole graph).
//
// IDENTITY NOTE: lakes are keyed by `unique_guid`, not `fw_id` - see the
// rest of this file's history. fw_id collides across real lakes and is
// unsafe as a lookup key.
(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.GraphEngine = factory();
    }
})(typeof self !== "undefined" ? self : this, function () {

    const ROD_TO_METERS = 5.0292;
    const LAKE_MATCH_BUFFER_METERS = 25;
    const MAX_LAKE_VERTICES = 24;
    const SIMPLIFY_TOLERANCE_DEG = 0.00015;

    function createGraphEngine(turf, lakes, rivers, fires) {
        const lakesById = new Map(lakes.features.map((f) => [f.properties.unique_guid, f]));
        const nodes = new Map();
        const adjacency = new Map();
        const accessPointsByLake = new Map();

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

        const preparedLakeCache = new Map();
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

        // ---- Burn-area awareness ----
        const burnFeatures = fires && fires.features ? fires.features : [];

        function edgeCrossesBurn(geometry) {
            if (burnFeatures.length === 0) return false;
            let line;
            try {
                line = turf.feature(geometry);
            } catch {
                return false;
            }
            return burnFeatures.some((burn) => {
                try {
                    return turf.booleanIntersects(line, burn);
                } catch {
                    return false;
                }
            });
        }

        // precomputedCrossesBurn: pass the already-known value (from a
        // dumped/loaded precomputed graph) to skip recomputing it here -
        // that's the whole point of precomputing. Leave undefined/null for
        // a brand-new edge (click-time wiring, or the build-time script's
        // first-ever pass over the data) and it'll be computed fresh.
        function addEdge(a, b, weight, kind, geometry, precomputedCrossesBurn) {
            const crossesBurn = (precomputedCrossesBurn === undefined || precomputedCrossesBurn === null)
                ? edgeCrossesBurn(geometry)
                : precomputedCrossesBurn;
            adjacency.get(a).push({ to: b, weight, kind, geometry, crossesBurn });
            adjacency.get(b).push({ to: a, weight, kind, geometry, crossesBurn });
        }

        // ---- River-snap routing (click-time only) ----
        const riverSnapNodes = new Set();
        const riverSnapBySegment = new Map();
        const lakeBboxCache = new Map();

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
            lakesById, nodes, adjacency, accessPointsByLake, vertexGraphBuilt,
            simplifiedLake, preparedLake, lineStaysInLake, lakeBoundaryPoints,
            buildLakeVertexGraph, wirePaddleEdges, addNode, removeNode, addEdge,
            wireRiverSnapEdges, clearRiverSnapEdges, edgeCrossesBurn,
        };
    }

    // crossesBurn now travels with every dumped edge, so a fresh page load
    // never has to recompute a single turf.booleanIntersects call for the
    // fixed graph - only click-time edges do that live.
    function dumpPrecomputed(engine) {
        const nodes = [...engine.nodes.entries()].map(([id, n]) => [id, n.lakeId, n.coord]);
        const edges = [];
        for (const [a, edgeList] of engine.adjacency.entries()) {
            for (const edge of edgeList) {
                if (a < edge.to) {
                    edges.push([a, edge.to, edge.weight, edge.kind, edge.geometry, edge.crossesBurn]);
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
        for (const [a, b, weight, kind, geometry, crossesBurn] of data.edges) {
            // pass the stored crossesBurn through - addEdge skips recomputing
            // it when a value is already provided (see addEdge above).
            engine.addEdge(a, b, weight, kind, geometry, crossesBurn);
        }
        for (const lakeId of data.vertexGraphLakes) {
            engine.vertexGraphBuilt.add(lakeId);
        }
    }

    return { createGraphEngine, ROD_TO_METERS, dumpPrecomputed, loadPrecomputed };
});