import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from models.lake_ids import normalize_dow
from Scripts.sync_lake_bundles import clean, clean_url, lake_details, SourceCache, stable


class IdentifierTests(unittest.TestCase):
    def test_canonical_identifiers(self):
        for value in (4013500, 4013500.0, 4013500.0000001, '4013500.00', '4.0135e6', '04013500'):
            with self.subTest(value=value):
                self.assertEqual(normalize_dow(value), '04013500')
        for value in (None, float('nan'), True, False, 'junk', 'N/A', 100000000, 4013500.25, -1):
            with self.subTest(value=value):
                self.assertIsNone(normalize_dow(value))

    def test_clean_values(self):
        for value in ('', ' NULL ', 'N/A', 'none', '<NA>', float('nan')):
            self.assertIsNone(clean(value))
        self.assertEqual(clean('0'), 0)
        self.assertIs(clean('Y'), True)
        self.assertIs(clean('N'), False)
        self.assertEqual(clean('08/09/1971', 'surveyDate'), '1971-08-09')
        self.assertEqual(clean(0, 'count'), 0)
        self.assertEqual(clean(946684800000, 'surveyDate'), '2000-01-01')
        self.assertEqual(clean('17972322155705002', 'survey_id'), '17972322155705002')

    def test_links_and_narratives(self):
        self.assertEqual(clean_url('http://maps.dnr.state.mn.us/a'), 'https://maps.dnr.state.mn.us/a')
        for value in ('#', 'none', 'javascript:alert(1)', 'https://', '/relative'):
            self.assertIsNone(clean_url(value))
        self.assertEqual(clean('<p>One &amp; two</p><p>Three</p>', 'narrative'), 'One & two Three')

    def test_observation_deduplication(self):
        result = {'waterClarity': [['08/09/1971', '14.5'], ['08/09/1971', '14.5']],
                  'surveys': [{'surveyID': '100', 'surveyDate': '2000-01-01',
                    'lengths': {'WAE': {'fishCount': [[10, 2], [10, 2], [0, 2], [12, 0], [-1, 1]]}},
                    'fishCatchSummaries': [{'species': 'WAE', 'CPUE': '0', 'averageWeight': '1.4', 'totalWeight': 100}]}]}
        bundle = lake_details(result)
        self.assertEqual(len(bundle['fish_lengths']), 1)
        self.assertEqual(len(bundle['clarity']), 1)
        self.assertEqual(bundle['clarity'][0]['date'], '1971-08-09')
        catch = bundle['fish_catches'][0]
        self.assertNotIn('totalWeight', catch)
        self.assertEqual(catch['average_weight_lb'], 1.4)
        self.assertEqual(catch['cpue'], 0)
        self.assertEqual(stable(bundle), stable(lake_details(result)))

    def test_cache_refresh_and_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch('Scripts.sync_lake_bundles.CACHE', Path(directory)):
            response = Mock(content=b'{"a":1}', text='{"a":1}')
            response.json.return_value = {'a': 1}
            with patch('Scripts.sync_lake_bundles.requests.Session') as session:
                session.return_value.get.return_value = response
                first = SourceCache().get('https://example.test/data')
                self.assertEqual(SourceCache().get('https://example.test/data'), first)
                self.assertEqual(session.return_value.get.call_count, 1)
                SourceCache(True).get('https://example.test/data')
                self.assertEqual(session.return_value.get.call_count, 2)
                response.json.side_effect = ValueError('HTML response')
                with self.assertRaises(ValueError):
                    SourceCache().get('https://example.test/blocked')
                self.assertEqual(len(list(Path(directory).glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
