"""Build the search index directly from normalized bundles, preserving all IDs."""
import json
from pathlib import Path
import sys
import pandas as pd
from statistics import mean
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Scripts.sync_lake_bundles import write


def search_row(bundle):
    info = bundle['lake_info']
    sp = {}
    species = {r['species'] for r in bundle['fish_lengths'] + bundle['fish_catches']}
    for code in sorted(species):
        lengths = [r['length_inches'] for r in bundle['fish_lengths'] if r['species'] == code]
        cpue = [r['cpue'] for r in bundle['fish_catches'] if r['species'] == code and isinstance(r.get('cpue'), (int, float))]
        sp[code] = [max(lengths, default=None), round(mean(cpue), 3) if cpue else None]
    clarity = info.get('averageWaterClarity')
    return {'g': bundle['unique_guid'], 'dowlknum': bundle['dowlknum'], 'n': bundle['name'],
            'ac': info.get('areaAcres', bundle['project']['area_acres']),
            'md': info.get('maxDepthFeet'), 'cl': clarity, 'cs': 0, 'sp': sp}


def main():
    directory = ROOT / 'maps/fisheries'
    index = json.loads((directory / '_index.json').read_text(encoding='utf-8'))
    rows = [search_row(json.loads((directory / (guid + '.json')).read_text(
        encoding='utf-8'))) for guid in sorted(index)]
    camps_path = ROOT / 'Data/processed/bwca_campsites_river.parquet'
    if camps_path.exists():
        camps = pd.read_parquet(camps_path)
        if 'STATUS' in camps:
            camps = camps[camps.STATUS.eq('open')]
        counts = camps.lake_unique_guid.astype(str).value_counts()
        for row in rows:
            row['cs'] = int(counts.get(row['g'], 0))
    write(ROOT / 'maps/lake_search_index.json', rows)
    print(f'{len(rows)} search entries')


if __name__ == '__main__':
    main()
