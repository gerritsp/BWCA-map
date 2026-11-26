const assert = require("node:assert/strict");
const fs = require("node:fs");
const turf = require("@turf/turf");
const Graph = require("../maps/bwca_graph_map_engine");

const read = file => JSON.parse(fs.readFileSync("maps/" + file, "utf8"));
const layer = name => read("bwca_graph_map_" + name + ".json");
const lakes = turf.featureCollection(layer("lakes").shards.flatMap(file => read(file).features));
const rivers = layer("rivers"), fires = layer("fires"), graph = layer("paddle_edges");

function run(startName, start, endName, end) {
    const engine = Graph.createGraphEngine(turf, lakes, rivers, fires);
    Graph.loadPrecomputed(engine, graph);
    for (const [role, name, coord] of [["start", startName, start], ["end", endName, end]]) {
        const lake = lakes.features.find(f => turf.booleanPointInPolygon(coord, f));
        assert.equal(lake?.properties.name, name);
        const guid = lake.properties.unique_guid;
        engine.addNode(role, guid, coord);
        engine.ensurePaddleAttachment(role);
        engine.wireRiverSnapEdges(role, guid, coord);
    }
    const result = Graph.shortestPath(engine, "start", "end", {algorithm: "astar", geographicFloor: true});
    assert(result, `No route from ${startName} to ${endName}`);
    assert(result.distance >= Graph.greatCircleMeters(start, end) * 0.99);
    return result;
}

// Fixed clicks from the historical branch comparison.
const brule = [-90.67151950634272, 47.93807917064623];
for (const [name, start] of [
    ["Bruin", [-91.64714135003135, 47.85982150132512]],
    ["Little Gabbro", [-91.62084470464718, 47.85711052038519]],
    ["One", [-91.48227439470273, 47.926962364735815]],
    ["Knife", [-91.19628386271998, 48.09452063273196]],
]) {
    const result = run(name, start, "Brule", brule);
    console.log(`${name} to Brule: ${(result.distance / 1000).toFixed(2)} km`);
}

// Repeat the five lake-click trials, checking the actual carry in each path.
for (const [start, end] of [
    [[-91.2983954722894,47.89047985087021],[-91.26800434477366,47.970075544787335]],
    [[-91.26753409481651,47.92995472217871],[-91.2594406785352,47.9638193979312]],
    [[-91.26696700066731,47.92468845755678],[-91.26264136204234,47.9713816645831]],
    [[-91.2872444505965,47.93043141334497],[-91.26218949938597,47.964017885540535]],
    [[-91.2835723025042,47.93880946515083],[-91.2629327526487,47.96480886235794]],
]) {
    const result = run("Insula", start, "Kiana", end);
    assert(result.path.some((id, i) => id === "portage:570:b" && result.path[i + 1] === "portage:570:a"));
}
console.log("Five Insula–Kiana click pairs crossed portage 570.");
