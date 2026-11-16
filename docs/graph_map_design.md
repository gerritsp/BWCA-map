# Routing graph design

`APP.py` writes the browser layers, then builds the fixed route graph in two
stages. `Scripts/build_paddle_edges.js` creates only official portage and
reviewed river nodes and edges. `Scripts/repair_routing_graph.py` attaches exact
river junctions, creates a water-contained path for every pair of portage
landings on one lake polygon part, and adds the minimum extra lake paths needed
to attach remaining access nodes.

The lake router first accepts a straight path only when the full-resolution
polygon covers it. Island- or peninsula-blocked pairs use a constrained
Delaunay mesh made from a 15 m simplified copy. Simplification is an internal
speed optimization: the smoothed result must still be covered by the original
polygon (plus the 25 m landing tolerance). Separate polygon parts are never
joined automatically.

The generated `*_paddle_edges.json` contains:

- `nodes`: `[id, lake_guid_or_null, [longitude, latitude]]`;
- `edges`: `[left_id, right_id, distance_m, kind, geometry_or_null, crosses_burn]`;
- `topology_repair`: counts and tolerances from the deterministic repair; and
- `vertexGraphLakes`: normally empty for a fixed build.

Two-coordinate paddle geometry may be `null`; the browser reconstructs that
line from its endpoint nodes. This keeps the static payload smaller. The route
graph is fetched only after route mode is selected. A live lake click first
connects to visible fixed access points. Only when that leaves the click
isolated does the browser create a small, temporary shoreline mesh for that
lake.

The lake display layer is written as a small `*_lakes.json` manifest plus
bounded `*_lakes_N.json` GeoJSON shards. The browser loads those shards in
parallel and verifies the combined feature count before drawing them. This
keeps every repository object below common upload limits without changing the
map's lake geometry.

Search cost is estimated minutes, while the result also retains physical
distance. Paddle and river edges use 75 m/min, approaches 60 m/min and portages
50 m/min. Portages add five minutes and support one traversal for a single
carry or three traversals for a double carry. A burn preference triples the
cost of affected portage/approach edges; it does not remove the only available
route. A* divides its straight-line lower bound by the fastest configured speed,
so it remains admissible and returns the same optimum as Dijkstra.
