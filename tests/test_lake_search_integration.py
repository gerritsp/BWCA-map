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


class SearchIntegrationTests(unittest.TestCase):
    def test_every_search_bundle(self):
        rows = json.loads((ROOT / 'maps/lake_search_index.json').read_text())
        index = json.loads((ROOT / 'maps/fisheries/_index.json').read_text())
        self.assertEqual({r['g'] for r in rows}, set(index))
        self.assertEqual(len(rows), len(index))
        for row in rows:
            with self.subTest(guid=row['g']):
                self.assertEqual(unquote(quote(row['g'], safe='')), row['g'])
                self.assertIsInstance(row['g'], str)
                self.assertIsInstance(row['dowlknum'], str)
                self.assertRegex(row['dowlknum'], r'^\d{8}$')
                bundle = json.loads((ROOT / 'maps/fisheries' / (row['g'] + '.json')).read_text())
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
            assets = ['lake_search.html', 'lake_search_index.json', 'lake_access_index.json'] + ['bwca_graph_map' + suffix for suffix in ('.html', '.js', '_engine.js', '_lakes.json', '_campsites.json', '_portages.json', '_rivers.json', '_entry_points.json', '_boundary.json', '_fires.json', '_paddle_edges.json')]
            for asset in assets:
                with urlopen(base + asset) as response:
                    self.assertEqual(response.status, 200)
                    response.read()
            rows = json.loads((ROOT / 'maps/lake_search_index.json').read_text())
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
        rows = json.loads((ROOT / 'maps/lake_search_index.json').read_text())
        for row in rows:
            with self.subTest(lake=row['n'], guid=row['g']):
                self.assertEqual(row['cs'], int(counts.get(row['g'], 0)))

    def test_access_index_contract(self):
        access = json.loads((ROOT / 'maps/lake_access_index.json').read_text())
        lakes = json.loads((ROOT / 'maps/bwca_graph_map_lakes.json').read_text())
        lake_guids = {feature['properties']['unique_guid']
                      for feature in lakes['features']}
        self.assertEqual(access['schema_version'], 1)
        self.assertGreater(len(access['entries']), 0)
        self.assertEqual(len(access['entries']),
                         len({entry['code'] for entry in access['entries']}))
        for entry in access['entries']:
            self.assertIn(entry['lake_guid'], lake_guids)
            self.assertIn(entry['lake_guid'], access['starts'])
            self.assertEqual(access['starts'][entry['lake_guid']][entry['lake_guid']],
                             [[0.0, 0, 0]])
        for routes in access['starts'].values():
            for destination, states in routes.items():
                self.assertIn(destination, lake_guids)
                self.assertGreater(len(states), 0)
                for rods, portages, lakes_in in states:
                    self.assertGreaterEqual(rods, 0)
                    self.assertGreaterEqual(portages, 0)
                    self.assertGreaterEqual(lakes_in, 0)

    def test_boundary_asset_contract(self):
        boundary = json.loads((ROOT / 'maps/bwca_graph_map_boundary.json').read_text())
        self.assertEqual(boundary['type'], 'FeatureCollection')
        self.assertEqual({feature['properties']['unit']
                          for feature in boundary['features']},
                         {'Central', 'Eastern', 'Southwest'})
        self.assertTrue(all(feature['geometry']['type'] in {'Polygon', 'MultiPolygon'}
                            for feature in boundary['features']))

    def test_popup_runtime(self):
        subprocess.run(['node', 'tests/test_lake_popup.js'], cwd=ROOT, check=True)

    def test_map_bundle_contract(self):
        source = (ROOT / 'Templates/js_template.js').read_text()
        self.assertIn('bundle.unique_guid !== unique_guid', source)
        self.assertIn('lakeBundlePromises.delete(unique_guid)', source)
        self.assertIn('encodeURIComponent(unique_guid)', source)
        self.assertIn('openLakeData(layer, guid)', source)
        self.assertIn('L.control.layers(', source)
        self.assertIn('USGSTopo/MapServer/tile/{z}/{y}/{x}', source)
        self.assertIn('map.setMaxBounds(padded)', source)
        self.assertIn('lakeDetailsEnabled.checked', source)
        self.assertIn('bundle.unique_guid !== requestedGuid', (ROOT / 'maps/lake_search.html').read_text())


if __name__ == '__main__':
    unittest.main()
