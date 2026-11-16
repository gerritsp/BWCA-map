// Precomputes the fixed portage/river base graph and land-edge burn flags.
// Python adds exact in-lake paths afterward; see docs/graph_map_design.md.
//
// Usage: node Scripts/build_paddle_edges.js <stem>
// Reads   <stem>_lakes.json, <stem>_portages.json, <stem>_rivers.json,
//         <stem>_fires.json
// Writes  <stem>_paddle_edges.json
const fs = require("fs");
const turf = require("@turf/turf");
const GraphEngine = require("../Templates/graph_engine.js");

function readJSON(path) {
    return JSON.parse(fs.readFileSync(path, "utf8"));
}

function readJSONIfExists(path) {
    if (!fs.existsSync(path)) return { type: "FeatureCollection", features: [] };
    return readJSON(path);
}

function main() {
    const stem = process.argv[2];
    if (!stem) {
        console.error("usage: node Scripts/build_paddle_edges.js <stem>");
        process.exit(1);
    }
    const lakes = readJSON(`${stem}_lakes.json`);
    const portages = readJSON(`${stem}_portages.json`);
    const rivers = readJSON(`${stem}_rivers.json`);
    // Fires is optional - if graph_map.py hasn't started writing
    // <stem>_fires.json yet, this falls back to an empty FeatureCollection
    // so build_paddle_edges.js doesn't hard-fail on older data. Every edge
    // just gets crossesBurn=false, which is exactly what you'd want with no
    // fire data at all - "not crossing a burn" (rather than "unknown"), since
    // the checkbox in the UI never has anything to filter without real fire
    // polygons anyway.
    const fires = readJSONIfExists(`${stem}_fires.json`);

    // Fixed builds contain only official portage/river nodes and edges here.
    // repair_routing_graph.py adds exact in-water landing paths afterward;
    // the small shoreline mesh is reserved for an otherwise-isolated live
    // click in the browser.
    const engine = GraphEngine.createGraphEngine(
        turf, lakes, rivers, fires, {buildMode: true}
    );
    const { addNode, addEdge } = engine;
    const ROD_TO_METERS = GraphEngine.ROD_TO_METERS;

    for (const feature of portages.features) {
        const p = feature.properties;
        const coords = feature.geometry.coordinates;
        const nodeA = `portage:${p.portage_number}:a`;
        const nodeB = `portage:${p.portage_number}:b`;
        const lakeA = Object.prototype.hasOwnProperty.call(p, "routing_lake_guid_a")
            ? p.routing_lake_guid_a : p.unique_guid_a;
        const lakeB = Object.prototype.hasOwnProperty.call(p, "routing_lake_guid_b")
            ? p.routing_lake_guid_b : p.unique_guid_b;
        addNode(nodeA, lakeA, coords[0]);
        addNode(nodeB, lakeB, coords[coords.length - 1]);
        const routeLength = Number.isFinite(p.routing_length_m)
            ? p.routing_length_m : p.length_rods * ROD_TO_METERS;
        addEdge(nodeA, nodeB, routeLength, "portage", feature.geometry);
    }

    for (const feature of rivers.features) {
        const p = feature.properties;
        if (!p.routable) continue;
        const coords = feature.geometry.coordinates;
        addNode(p.node_a, p.unique_guid_a, coords[0]);
        addNode(p.node_b, p.unique_guid_b, coords[coords.length - 1]);
        addEdge(p.node_a, p.node_b, p.length_m, "river", feature.geometry);
    }

    const out = GraphEngine.dumpPrecomputed(engine);
    fs.writeFileSync(`${stem}_paddle_edges.json`, JSON.stringify(out));

    const burnCount = out.edges.filter((e) => e[5]).length;
    console.log(
        `Wrote ${stem}_paddle_edges.json: ${out.nodes.length} nodes, ` +
        `${out.edges.length} edges (${burnCount} crossing a burn area), ` +
        `${out.vertexGraphLakes.length} lakes with a vertex graph`
    );
}
main();
