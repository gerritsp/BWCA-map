"""Validate polygon correspondence and normalized observation invariants."""
import json
from pathlib import Path
import re
import sys
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from models.lake_ids import normalize_dow
from Scripts.sync_lake_bundles import stable


def validate(root=ROOT, require_complete=True):
    directory = root / 'maps/fisheries'
    index = json.loads((directory / '_index.json').read_text(encoding='utf-8'))
    manifest = json.loads((directory / '_manifest.json').read_text(encoding='utf-8'))
    assert manifest['schema_version'] == 3
    if require_complete:
        assert not manifest['incomplete'], 'Snapshot has unresolved source failures'
    source = pd.read_parquet(root / 'Data/processed/bwca_lakes.parquet', columns=['unique_guid', 'dowlknum'])
    expected = {str(r.unique_guid): normalize_dow(r.dowlknum) for r in source.itertuples() if normalize_dow(r.dowlknum) is not None}
    assert set(index) == set(expected), 'Bundle index differs from project polygons'
    rows = json.loads((root / 'maps/lake_search_index.json').read_text(encoding='utf-8'))
    assert len(rows) == len(index), 'Search index length mismatch'
    assert len({r['g'] for r in rows}) == len(rows), 'Duplicate search GUID'
    assert {r['g'] for r in rows} == set(index), 'Search GUID mismatch'
    for row in rows:
        guid, dow = row['g'], row['dowlknum']
        assert isinstance(guid, str) and guid and Path(guid).name == guid, 'Invalid search GUID'
        assert isinstance(dow, str) and re.fullmatch(r'\d{8}', dow), 'Invalid search DOW'
        assert dow == normalize_dow(dow) == expected[guid] == index[guid]['dowlknum'], 'DOW mismatch'
        bundle = json.loads((directory / (guid + '.json')).read_text(encoding='utf-8'))
        assert bundle['unique_guid'] == guid and bundle['dowlknum'] == dow
        assert bundle['schema_version'] == 3 and bundle['provenance']
        assert bundle['join_keys']['unique_guid'] == guid and bundle['join_keys']['dowlknum'] == dow
        assert '"totalWeight":' not in stable(bundle)
        for key in ('fish_lengths', 'clarity', 'survey_inventory', 'survey_inventory_lakes'):
            assert len(bundle[key]) == len({stable(r) for r in bundle[key]}), f'Duplicates in {key}'
        for fish in bundle['fish_lengths']:
            assert fish['count'] > 0 and fish['length_inches'] > 0
        assert row['n'] == bundle['name']
    print(f'Validated {len(rows)} bundles and exact search correspondence')
    return len(rows)


if __name__ == '__main__':
    validate()
