// Precomputes the routing graph's fixed paddle-edge mesh (portage endpoints,
// routable river endpoints, and lake boundary vertices) at build time instead
// of the browser doing it on every page load. Run after graph_map.py has
// written maps/<stem>_lakes.json / _portages.json / _rivers.json.
//
// This intentionally reuses templates/graph_engine.js unmodified - the exact
// same addNode/wirePaddleEdges/buildLakeVertexGraph code that runs client-side
// for click-time start/end wiring - so the precomputed edge set matches what
// the browser would have computed itself, by construction rather than by
// separately-maintained logic that could drift. See docs/graph_map_design.md's
// "Paddle-edge precomputation" section.
//
// IDENTITY NOTE: lakes are addressed by unique_guid here, matching
// graph_engine.js's IDENTITY NOTE. fw_id is NOT safe to use as a lake key -
// it collides across multiple real lakes (fw_id=88888 alone is shared by 6
// unrelated lakes) and is null for most lake rows. graph_map.py's
// portages_geojson()/rivers_geojson() must emit unique_guid_a/unique_guid_b
// alongside the legacy fw_id_a/fw_id_b (kept for debug display only) for
// this to wire up correctly.
//
// Usage: node scripts/build_paddle_edges.js <stem>
//   e.g. node scripts/build_paddle_edges.js maps/bwca_graph_map
// Reads   <stem>_lakes.json, <stem>_portages.json, <stem>_rivers.json
// Writes  <stem>_paddle_edges.json
const fs = require("fs");
const turf = require("@turf/turf");
const GraphEngine = require("../templates/graph_engine.js");
function readJSON(path) {
    return JSON.parse(fs.readFileSync(path, "utf8"));
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
    const engine = GraphEngine.createGraphEngine(turf, lakes);
    const { addNode, addEdge } = engine;
    const ROD_TO_METERS = GraphEngine.ROD_TO_METERS;
    // Mirrors the portage-ingestion loop in templates/js_template.js exactly -
    // same node ID scheme, same edge weight/kind, same call order.
    // CHANGED: p.fw_id_a/p.fw_id_b -> p.unique_guid_a/p.unique_guid_b (see
    // IDENTITY NOTE above). Using fw_id here silently produced a graph with
    // the same wrong-lake attachments this whole precomputation step exists
    // to make fast, not correct - speed doesn't help if the underlying edges
    // are wired to the wrong lake.
    for (const feature of portages.features) {
        const p = feature.properties;
        const coords = feature.geometry.coordinates;
        const nodeA = `portage:${p.portage_number}:a`;
        const nodeB = `portage:${p.portage_number}:b`;
        addNode(nodeA, p.unique_guid_a, coords[0]);
        addNode(nodeB, p.unique_guid_b, coords[coords.length - 1]);
        addEdge(nodeA, nodeB, p.length_rods * ROD_TO_METERS, "portage", feature.geometry);
    }
    // Mirrors the river-ingestion loop in templates/js_template.js exactly.
    // Same unique_guid_a/unique_guid_b change as above.
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
    console.log(
        `Wrote ${stem}_paddle_edges.json: ${out.nodes.length} nodes, ` +
        `${out.edges.length} edges, ${out.vertexGraphLakes.length} lakes with a vertex graph`
    );
}
main();