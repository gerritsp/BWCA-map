"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const destinationRoot = path.join(root, "maps", "vendor");

const files = [
  ["node_modules/leaflet/dist/leaflet.css", "leaflet/leaflet.css"],
  ["node_modules/leaflet/dist/leaflet.js", "leaflet/leaflet.js"],
  ["node_modules/leaflet/LICENSE", "leaflet/LICENSE"],
  ["node_modules/leaflet.markercluster/dist/MarkerCluster.css", "leaflet.markercluster/MarkerCluster.css"],
  ["node_modules/leaflet.markercluster/dist/MarkerCluster.Default.css", "leaflet.markercluster/MarkerCluster.Default.css"],
  ["node_modules/leaflet.markercluster/dist/leaflet.markercluster.js", "leaflet.markercluster/leaflet.markercluster.js"],
  ["node_modules/leaflet.markercluster/MIT-LICENCE.txt", "leaflet.markercluster/MIT-LICENCE.txt"],
  ["node_modules/@turf/turf/turf.min.js", "turf/turf.min.js"],
  ["node_modules/@turf/turf/LICENSE", "turf/LICENSE"],
];

for (const [sourceRelative, destinationRelative] of files) {
  const source = path.join(root, sourceRelative);
  const destination = path.join(destinationRoot, destinationRelative);
  if (!fs.existsSync(source)) {
    throw new Error(`Missing vendor source: ${sourceRelative}. Run npm ci first.`);
  }
  fs.mkdirSync(path.dirname(destination), {recursive: true});
  fs.copyFileSync(source, destination);
  fs.chmodSync(destination, 0o644);
}

const leafletImages = path.join(root, "node_modules", "leaflet", "dist", "images");
const destinationImages = path.join(destinationRoot, "leaflet", "images");
fs.mkdirSync(destinationImages, {recursive: true});
for (const file of fs.readdirSync(leafletImages)) {
  const destination = path.join(destinationImages, file);
  fs.copyFileSync(path.join(leafletImages, file), destination);
  fs.chmodSync(destination, 0o644);
}

console.log(`Synced ${files.length} vendor files and Leaflet images to maps/vendor.`);
