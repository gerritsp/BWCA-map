import ast
import json
from pathlib import Path
import re
import subprocess
import threading
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import urlopen
import unittest
from urllib.parse import quote, unquote
from Scripts.build_search_index import search_row
from Scripts.validate_lake_bundles import validate

ROOT = Path(__file__).resolve().parents[1]


def load_access_index():
    manifest = json.loads((ROOT / 'maps/lake_access_index.json').read_text(encoding='utf-8'))
    starts = {}
    for shard in manifest.get('shards', []):
        starts.update(json.loads((ROOT / 'maps' / shard).read_text(encoding='utf-8'))['starts'])
    if manifest.get('shards'):
        manifest['starts'] = starts
    return manifest


class SearchIntegrationTests(unittest.TestCase):
    def test_every_search_bundle(self):
        rows = json.loads((ROOT / 'maps/lake_search_index.json').read_text(encoding='utf-8'))
        index = json.loads((ROOT / 'maps/fisheries/_index.json').read_text(encoding='utf-8'))
        self.assertEqual({r['g'] for r in rows}, set(index))
        self.assertEqual(len(rows), len(index))
        for row in rows:
            with self.subTest(guid=row['g']):
                self.assertEqual(unquote(quote(row['g'], safe='')), row['g'])
                self.assertIsInstance(row['g'], str)
                self.assertIsInstance(row['dowlknum'], str)
                self.assertRegex(row['dowlknum'], r'^\d{8}$')
                bundle = json.loads((ROOT / 'maps/fisheries' / (row['g'] + '.json')).read_text(
                    encoding='utf-8'))
                self.assertEqual(bundle['unique_guid'], row['g'])
                self.assertEqual(bundle['dowlknum'], row['dowlknum'])
                # Campsites come from the project parquet, not the fisheries bundle.
                self.assertEqual({k: v for k, v in search_row(bundle).items() if k != "cs"},
                                 {k: v for k, v in row.items() if k != "cs"})

    def test_full_validation(self):
        self.assertGreater(validate(), 0)

    def test_http_assets_and_all_encoded_bundles(self):
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT / 'maps')))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}/'
        try:
            access = load_access_index()
            assets = ['lake_search.html', 'lake_search_index.json', 'lake_access_index.json', 'fisheries/species.json', *access.get('shards', [])] + ['bwca_graph_map' + suffix for suffix in ('.html', '.js', '_engine.js', '_lakes.json', '_campsites.json', '_portages.json', '_rivers.json', '_entry_points.json', '_boundary.json', '_fires.json', '_paddle_edges.json')]
            for asset in assets:
                with urlopen(base + asset) as response:
                    self.assertEqual(response.status, 200)
                    response.read()
            rows = json.loads((ROOT / 'maps/lake_search_index.json').read_text(encoding='utf-8'))
            for row in rows:
                with urlopen(base + 'fisheries/' + quote(row['g'], safe='') + '.json') as response:
                    self.assertEqual(response.status, 200)
                    bundle = json.load(response)
                    self.assertEqual(bundle['unique_guid'], row['g'])
                    self.assertEqual(bundle['dowlknum'], row['dowlknum'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_search_campsites_match_source(self):
        import pandas as pd
        camps = pd.read_parquet(ROOT / 'Data/processed/bwca_campsites_river.parquet')
        counts = camps.loc[camps['STATUS'].eq('open'), 'lake_unique_guid'].value_counts()
        rows = json.loads((ROOT / 'maps/lake_search_index.json').read_text(encoding='utf-8'))
        for row in rows:
            with self.subTest(lake=row['n'], guid=row['g']):
                self.assertEqual(row['cs'], int(counts.get(row['g'], 0)))

    def test_every_search_species_has_an_official_name(self):
        rows = json.loads((ROOT / 'maps/lake_search_index.json').read_text(encoding='utf-8'))
        species = json.loads((ROOT / 'maps/fisheries/species.json').read_text(encoding='utf-8'))
        search_codes = {code for row in rows for code in row.get('sp', {})}
        self.assertLessEqual(search_codes, set(species))
        for code in search_codes:
            self.assertTrue(species[code]['common_name'])

    def test_access_index_contract(self):
        access = load_access_index()
        lakes = json.loads((ROOT / 'maps/bwca_graph_map_lakes.json').read_text(encoding='utf-8'))
        lake_guids = {feature['properties']['unique_guid']
                      for feature in lakes['features']}
        entry_points = json.loads((ROOT / 'maps/bwca_graph_map_entry_points.json').read_text(
            encoding='utf-8'))
        entry_codes = {feature['properties']['code'] for feature in entry_points['features']
                       if feature['properties']['routing_status'] == 'connected'}
        self.assertEqual(access['schema_version'], 3)
        self.assertEqual(len(access['entries']), 69)
        self.assertEqual(len(access['entries']),
                         len({entry['code'] for entry in access['entries']}))
        self.assertEqual({entry['code'] for entry in access['entries']}, entry_codes)
        for entry in access['entries']:
            self.assertIn(entry['code'], access['starts'])
            self.assertGreater(len(access['starts'][entry['code']]), 0)
        for routes in access['starts'].values():
            for destination, states in routes.items():
                self.assertIn(destination, lake_guids)
                self.assertGreater(len(states), 0)
                for rods, portages, lakes_in in states:
                    self.assertGreaterEqual(rods, 0)
                    self.assertGreaterEqual(portages, 0)
                    self.assertGreaterEqual(lakes_in, 0)

        crab = next(feature for feature in entry_points['features']
                    if feature['properties']['code'] == '4')
        crab_guid = crab['properties']['attachments'][0]['lake_guid']
        crab_states = access['starts']['4'][crab_guid]
        self.assertTrue(any(348 <= rods <= 349 and portages == 1 and lakes_in == 0
                            for rods, portages, lakes_in in crab_states))

    def test_official_entry_points_are_connected_without_moving_markers(self):
        source = json.loads((ROOT / 'Data/entry_points/usfs_bwca_entry_points_2026.geojson').read_text(
            encoding='utf-8'))
        entries = json.loads((ROOT / 'maps/bwca_graph_map_entry_points.json').read_text(
            encoding='utf-8'))
        lakes = json.loads((ROOT / 'maps/bwca_graph_map_lakes.json').read_text(encoding='utf-8'))
        paddle = json.loads((ROOT / 'maps/bwca_graph_map_paddle_edges.json').read_text(
            encoding='utf-8'))
        portages = json.loads((ROOT / 'maps/bwca_graph_map_portages.json').read_text(
            encoding='utf-8'))
        lake_guids = {feature['properties']['unique_guid'] for feature in lakes['features']}
        node_ids = {node[0] for node in paddle['nodes']}
        portage_node_ids = {
            f"portage:{feature['properties']['portage_number']}:{side}"
            for feature in portages['features'] for side in ('a', 'b')
        }

        self.assertEqual(len(source['features']), 87)
        self.assertEqual(len(entries['features']), 71)
        counts = {}
        for feature in entries['features']:
            p = feature['properties']
            counts[p['code']] = counts.get(p['code'], 0) + 1
            self.assertIn(p['routing_status'], {'connected', 'review'})
            self.assertGreater(len(p['attachments']), 0)
            for attachment in p['attachments']:
                self.assertIn(attachment['routing_type'], {'lake', 'river'})
                if attachment['routing_type'] == 'lake':
                    self.assertIn(attachment['lake_guid'], lake_guids)
                else:
                    self.assertIsNotNone(attachment['routing_river_id'])
                self.assertIn(attachment['confidence'], {'high', 'medium', 'review'})
                if attachment['node_id']:
                    self.assertIn(attachment['node_id'], node_ids | portage_node_ids)
        self.assertEqual({code for code, count in counts.items() if count > 1}, {'47', '49'})
        self.assertEqual(
            {feature['properties']['code'] for feature in entries['features']
             if feature['properties']['routing_status'] == 'review'},
            set(),
        )
        self.assertNotIn('54A', counts)
        self.assertNotIn('55A', counts)
        self.assertNotIn('86', counts)  # hiking-only entry; canoe graph intentionally excludes it

        crab = next(feature for feature in entries['features']
                    if feature['properties']['code'] == '4')
        self.assertAlmostEqual(crab['geometry']['coordinates'][0], -92.033187318921, places=10)
        self.assertAlmostEqual(crab['geometry']['coordinates'][1], 47.931414809367, places=10)
        self.assertEqual(crab['properties']['routing_method'], 'portage')
        self.assertGreater(crab['properties']['attachments'][0]['initial_rods'], 300)

        snowbank = next(feature for feature in entries['features']
                        if feature['properties']['code'] == '27')
        self.assertAlmostEqual(snowbank['geometry']['coordinates'][0], -91.432158476718, places=10)
        self.assertEqual(snowbank['properties']['attachments'][0]['lake_name'], 'Snowbank')
        self.assertEqual(snowbank['properties']['attachments'][0]['confidence'], 'review')
        self.assertGreater(snowbank['properties']['attachments'][0]['connector_distance_m'], 1500)

        little_isabella = next(feature for feature in entries['features']
                               if feature['properties']['code'] == '75')
        self.assertEqual(little_isabella['properties']['routing_status'], 'connected')
        self.assertGreater(little_isabella['properties']['attachments'][0]['initial_rods'], 15)
        self.assertLess(little_isabella['properties']['attachments'][0]['initial_rods'], 25)

        snake = next(feature for feature in entries['features']
                     if feature['properties']['code'] == '84')
        self.assertEqual(snake['properties']['routing_method'], 'portage')
        self.assertEqual(snake['properties']['routing_status'], 'connected')
        self.assertGreater(snake['properties']['attachments'][0]['initial_rods'], 160)
        self.assertLess(snake['properties']['attachments'][0]['initial_rods'], 180)

        self.assertEqual(len(portages['features']), 905)
        self.assertEqual(len({feature['properties']['portage_number']
                              for feature in portages['features']}), 905)

    def test_boundary_asset_contract(self):
        boundary = json.loads((ROOT / 'maps/bwca_graph_map_boundary.json').read_text(
            encoding='utf-8'))
        self.assertEqual(boundary['type'], 'FeatureCollection')
        self.assertEqual({feature['properties']['unit']
                          for feature in boundary['features']},
                         {'Central', 'Eastern', 'Southwest'})
        self.assertTrue(all(feature['geometry']['type'] in {'Polygon', 'MultiPolygon'}
                            for feature in boundary['features']))

    def test_popup_runtime(self):
        subprocess.run(['node', 'tests/test_lake_popup.js'], cwd=ROOT, check=True)

    def test_map_bundle_contract(self):
        build_sources = [ROOT / 'APP.py', *(ROOT / 'Scripts').glob('*.py')]
        implicit_text_io = []
        for path in build_sources:
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for call in ast.walk(tree):
                if (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr in {'read_text', 'write_text'}
                        and not any(keyword.arg == 'encoding' for keyword in call.keywords)):
                    implicit_text_io.append(f'{path.relative_to(ROOT)}:{call.lineno}')
        self.assertEqual(implicit_text_io, [],
                         'Build text I/O must explicitly use UTF-8')

        source = (ROOT / 'Templates/js_template.js').read_text(encoding='utf-8')
        self.assertIn('bundle.unique_guid !== unique_guid', source)
        self.assertIn('lakeBundlePromises.delete(unique_guid)', source)
        self.assertIn('encodeURIComponent(unique_guid)', source)
        self.assertIn('openLakeData(layer, guid)', source)
        self.assertIn('L.control.layers(', source)
        self.assertIn('USGSTopo/MapServer/tile/{z}/{y}/{x}', source)
        self.assertIn('map.setMaxBounds(padded)', source)
        self.assertIn('map.setMinZoom(map.getZoom())', source)
        self.assertNotIn('boundaryVisuals', source)
        self.assertIn('lakeDetailsEnabled.checked', source)
        self.assertIn('feature.properties.attachments || []', source)
        self.assertIn('entryAnchorNodes', source)
        self.assertIn('approximate approach', source)
        self.assertIn('if (!nodes.has(nodeA)) addNode', source)
        search_source = (ROOT / 'maps/lake_search.html').read_text(encoding='utf-8')
        self.assertIn('bundle.unique_guid !== requestedGuid', search_source)
        self.assertIn('maxcs=num("maxcs")', search_source)
        self.assertIn('fetch("fisheries/species.json")', search_source)
        self.assertIn('const DESC_FIRST=new Set', search_source)
        self.assertIn('aria-sort=', search_source)
        self.assertIn('Math.max(...lengths)', search_source)
        self.assertIn('access.starts?.[entry.code]', search_source)
        self.assertIn('async function loadAccessIndex()', search_source)


if __name__ == '__main__':
    unittest.main()
