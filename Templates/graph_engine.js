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
    const SHORE_TOLERANCE_METERS = 3;
    const MIN_STRETCH_METERS = 0.5;
    const MAX_LAKE_VERTICES = 24;
    const SIMPLIFY_TOLERANCE_DEG = 0.00015;
    const EARTH_RADIUS_METERS = 6371008.8;
    const HEURISTIC_EDGE_EPSILON_METERS = 0.001;

    function greatCircleMeters(coordA, coordB) {
        if (!Array.isArray(coordA) || !Array.isArray(coordB)) return Infinity;
        const toRadians = value => value * Math.PI / 180;
        const lonA = toRadians(coordA[0]), latA = toRadians(coordA[1]);
        const lonB = toRadians(coordB[0]), latB = toRadians(coordB[1]);
        const deltaLat = latB - latA, deltaLon = lonB - lonA;
        const a = Math.sin(deltaLat / 2) ** 2 +
            Math.cos(latA) * Math.cos(latB) * Math.sin(deltaLon / 2) ** 2;
        return EARTH_RADIUS_METERS * 2 * Math.asin(Math.min(1, Math.sqrt(a)));
    }

    function sphereVector(coord) {
        const lon = coord[0] * Math.PI / 180;
        const lat = coord[1] * Math.PI / 180;
        const cosLat = Math.cos(lat);
        return [cosLat * Math.cos(lon), cosLat * Math.sin(lon), Math.sin(lat)];
    }

    function chordLowerBoundMeters(vectorA, vectorB) {
        // A 3-D chord never exceeds its spherical arc, so this remains an
        // admissible lower bound without doing per-node spherical trigonometry.
        return EARTH_RADIUS_METERS * Math.hypot(
            vectorA[0] - vectorB[0],
            vectorA[1] - vectorB[1],
            vectorA[2] - vectorB[2]
        );
    }

    class MinPriorityQueue {
        constructor() {
            this.items = [];
            this.sequence = 0;
        }
        get length() { return this.items.length; }
        push(priority, cost, node) {
            const item = { priority, cost, node, sequence: this.sequence++ };
            this.items.push(item);
            let index = this.items.length - 1;
            while (index > 0) {
                const parent = Math.floor((index - 1) / 2);
                if (!this.less(item, this.items[parent])) break;
                this.items[index] = this.items[parent];
                index = parent;
            }
            this.items[index] = item;
        }
        pop() {
            if (!this.items.length) return null;
            const first = this.items[0];
            const last = this.items.pop();
            if (this.items.length) {
                let index = 0;
                while (true) {
                    const left = index * 2 + 1, right = left + 1;
                    if (left >= this.items.length) break;
                    let child = left;
                    if (right < this.items.length && this.less(this.items[right], this.items[left])) child = right;
                    if (!this.less(this.items[child], last)) break;
                    this.items[index] = this.items[child];
                    index = child;
                }
                this.items[index] = last;
            }
            return first;
        }
        less(a, b) {
            return a.priority < b.priority ||
                (a.priority === b.priority && a.sequence < b.sequence);
        }
    }

    function shortestPath(engine, startNode, endNode, options = {}) {
        const algorithm = options.algorithm || "dijkstra";
        if (!new Set(["dijkstra", "astar"]).has(algorithm)) {
            throw new Error(`Unknown routing algorithm: ${algorithm}`);
        }
        if (!engine.nodes.has(startNode) || !engine.nodes.has(endNode)) return null;

        const paddlePenalty = options.paddlePenalty ?? 1;
        const avoidBurnAreas = Boolean(options.avoidBurnAreas);
        const geographicFloor = Boolean(options.geographicFloor);
        const goalNode = engine.nodes.get(endNode);
        const goalVector = goalNode.vector || sphereVector(goalNode.coord);
        const heuristicScale = algorithm === "astar"
            ? (geographicFloor ? 1 : engine.heuristicScale()) : 0;
        const heuristic = nodeId => {
            if (!heuristicScale) return 0;
            const node = engine.nodes.get(nodeId);
            const vector = node.vector || sphereVector(node.coord);
            return chordLowerBoundMeters(vector, goalVector) * heuristicScale;
        };

        const cost = new Map([[startNode, 0]]);
        const trueDistance = new Map([[startNode, 0]]);
        const previous = new Map();
        const queue = new MinPriorityQueue();
        queue.push(heuristic(startNode), 0, startNode);
        let expanded = 0;

        while (queue.length) {
            const current = queue.pop();
            if (current.cost !== cost.get(current.node)) continue;
            expanded++;
            if (current.node === endNode) break;

            for (const edge of engine.adjacency.get(current.node) || []) {
                if (avoidBurnAreas && edge.crossesBurn) continue;
                const routeDistance = geographicFloor
                    ? Math.max(edge.weight, edge.directDistance || 0) : edge.weight;
                const edgeCost = routeDistance * (edge.kind === "paddle" ? paddlePenalty : 1);
                if (!Number.isFinite(edgeCost) || edgeCost < 0) continue;
                const alternate = current.cost + edgeCost;
                if (alternate < (cost.get(edge.to) ?? Infinity)) {
                    cost.set(edge.to, alternate);
                    trueDistance.set(edge.to, trueDistance.get(current.node) + routeDistance);
                    previous.set(edge.to, current.node);
                    queue.push(alternate + heuristic(edge.to), alternate, edge.to);
                }
            }
        }

        if (!cost.has(endNode)) return null;
        const path = [endNode];
        let current = endNode;
        while (current !== startNode) {
            current = previous.get(current);
            if (current === undefined) return null;
            path.push(current);
        }
        path.reverse();
        return {
            algorithm,
            cost: cost.get(endNode),
            distance: trueDistance.get(endNode),
            expanded,
            path,
        };
    }

    function createGraphEngine(turf, lakes, rivers, fires) {
        const lakesById = new Map(lakes.features.map((f) => [f.properties.unique_guid, f]));
        const nodes = new Map();
        const adjacency = new Map();
        const accessPointsByLake = new Map();
        let safeHeuristicScale = 1;

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
                    const inside = turf.buffer(simplified, SHORE_TOLERANCE_METERS / 1000, { units: "kilometers" });
                    preparedLakeCache.set(lakeId, { polygon, inside, rawBoundary: turf.polygonToLine(simplified) });
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
            const crossingsNearEnds = crossings.every((crossing) => {
                const pt = crossing.geometry.coordinates;
                const distA = turf.distance(pt, coordA, { units: "meters" });
                const distB = turf.distance(pt, coordB, { units: "meters" });
                return distA <= LAKE_MATCH_BUFFER_METERS || distB <= LAKE_MATCH_BUFFER_METERS;
            });
            if (!crossingsNearEnds) return false;

            // Shore-to-shore chords across a peninsula or island cross the outline
            // only at their own endpoints, so the check above passes them. Require
            // the middle of every stretch away from the endpoints to be in the lake.
            const total = turf.distance(coordA, coordB, { units: "meters" });
            const breaks = [
                0,
                ...crossings
                    .map((c) => turf.distance(coordA, c.geometry.coordinates, { units: "meters" }))
                    .sort((a, b) => a - b),
                total,
            ];
            for (let i = 0; i < breaks.length - 1; i++) {
                const start = breaks[i];
                const end = breaks[i + 1];
                if (end - start < MIN_STRETCH_METERS) continue;
                if (end <= LAKE_MATCH_BUFFER_METERS) continue;
                if (start >= total - LAKE_MATCH_BUFFER_METERS) continue;
                const mid = turf.along(line, (start + end) / 2, { units: "meters" });
                if (!turf.booleanPointInPolygon(mid, prepared.inside)) return false;
            }
            return true;
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
            nodes.set(nodeId, { lakeId, coord, vector: sphereVector(coord) });
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
        const burnBBoxes = burnFeatures.map((burn) => turf.bbox(burn));

        function edgeCrossesBurn(geometry) {
            if (burnFeatures.length === 0) return false;
            let line;
            try {
                line = turf.feature(geometry);
            } catch {
                return false;
            }
            const lineBbox = turf.bbox(line);
            return burnFeatures.some((burn, index) => {
                if (!bboxesOverlap(lineBbox, burnBBoxes[index])) return false;
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
            const nodeA = nodes.get(a), nodeB = nodes.get(b);
            if (nodeA && !nodeA.vector) nodeA.vector = sphereVector(nodeA.coord);
            if (nodeB && !nodeB.vector) nodeB.vector = sphereVector(nodeB.coord);
            // Unit-sphere chord distance is a true lower bound and metric. It
            // lets A* stay optimal even when a reported portage length is
            // shorter than the displacement between its mapped endpoints.
            const directDistance = nodeA && nodeB
                ? chordLowerBoundMeters(nodeA.vector, nodeB.vector) : Infinity;
            if (Number.isFinite(directDistance) && directDistance > HEURISTIC_EDGE_EPSILON_METERS) {
                const ratio = Number.isFinite(weight) && weight >= 0 ? weight / directDistance : 0;
                safeHeuristicScale = Math.min(safeHeuristicScale, ratio);
            }
            const edge = { weight, kind, geometry, crossesBurn, directDistance };
            adjacency.get(a).push({ to: b, ...edge });
            adjacency.get(b).push({ to: a, ...edge });
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
            heuristicScale: () => safeHeuristicScale,
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
            engine.nodes.set(id, { lakeId, coord, vector: sphereVector(coord) });
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

    return {
        createGraphEngine, ROD_TO_METERS, dumpPrecomputed, loadPrecomputed,
        shortestPath, greatCircleMeters,
    };
});
