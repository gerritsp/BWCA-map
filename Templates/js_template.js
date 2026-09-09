const LAKES_URL = "__LAKES_URL__";
    const CAMPSITES_URL = "__CAMPSITES_URL__";
    const PORTAGES_URL = "__PORTAGES_URL__";
    const RIVERS_URL = "__RIVERS_URL__";
    const ENTRY_POINTS_URL = "__ENTRY_POINTS_URL__";
    const PADDLE_EDGES_URL = "__PADDLE_EDGES_URL__";

    function init(lakes, campsites, portages, rivers, entryPoints, paddleEdges) {
    const map = L.map("map");
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);

    const lakesLayer = L.geoJSON(lakes, {
        style: {
            color: "#2b6cb0",
            weight: 1,
            fillColor: "#63b3ed",
            fillOpacity: 0.35
        },
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            layer.bindTooltip(
                `${p.name} &mdash; ${p.acres.toFixed(1)} acres, ${p.num_campsites} campsite(s)`
            );
        }
    }).addTo(map);

    const PORTAGE_STYLE = { color: "#0f5c2e", weight: 3, opacity: 0.9 };

    const portagesLayer = L.geoJSON(portages, {
        style: PORTAGE_STYLE,
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            const label = p.name || "(unnamed)";
            const rods = p.length_rods == null ? "N/A" : `${p.length_rods.toFixed(1)} rods`;
            layer.bindPopup(
                `<b>Portage #${p.portage_number}</b> (USFS ID ${p.usfs_id})<br>` +
                `${label} &mdash; ${rods}<br>` +
                `${p.lake_a} &rarr; ${p.lake_b}<br>` +
                `<span style="font-size:11px; color:#555;">` +
                `unique_guid_a=${p.unique_guid_a ?? "N/A"} &middot; ` +
                `unique_guid_b=${p.unique_guid_b ?? "N/A"}</span>`
            );
        }
    }).addTo(map);

    const legend = L.control({ position: "bottomright" });
    legend.onAdd = function () {
        const div = L.DomUtil.create("div", "legend");
        div.innerHTML = `
            <b>Portages</b><br>
            <span style="display:inline-block;width:20px;border-top:3px solid #0f5c2e;margin-right:4px;"></span>Portage<br>
            <b>Rivers &amp; streams</b><br>
            <span style="display:inline-block;width:20px;border-top:2px solid #0891b2;margin-right:4px;"></span>Routable (river/connector)<br>
            <span style="display:inline-block;width:20px;border-top:2px dotted #0891b2;margin-right:4px;"></span>Display only (small stream)<br>
            <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#f59e0b;border:2px solid white;box-shadow:0 0 2px rgba(0,0,0,0.5);margin-right:4px;vertical-align:middle;"></span>Entry point
        `;
        return div;
    };
    legend.addTo(map);

    const riversLayer = L.geoJSON(rivers, {
        style: (feature) => ({
            color: "#0891b2",
            weight: feature.properties.routable ? 2 : 1.5,
            opacity: feature.properties.routable ? 0.85 : 0.6,
            dashArray: feature.properties.routable ? null : "1 4"
        }),
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            layer.bindTooltip(`${p.name || "Unnamed stream"} &mdash; ${p.strm_type}`);
        }
    }).addTo(map);

    const campsitesLayer = L.markerClusterGroup();
    L.geoJSON(campsites, {
        pointToLayer: function (feature, latlng) {
            return L.circleMarker(latlng, {
                radius: 4,
                color: "#c53030",
                fillColor: "#c53030",
                fillOpacity: 1
            });
        },
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            const dist = p.distance_to_lake == null ? "N/A" : `${p.distance_to_lake.toFixed(1)} m`;
            layer.bindPopup(
                `<b>Campsite:</b> ${p.camp_id}<br>` +
                `<b>Lake:</b> ${p.lake_name}<br>` +
                `<b>Status:</b> ${p.status}<br>` +
                `<b>District:</b> ${p.district}<br>` +
                `<b>Distance to matched lake:</b> ${dist}`
            );
        }
    }).addTo(campsitesLayer);
    campsitesLayer.addTo(map);

    const entryPointsLayer = L.geoJSON(entryPoints, {
        pointToLayer: function (feature, latlng) {
            return L.marker(latlng, {
                icon: L.divIcon({
                    className: "entry-point-icon",
                    html: '<div style="background:#f59e0b;border:2px solid white;' +
                          'border-radius:50%;width:14px;height:14px;' +
                          'box-shadow:0 0 3px rgba(0,0,0,0.5);"></div>',
                    iconSize: [14, 14],
                    iconAnchor: [7, 7]
                })
            });
        },
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            layer.bindPopup(
                `<b>Entry Point ${p.code ?? ""}</b><br>` +
                `${p.name || "(unnamed)"}<br>` +
                `<span style="font-size:11px; color:#555;">Lake: ${p.lake_name || "unmatched"}</span>`
            );
        }
    }).addTo(map);

    map.fitBounds(lakesLayer.getBounds());

    const engine = GraphEngine.createGraphEngine(turf, lakes, rivers);
    const { nodes, adjacency, addNode, removeNode, addEdge, wireRiverSnapEdges, clearRiverSnapEdges } = engine;
    GraphEngine.loadPrecomputed(engine, paddleEdges);

    function findLakeAtPoint(coord) {
        for (const feature of lakes.features) {
            if (turf.booleanPointInPolygon(coord, feature)) return feature;
        }
        return null;
    }

    function nearestLake(coord) {
        let best = null;
        let bestDist = Infinity;
        let bestCoord = coord;
        for (const feature of lakes.features) {
            const boundary = turf.polygonToLine(feature);
            const nearest = turf.nearestPointOnLine(boundary, coord, { units: "meters" });
            if (nearest.properties.dist < bestDist) {
                bestDist = nearest.properties.dist;
                best = feature;
                bestCoord = nearest.geometry.coordinates;
            }
        }
        return { feature: best, coord: bestCoord, distance: bestDist };
    }

    const PADDLE_PREFERENCE_PENALTY = 1.3;

    function dijkstra(startNode, endNode) {
        const cost = new Map([[startNode, 0]]);
        const trueDist = new Map([[startNode, 0]]);
        const prev = new Map();
        const visited = new Set();
        const queue = [[0, startNode]];

        while (queue.length) {
            queue.sort((a, b) => a[0] - b[0]);
            const [c, u] = queue.shift();
            if (visited.has(u)) continue;
            visited.add(u);
            if (u === endNode) break;

            for (const edge of adjacency.get(u) || []) {
                const edgeCost = edge.kind === "paddle" ? edge.weight * PADDLE_PREFERENCE_PENALTY : edge.weight;
                const alt = c + edgeCost;
                if (alt < (cost.get(edge.to) ?? Infinity)) {
                    cost.set(edge.to, alt);
                    trueDist.set(edge.to, trueDist.get(u) + edge.weight);
                    prev.set(edge.to, u);
                    queue.push([alt, edge.to]);
                }
            }
        }

        if (!cost.has(endNode)) return null;

        const path = [endNode];
        let current = endNode;
        while (current !== startNode) {
            current = prev.get(current);
            path.push(current);
        }
        path.reverse();
        return { distance: trueDist.get(endNode), path };
    }

    let routeLayer = null;
    let markerStart = null;
    let markerEnd = null;

    function setStatus(text) {
        document.getElementById("route-status-text").textContent = text;
    }

    function clearRoute() {
        if (markerStart) map.removeLayer(markerStart);
        if (markerEnd) map.removeLayer(markerEnd);
        if (routeLayer) map.removeLayer(routeLayer);
        clearRiverSnapEdges();
        removeNode("start");
        removeNode("end");
        markerStart = null;
        markerEnd = null;
        routeLayer = null;
        setStatus("Click a point on a lake to start a route.");
    }

    function computeAndDrawRoute() {
        const result = dijkstra("start", "end");
        if (routeLayer) map.removeLayer(routeLayer);

        if (!result) {
            setStatus("No route found - these lakes aren't connected by any recorded portage or river.");
            return;
        }

        const segments = [];
        for (let i = 0; i < result.path.length - 1; i++) {
            segments.push(adjacency.get(result.path[i]).find((e) => e.to === result.path[i + 1]));
        }

        const ROUTE_COLORS = { portage: "#7c2d12", paddle: "#1d4ed8", river: "#0891b2" };

        routeLayer = L.geoJSON(
            segments.map((s) => ({ type: "Feature", properties: { kind: s.kind }, geometry: s.geometry })),
            {
                style: (feature) => ({
                    color: ROUTE_COLORS[feature.properties.kind],
                    weight: 5,
                    opacity: 0.9,
                    dashArray: feature.properties.kind === "portage" ? "2 6" : null
                })
            }
        ).addTo(map);

        const rods = segments
            .filter((s) => s.kind === "portage")
            .reduce((sum, s) => sum + s.weight / GraphEngine.ROD_TO_METERS, 0);
        const paddleKm = segments
            .filter((s) => s.kind === "paddle")
            .reduce((sum, s) => sum + s.weight, 0) / 1000;
        const riverKm = segments
            .filter((s) => s.kind === "river")
            .reduce((sum, s) => sum + s.weight, 0) / 1000;

        setStatus(
            `Route found: ${(result.distance / 1000).toFixed(2)} km total ` +
            `(${rods.toFixed(0)} rods of portaging, ${paddleKm.toFixed(2)} km paddling, ` +
            `${riverKm.toFixed(2)} km river).`
        );
    }

    const routeControl = L.control({ position: "topleft" });
    routeControl.onAdd = function () {
        const div = L.DomUtil.create("div", "legend");
        div.innerHTML = `
            <b>Route finder</b><br>
            <span id="route-status-text">Click a point on a lake to start a route.</span><br>
            <button id="route-clear-btn" style="margin-top:6px;">Clear route</button>
        `;
        L.DomEvent.disableClickPropagation(div);
        return div;
    };
    routeControl.addTo(map);
    document.getElementById("route-clear-btn").addEventListener("click", clearRoute);

    function handleRouteClick(latlng) {
        if (nodes.has("start") && nodes.has("end")) clearRoute();

        const clickCoord = [latlng.lng, latlng.lat];
        let lakeFeature = findLakeAtPoint(clickCoord);
        let snappedCoord = clickCoord;

        if (!lakeFeature) {
            const nearest = nearestLake(clickCoord);
            if (!nearest.feature || nearest.distance > 200) {
                setStatus("That's too far from any lake - click closer to the water.");
                return;
            }
            lakeFeature = nearest.feature;
            snappedCoord = nearest.coord;
        }

        const role = nodes.has("start") ? "end" : "start";
        addNode(role, lakeFeature.properties.unique_guid, snappedCoord);
        wireRiverSnapEdges(role, lakeFeature.properties.unique_guid, snappedCoord);
        const marker = L.marker([snappedCoord[1], snappedCoord[0]], {
            title: role === "start" ? "Start" : "End"
        }).addTo(map);

        if (role === "start") {
            markerStart = marker;
            setStatus("Click a second point to find a route.");
        } else {
            markerEnd = marker;
            computeAndDrawRoute();
        }
    }

    // Entry points get their own click handler: an entry point already knows
    // which lake it's matched to (unique_guid, resolved in the Python
    // pipeline), so it doesn't need findLakeAtPoint/nearestLake's geometric
    // guessing at all - that guessing is what was rejecting entry points
    // that sit slightly outside a lake polygon or right next to a stream.
    function handleEntryPointClick(feature, latlng) {
        const lakeGuid = feature.properties.unique_guid;
        if (!lakeGuid) {
            setStatus("This entry point isn't matched to a lake yet.");
            return;
        }
        if (nodes.has("start") && nodes.has("end")) clearRoute();

        const coord = [latlng.lng, latlng.lat];
        const role = nodes.has("start") ? "end" : "start";
        addNode(role, lakeGuid, coord);
        wireRiverSnapEdges(role, lakeGuid, coord);
        const marker = L.marker(latlng, { title: role === "start" ? "Start" : "End" }).addTo(map);

        if (role === "start") {
            markerStart = marker;
            setStatus("Click a second point to find a route.");
        } else {
            markerEnd = marker;
            computeAndDrawRoute();
        }
    }

    map.on("click", (e) => handleRouteClick(e.latlng));
    portagesLayer.on("click", (e) => handleRouteClick(e.latlng));
    campsitesLayer.on("click", (e) => handleRouteClick(e.latlng));
    riversLayer.on("click", (e) => handleRouteClick(e.latlng));
    entryPointsLayer.on("click", (e) => handleEntryPointClick(e.layer.feature, e.latlng));
    }

    Promise.all([
        fetch(LAKES_URL).then((r) => r.json()),
        fetch(CAMPSITES_URL).then((r) => r.json()),
        fetch(PORTAGES_URL).then((r) => r.json()),
        fetch(RIVERS_URL).then((r) => r.json()),
        fetch(ENTRY_POINTS_URL).then((r) => r.json()),
        fetch(PADDLE_EDGES_URL).then((r) => r.json()),
    ])
        .then(([lakes, campsites, portages, rivers, entryPoints, paddleEdges]) =>
            init(lakes, campsites, portages, rivers, entryPoints, paddleEdges))
        .catch((err) => {
            console.error("Failed to load map data:", err);
            document.getElementById("map").textContent = "Failed to load map data - see console for details.";
        });