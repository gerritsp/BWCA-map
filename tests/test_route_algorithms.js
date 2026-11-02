const assert = require('assert/strict');
const fs = require('fs');
const turf = require('@turf/turf');
const GraphEngine = require('../Templates/graph_engine.js');

const empty = {type: 'FeatureCollection', features: []};

function add(engine, id, coord) {
  engine.addNode(id, null, coord);
}

function connect(engine, a, b, kind = 'paddle', crossesBurn = false) {
  const coordA = engine.nodes.get(a).coord;
  const coordB = engine.nodes.get(b).coord;
  engine.addEdge(
    a, b, GraphEngine.greatCircleMeters(coordA, coordB), kind,
    turf.lineString([coordA, coordB]).geometry, crossesBurn
  );
}

function syntheticComparison() {
  const engine = GraphEngine.createGraphEngine(turf, empty, empty, empty);
  add(engine, 'start', [-91.50, 48.00]);
  add(engine, 'middle', [-91.49, 48.00]);
  add(engine, 'end', [-91.48, 48.00]);
  connect(engine, 'start', 'middle', 'paddle', true);
  connect(engine, 'middle', 'end');
  add(engine, 'detour', [-91.49, 48.005]);
  connect(engine, 'start', 'detour');
  connect(engine, 'detour', 'end');

  // These cheap branches are closer to the start than the destination cost,
  // so Dijkstra explores them. A* recognizes that they head away from the goal.
  for (let branch = 0; branch < 8; branch++) {
    let prior = 'start';
    for (let step = 1; step <= 8; step++) {
      const id = `branch:${branch}:${step}`;
      add(engine, id, [-91.50 - step * 0.001, 48.00 + branch * 0.0001]);
      connect(engine, prior, id);
      prior = id;
    }
  }

  const dijkstra = GraphEngine.shortestPath(engine, 'start', 'end',
    {algorithm: 'dijkstra', geographicFloor: true});
  const astar = GraphEngine.shortestPath(engine, 'start', 'end',
    {algorithm: 'astar', geographicFloor: true});
  assert.deepEqual(astar.path, ['start', 'middle', 'end']);
  assert.equal(astar.cost, dijkstra.cost);
  assert.equal(astar.distance, dijkstra.distance);
  assert(astar.expanded < dijkstra.expanded,
    `expected A* (${astar.expanded}) to expand fewer nodes than Dijkstra (${dijkstra.expanded})`);

  const avoidOptions = {avoidBurnAreas: true, geographicFloor: true};
  const dijkstraAvoid = GraphEngine.shortestPath(engine, 'start', 'end',
    {...avoidOptions, algorithm: 'dijkstra'});
  const astarAvoid = GraphEngine.shortestPath(engine, 'start', 'end',
    {...avoidOptions, algorithm: 'astar'});
  assert.deepEqual(dijkstraAvoid.path, ['start', 'detour', 'end']);
  assert.deepEqual(astarAvoid.path, dijkstraAvoid.path);
  assert.equal(astarAvoid.cost, dijkstraAvoid.cost);
  assert.throws(
    () => GraphEngine.shortestPath(engine, 'start', 'end', {algorithm: 'unknown'}),
    /Unknown routing algorithm/
  );
}

function largestComponent(adjacency) {
  const unseen = new Set(adjacency.keys());
  let largest = [];
  while (unseen.size) {
    const start = unseen.values().next().value;
    unseen.delete(start);
    const component = [start];
    for (let index = 0; index < component.length; index++) {
      for (const edge of adjacency.get(component[index]) || []) {
        if (unseen.delete(edge.to)) component.push(edge.to);
      }
    }
    if (component.length > largest.length) largest = component;
  }
  return largest;
}

function realGraphComparison() {
  const data = JSON.parse(fs.readFileSync('maps/bwca_graph_map_paddle_edges.json', 'utf8'));
  const engine = GraphEngine.createGraphEngine(turf, empty, empty, empty);
  GraphEngine.loadPrecomputed(engine, data);
  const component = largestComponent(engine.adjacency);
  assert(component.length > 1000, 'expected a substantial connected routing component');

  const start = component[0];
  const startCoord = engine.nodes.get(start).coord;
  const end = component.reduce((farthest, node) =>
    GraphEngine.greatCircleMeters(startCoord, engine.nodes.get(node).coord) >
      GraphEngine.greatCircleMeters(startCoord, engine.nodes.get(farthest).coord)
      ? node : farthest, start);

  const dijkstra = GraphEngine.shortestPath(engine, start, end,
    {algorithm: 'dijkstra', geographicFloor: true});
  const astar = GraphEngine.shortestPath(engine, start, end,
    {algorithm: 'astar', geographicFloor: true});
  assert(dijkstra && astar, 'both algorithms should find the route');
  assert(Math.abs(astar.cost - dijkstra.cost) < 1e-6, 'A* and Dijkstra cost mismatch');
  assert(Math.abs(astar.distance - dijkstra.distance) < 1e-6, 'A* and Dijkstra distance mismatch');
  assert(astar.expanded <= dijkstra.expanded,
    `A* expanded ${astar.expanded}, Dijkstra expanded ${dijkstra.expanded}`);
  console.log(
    `Route algorithms agree at ${(astar.distance / 1000).toFixed(2)} km; ` +
    `A* expanded ${astar.expanded.toLocaleString()} nodes vs ` +
    `${dijkstra.expanded.toLocaleString()} for Dijkstra`
  );
}

syntheticComparison();
realGraphComparison();
