const assert = require("node:assert/strict");
const fs = require("node:fs");
const turf = require("@turf/turf");
const Graph = require("../Templates/graph_engine");

const read = name => JSON.parse(fs.readFileSync(`maps/bwca_graph_map_${name}.json`, "utf8"));
const empty = {type: "FeatureCollection", features: []};
const engine = Graph.createGraphEngine(turf, empty, empty, empty);
const graph = read("paddle_edges");
Graph.loadPrecomputed(engine, graph);
const options = {algorithm: "astar", geographicFloor: true};
// Find a nearby destination reached by traveling on actual mapped water.
function routeToWater(start, allowEstimatedApproaches = false) {
    const queue = [start];
    const seen = new Set(queue);
    for (let i = 0; i < queue.length; i++) {
        for (const edge of engine.adjacency.get(queue[i]) || []) {
            if (!allowEstimatedApproaches && edge.kind === "approach" &&
                (queue[i].includes(":estimate") || edge.to.includes(":estimate"))) continue;
            if ((edge.kind === "paddle" || edge.kind === "river") && edge.weight > 1 && edge.to !== start) {
                const route = Graph.shortestPath(engine, start, edge.to, {...options, allowEstimatedApproaches});
                if (route && route.edges.some(e => ["paddle", "river"].includes(e.kind) && e.weight > 1)) return route;
            }
            if (!seen.has(edge.to)) {
                queue.push(edge.to);
                seen.add(edge.to);
            }
        }
    }
    return null;
}

const estimated = new Set();
const portages = read("portages").features;
assert.equal(portages.length, 905);
for (const feature of portages) {
    const number = feature.properties.portage_number;
    const coords = feature.geometry.coordinates;
    for (const [i, side] of [[0, "a"], [coords.length - 1, "b"]]) {
        const landing = `portage:${number}:${side}`;
        const opposite = `portage:${number}:${side === "a" ? "b" : "a"}`;
        assert(engine.attachPortageLanding("click", feature, coords[i]), `missing ${landing}`);
        assert.equal(engine.adjacency.get("click")[0].to, landing, `click on ${landing}`);
        assert(Graph.shortestPath(engine, "click", opposite, options), `carry ${landing}`);
        if (!routeToWater("click")) {
            estimated.add(number);
            assert.equal(feature.properties.routing_status, "review");
            assert(routeToWater("click", true), `no onward route from ${landing}`);
        }
        engine.removeNode("click");
    }

}

const entries = read("entry_points").features;
assert.equal(entries.length, 71);
for (const feature of entries) {
    const p = feature.properties;
    assert.notEqual(p.routing_status, "review", feature.id);
    const preferred = p.attachments.filter(a => a.confidence !== "review");
    const choices = preferred.length ? preferred : p.attachments;
    engine.addNode("entry-click", null, feature.geometry.coordinates);
    for (const a of choices) {
        assert(engine.nodes.has(a.node_id), `missing attachment for ${feature.id}`);
        engine.addEdge("entry-click", a.node_id, a.connector_distance_m, a.edge_kind || "approach",
            a.connector_geometry || turf.lineString([feature.geometry.coordinates, a.route_coordinates]).geometry);
    }
    assert(routeToWater("entry-click"), `entry ${feature.id} has no onward route`);
    engine.removeNode("entry-click");
}
assert.deepEqual([...estimated].sort((a, b) => a - b), [123, 385, 676, 814, 819, 887, 888]);
console.log(`Both landings of ${portages.length} portages route onward. ${estimated.size} require estimated approaches. All ${entries.length} entries route onward with default settings.`);
