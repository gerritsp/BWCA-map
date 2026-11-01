"""Build the search index directly from normalized bundles, preserving all IDs."""
import json
from pathlib import Path
import sys
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Scripts.sync_lake_bundles import write


# Indicator gear makes catch rates comparable between lakes for these species.
# Other species fall back to their latest recorded gear, which is exposed in the UI.
INDICATOR_GEAR = {
    'WAE': 'Standard gill nets',
}


def abundance_record(catches, species):
    records = [row for row in catches if row.get('species') == species]
    preferred = INDICATOR_GEAR.get(species)
    if preferred:
        preferred_records = [row for row in records if row.get('gear') == preferred]
        if preferred_records:
            records = preferred_records
    if not records:
        return [None] * 7

    record = max(records, key=lambda row: (
        row.get('date') or '', str(row.get('survey_id') or ''),
        row.get('gearCount') if isinstance(row.get('gearCount'), (int, float)) else -1,
    ))
    survey_id, date, gear = record.get('survey_id'), record.get('date'), record.get('gear')
    same_gear_sample = [
        row for row in catches
        if row.get('survey_id') == survey_id
        and row.get('date') == date
        and row.get('gear') == gear
    ]
    total = record.get('totalCatch')
    denominator = sum(
        row['totalCatch'] for row in same_gear_sample
        if isinstance(row.get('totalCatch'), (int, float))
    )
    share = round(total / denominator * 100, 1) if isinstance(total, (int, float)) and denominator else None
    cpue = record.get('cpue')
    if isinstance(cpue, (int, float)):
        cpue = round(cpue, 3)
    else:
        cpue = None
    return [cpue, total if isinstance(total, (int, float)) else None, share,
            date, gear, record.get('gearCount'), record.get('quartileCount')]


def search_row(bundle):
    info = bundle['lake_info']
    sp = {}
    species = {r['species'] for r in bundle['fish_lengths'] + bundle['fish_catches']}
    for code in sorted(species):
        lengths = [r['length_inches'] for r in bundle['fish_lengths'] if r['species'] == code]
        # Compact schema: [max length, CPUE, total caught, same-gear share,
        #                  date, gear, gear effort, DNR normal CPUE range].
        sp[code] = [max(lengths, default=None), *abundance_record(bundle['fish_catches'], code)]
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
