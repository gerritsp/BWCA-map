// Precomputes the routing graph's fixed paddle-edge mesh, including burn-area
// intersection flags, at build time - see docs/graph_map_design.md and the
// "Burn-area awareness" note in templates/graph_engine.js.
//
// Usage: node scripts/build_paddle_edges.js <stem>
// Reads   <stem>_lakes.json, <stem>_portages.json, <stem>_rivers.json,
//         <stem>_fires.json
// Writes  <stem>_paddle_edges.json
const fs = require("fs");
const turf = require("@turf/turf");
const GraphEngine = require("../templates/graph_engine.js");

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
        console.error("usage: node scripts/build_paddle_edges.js <stem>");
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

    const engine = GraphEngine.createGraphEngine(turf, lakes, rivers, fires);
    const { addNode, addEdge } = engine;
    const ROD_TO_METERS = GraphEngine.ROD_TO_METERS;

    for (const feature of portages.features) {
        const p = feature.properties;
        const coords = feature.geometry.coordinates;
        const nodeA = `portage:${p.portage_number}:a`;
        const nodeB = `portage:${p.portage_number}:b`;
        addNode(nodeA, p.unique_guid_a, coords[0]);
        addNode(nodeB, p.unique_guid_b, coords[coords.length - 1]);
        addEdge(nodeA, nodeB, p.length_rods * ROD_TO_METERS, "portage", feature.geometry);
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