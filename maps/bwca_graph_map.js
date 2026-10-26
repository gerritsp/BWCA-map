const LAKE_BUNDLES_URL = "fisheries/";
const lakeBundlePromises = new Map();
function escapeHTML(value) {
    return String(value ?? "N/A").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function fetchLakeBundle(unique_guid) {
    if (!lakeBundlePromises.has(unique_guid)) {
        const promise = fetch(`${LAKE_BUNDLES_URL}${encodeURIComponent(unique_guid)}.json`)
            .then(response => {
                if (response.status === 404) { lakeBundlePromises.delete(unique_guid); return null; }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.json();
            }).then(bundle => {
                if (bundle && bundle.unique_guid !== unique_guid) throw new Error("Lake bundle GUID mismatch");
                return bundle;
            }).catch(error => { lakeBundlePromises.delete(unique_guid); throw error; });
        lakeBundlePromises.set(unique_guid, promise);
    }
    return lakeBundlePromises.get(unique_guid);
}
function lakeBundleHTML(bundle) {
    if (!bundle) return "No lake data is available for this polygon.";
    const info = bundle.lake_info || {};
    const lengths = bundle.fish_lengths;
    const catches = bundle.fish_catches;
    const species = [...new Set([...lengths, ...catches].map(row => row.species))].sort();
    const clarity = [...bundle.clarity].sort((a,b) => String(b.date ?? "").localeCompare(String(a.date ?? "")))[0];
    const fish = species.map(code => {
        const sampled = lengths.filter(row => row.species === code).map(row => row.length_inches);
        const cpue = catches.filter(row => row.species === code && typeof row.cpue === "number");
        return `<li>${escapeHTML(code)}: max sampled ${escapeHTML(sampled.length ? Math.max(...sampled) : null)} in; CPUE ${cpue.map(row => `${escapeHTML(row.cpue)} (${escapeHTML(row.gear)}, ${escapeHTML(row.date)})`).join("; ") || "N/A"}</li>`;
    }).join("");
    const latestClarity = clarity ? Object.entries(clarity).map(([k,v]) => `${escapeHTML(k)}: ${escapeHTML(v)}`).join(", ") : "N/A";
    return `<div><h2>${escapeHTML(bundle.name)}</h2>
      DOW: ${escapeHTML(bundle.dowlknum)}<br>Area: ${escapeHTML(info.areaAcres ?? bundle.project.area_acres)} acres<br>
      Maximum depth: ${escapeHTML(info.maxDepthFeet)} ft<br>Latest clarity: ${latestClarity}<br>
      Detailed surveys: ${escapeHTML(bundle.surveys.length)}; inventory surveys: ${escapeHTML(bundle.survey_inventory.length)}<br>
      MPCA assessments: ${escapeHTML(bundle.assessments.length)}${bundle.incomplete ? " (source collection incomplete)" : ""}<br>
      <details><summary>Fish observations</summary><ul>${fish || "<li>No fish observations available.</li>"}</ul></details>
      <a href="${escapeHTML(LAKE_BUNDLES_URL + encodeURIComponent(bundle.unique_guid) + ".json")}" target="_blank" rel="noopener">Complete normalized JSON bundle</a></div>`;
}
const LAKES_URL = "bwca_graph_map_lakes.json";
    const CAMPSITES_URL = "bwca_graph_map_campsites.json";
    const PORTAGES_URL = "bwca_graph_map_portages.json";
    const RIVERS_URL = "bwca_graph_map_rivers.json";
    const ENTRY_POINTS_URL = "bwca_graph_map_entry_points.json";
    const BOUNDARY_URL = "bwca_graph_map_boundary.json";
    const FIRES_URL = "bwca_graph_map_fires.json";
    const PADDLE_EDGES_URL = "bwca_graph_map_paddle_edges.json";

    function init(lakes, campsites, portages, rivers, entryPoints, boundary, fires, paddleEdges) {
    const map = L.map("map", { maxBoundsViscosity: 1.0 });
    const streetMap = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
    const topoMap = L.tileLayer("https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}", {
        maxNativeZoom: 16,
        maxZoom: 19,
        attribution: "Tiles courtesy of the U.S. Geological Survey"
    });

    const boundaryOutline = L.geoJSON(boundary, {
        interactive: false,
        style: { color: "#6aa6bf", weight: 1.5, opacity: 0.8, fillOpacity: 0 }
    });
    const boundaryBounds = boundaryOutline.getBounds();
    if (boundaryBounds.isValid()) {
        const padded = boundaryBounds.pad(0.14);
        map.setMaxBounds(padded);
        map.fitBounds(boundaryBounds);
        // maxBounds keeps the center nearby; minZoom prevents zooming out far
        // enough to see the whole planet around it.
        map.setMinZoom(map.getZoom());
    }

    let mode = "explore", selectedLayer = null, selectionRequest = 0;
    const content = document.getElementById("lake-content");
    const closeDetails = document.getElementById("close-details");
    const lakeDetailsEnabled = document.getElementById("lake-details-enabled");
    function showInfo(html) { content.innerHTML = html; closeDetails.hidden = false; }
    function resetSelection() {
        selectionRequest++;
        if (selectedLayer) lakesLayer.resetStyle(selectedLayer);
        selectedLayer = null;
        content.innerHTML = "<p>Select a lake to explore its details.</p>";
        closeDetails.hidden = true;
    }
    closeDetails.addEventListener("click", resetSelection);
    lakeDetailsEnabled.addEventListener("change", () => {
        if (!lakeDetailsEnabled.checked) resetSelection();
    });
    function bindFeatureInfo(layer, html) {
        layer.on("click", () => { if (mode === "explore") { resetSelection(); showInfo(html); } });
    }
    const lakeLayersByGuid = new Map();
    async function openLakeData(layer, guid) {
        resetSelection();
        selectedLayer = layer;
        layer.setStyle({color: "#d48a29", weight: 3, fillOpacity: 0.3});
        const request = selectionRequest;
        const name = escapeHTML(layer.feature.properties.name || "Unnamed lake");
        showInfo(`<h2>${name}</h2><p>Loading lake details…</p>`);
        try {
            const bundle = await fetchLakeBundle(guid);
            if (request === selectionRequest) showInfo(lakeBundleHTML(bundle));
        } catch (error) {
            if (request === selectionRequest) showInfo(`<h2>${name}</h2><p>Could not load lake data. Select this lake again to retry.</p>`);
        }
    }
    const lakesLayer = L.geoJSON(lakes, {
        style: {
            color: "#4c8e99",
            weight: 1,
            fillColor: "#8bc3c8",
            fillOpacity: 0.28
        },
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            lakeLayersByGuid.set(p.unique_guid, layer);
            layer.bindTooltip(escapeHTML(p.name || "Unnamed lake"), {sticky: true});
            layer.on("click", () => {
                if (mode === "explore" && lakeDetailsEnabled.checked) {
                    openLakeData(layer, p.unique_guid);
                }
            });
        }
    }).addTo(map);


    const PORTAGE_STYLE = { color: "#0f5c2e", weight: 3, opacity: 0.9 };

    const portagesLayer = L.geoJSON(portages, {
        style: (feature) =>
            (feature.properties.start_snapped || feature.properties.end_snapped)
                ? { color: "#7c3aed", weight: 3, opacity: 0.9, dashArray: "4 2" }
                : PORTAGE_STYLE,
        onEachFeature: function (feature, layer) {
            const p = feature.properties;
            const label = p.name || "(unnamed)";
            const rods = p.length_rods == null ? "N/A" : `${p.length_rods.toFixed(1)} rods`;
            const snappedNote = (p.start_snapped || p.end_snapped)
                ? '<span style="color:#7c3aed;font-size:11px;">Endpoint adjusted &mdash; not surveyed</span><br>'
                : "";
            bindFeatureInfo(layer,
                `<b>Portage #${p.portage_number}</b> (USFS ID ${p.usfs_id})<br>` +
                `${label} &mdash; ${rods}<br>` +
                `${p.lake_a} &rarr; ${p.lake_b}<br>` +
                snappedNote +
                `<span style="font-size:11px; color:#555;">` +
                `unique_guid_a=${p.unique_guid_a ?? "N/A"} &middot; ` +
                `unique_guid_b=${p.unique_guid_b ?? "N/A"}</span>`
            );
        }
    }).addTo(map);

    // ADDED: burn area rendering
    const FIRE_STYLE = { color: "#9a3412", weight: 1.5, fillColor: "#ea580c", fillOpacity: 0.28, dashArray: "4 3" };
    const firesLayer = L.geoJSON(fires, {
        style: FIRE_STYLE,
        interactive: false,
        onEachFeature: function (feature, layer) {
            const p = feature.properties || {};
            const label = p.incident_name || p.name || "Burn area";
            const year = p.last_updated ? new Date(p.last_updated).getFullYear() : null;
            layer.bindTooltip(year ? `${label} (${year})` : label);
        }
    }).addTo(map);

    const legend = L.control({ position: "bottomright" });
    legend.onAdd = function () {
        const div = L.DomUtil.create("div", "legend");
        div.innerHTML = `
            <details><summary>Map legend</summary><b>Portages</b><br>
            <span style="display:inline-block;width:20px;border-top:3px solid #0f5c2e;margin-right:4px;"></span>Portage (surveyed)<br>
            <span style="display:inline-block;width:20px;border-top:3px dashed #7c3aed;margin-right:4px;"></span>Portage (endpoint adjusted)<br>
            <b>Rivers &amp; streams</b><br>
            <span style="display:inline-block;width:20px;border-top:2px solid #0891b2;margin-right:4px;"></span>Routable (river/connector)<br>
            <span style="display:inline-block;width:20px;border-top:2px dotted #0891b2;margin-right:4px;"></span>Display only (small stream)<br>
            <span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#f59e0b;border:2px solid white;box-shadow:0 0 2px rgba(0,0,0,0.5);margin-right:4px;vertical-align:middle;"></span>Entry point<br>
            <span style="display:inline-block;width:14px;height:10px;background:#ea580c;opacity:0.5;border:1px dashed #9a3412;margin-right:4px;vertical-align:middle;"></span>Burn area</details>
        `;
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
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
            bindFeatureInfo(layer,
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
            bindFeatureInfo(layer,
                `<b>Entry Point ${p.code ?? ""}</b><br>` +
                `${p.name || "(unnamed)"}<br>` +
                `<span style="font-size:11px; color:#555;">Lake: ${p.lake_name || "unmatched"}</span>`
            );
        }
    }).addTo(map);

    // Add the non-interactive outline last so the soft boundary stays legible.
    boundaryOutline.addTo(map);

    L.control.layers(
        { "Street map": streetMap, "Topographic": topoMap },
        {
            "Lakes": lakesLayer,
            "Campsites": campsitesLayer,
            "Portages": portagesLayer,
            "Rivers & streams": riversLayer,
            "Entry points": entryPointsLayer,
            "Burn areas": firesLayer,
            "BWCA boundary": boundaryOutline,
        },
        { collapsed: true }
    ).addTo(map);

    if (!boundaryBounds.isValid()) map.fitBounds(lakesLayer.getBounds());
    function zoomToLakeFromHash() {
  try {
        const guid = new URLSearchParams(location.hash.slice(1)).get("lake");
        if (!guid) return;
        const layer = lakeLayersByGuid.get(guid);
        if (!layer) return;
        map.fitBounds(layer.getBounds(), { maxZoom: 14 });
        if (lakeDetailsEnabled.checked) openLakeData(layer, guid);
      } catch (err) { console.error("lake hash zoom failed", err); }
    }
    zoomToLakeFromHash();
    window.addEventListener("hashchange", zoomToLakeFromHash);

    // ADDED: fires passed as the 4th arg so every edge in the precomputed
    // dump (and any live click-time edge) carries a real crossesBurn flag.
    const engine = GraphEngine.createGraphEngine(turf, lakes, rivers, fires);
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

    // ADDED: burn-area avoidance state - the checkbox below sets this
    let avoidBurnAreas = false;

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
                if (avoidBurnAreas && edge.crossesBurn) continue; // ADDED - this is the line that makes the checkbox do anything
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
                interactive: false,
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

    function makeRouteControls() {
        const div = L.DomUtil.create("div", "legend");
        div.style.minWidth = "220px";
        div.innerHTML = `
            <b>Route finder</b><br>
            <span id="route-status-text">Click a point on a lake to start a route.</span>
            <div style="margin-top:8px; padding-top:8px; border-top:1px solid #e5e7eb;">
                <label style="display:flex; align-items:center; gap:6px; cursor:pointer; user-select:none;">
                    <input type="checkbox" id="avoid-burn-checkbox" style="accent-color:#ea580c; width:15px; height:15px;" />
                    <span>Avoid burn areas</span>
                </label>
            </div>
            <button id="route-clear-btn" style="margin-top:8px; width:100%; padding:5px 0; border:1px solid #d1d5db; border-radius:4px; background:#f9fafb; cursor:pointer;">Clear route</button>
        `;
        L.DomEvent.disableClickPropagation(div);
        return div;
    };
    document.getElementById("route-controls").appendChild(makeRouteControls());
    function setMode(next) {
        mode = next;
        if (mode === "route") resetSelection();
        document.getElementById("explore-mode").setAttribute("aria-pressed", String(mode === "explore"));
        document.getElementById("route-mode").setAttribute("aria-pressed", String(mode === "route"));
        document.getElementById("route-controls").hidden = mode !== "route";
        document.getElementById("mode-help").textContent = mode === "route" ? "Click your start, then your destination. Lake details stay closed while you plan." : "Click a lake to explore its details. Your map stays clear.";
    }
    document.getElementById("explore-mode").addEventListener("click", () => setMode("explore"));
    document.getElementById("route-mode").addEventListener("click", () => setMode("route"));
    document.getElementById("route-clear-btn").addEventListener("click", clearRoute);
    // ADDED: toggling the checkbox re-runs the search immediately if a route is already showing
    document.getElementById("avoid-burn-checkbox").addEventListener("change", (e) => {
        avoidBurnAreas = e.target.checked;
        if (nodes.has("start") && nodes.has("end")) computeAndDrawRoute();
    });

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

    const handledClicks = new WeakSet();
    function routeClick(e, entry = false) {
        if (mode !== "route") return;
        if (e.originalEvent) {
            if (handledClicks.has(e.originalEvent)) return;
            handledClicks.add(e.originalEvent);
        }
        if (entry) handleEntryPointClick(e.layer.feature, e.latlng);
        else handleRouteClick(e.latlng);
    }
    map.on("click", e => routeClick(e));
    portagesLayer.on("click", e => routeClick(e));
    campsitesLayer.on("click", e => routeClick(e));
    riversLayer.on("click", e => routeClick(e));
    entryPointsLayer.on("click", e => routeClick(e, true));
    }

    Promise.all([
        fetch(LAKES_URL).then((r) => r.json()),
        fetch(CAMPSITES_URL).then((r) => r.json()),
        fetch(PORTAGES_URL).then((r) => r.json()),
        fetch(RIVERS_URL).then((r) => r.json()),
        fetch(ENTRY_POINTS_URL).then((r) => r.json()),
        fetch(BOUNDARY_URL).then((r) => r.json()),
        fetch(FIRES_URL).then((r) => r.json()),
        fetch(PADDLE_EDGES_URL).then((r) => r.json()),
    ])
        .then(([lakes, campsites, portages, rivers, entryPoints, boundary, fires, paddleEdges]) =>
            init(lakes, campsites, portages, rivers, entryPoints, boundary, fires, paddleEdges))
        .catch((err) => {
            console.error("Failed to load map data:", err);
            document.getElementById("map").textContent = `Could not load the map: ${err.message}. Check that the server is running and rebuild with APP.py if needed.`;
        });
