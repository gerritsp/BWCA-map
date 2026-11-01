"""Build deterministic, polygon-level lake bundles from official source caches.

Network responses are cached by full request URL. Failed/HTML responses never
become empty successful data. Default builds require all sources; use
--allow-incomplete explicitly to inspect a partial snapshot after an outage.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import os
import tempfile
from urllib.parse import urlencode, urlsplit, urlunsplit

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from models.lake_ids import normalize_dow

OUT = ROOT / 'maps/fisheries'
CACHE = ROOT / '.cache/lake-data'
METADATA = 'https://services.dnr.state.mn.us/api/lakefinder/by_id/v1'
DETAIL = 'https://maps.dnr.state.mn.us/cgi-bin/lakefinder/detail.cgi'
SPECIES = 'https://maps.dnr.state.mn.us/lakefinder/lib/lakefinder.js'
INVENTORY = 'https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_dnr/env_lakes_surveyed_by_mndnr/MapServer'
MORPHOLOGY = 'https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_dnr/water_lake_basin_morphology/FeatureServer/1'
MPCA = 'https://services.pca.state.mn.us/api/v1/surfacewater'
HUC8 = ('09030001', '09030002', '09030003', '04010101')
NULLS = {'', 'null', 'n/a', 'na', 'none', '<na>', 'nan'}
IDENTIFIERS = {'surveyID', 'survey_id', 'wb_id', 'DOWNumber', 'dowlknum', 'id', 'code', 'officeCode', 'county_id', 'huc8', 'wid', 'auid', 'assessmentId'}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'br', 'div', 'li'):
            self.parts.append(' ')
    def handle_endtag(self, tag):
        if tag in ('p', 'div', 'li'):
            self.parts.append(' ')


def plain_text(value):
    parser = PlainText()
    parser.feed(unescape(value).replace('\\n', ' '))
    return ' '.join(''.join(parser.parts).split()) or None


def clean_url(value):
    if not isinstance(value, str):
        return None
    parts = urlsplit(value.strip())
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    scheme = 'https' if parts.hostname == 'dnr.state.mn.us' or parts.hostname.endswith('.dnr.state.mn.us') else parts.scheme
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def clean(value, key=''):
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: clean(v, k) for k, v in sorted(value.items()) if k != 'totalWeight'}
    if isinstance(value, (tuple, list)):
        return [clean(v, key) for v in value]
    if isinstance(value, str):
        value = value.strip()
        if value.lower() in NULLS:
            return None
        if key.lower().endswith(('url', 'link')):
            return clean_url(value)
        if 'narrative' in key.lower():
            return plain_text(value)
        if value in ('Y', 'N'):
            return value == 'Y'
        if key in IDENTIFIERS:
            return value
        if 'date' in key.lower():
            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ'):
                try:
                    return datetime.strptime(value, fmt).date().isoformat()
                except ValueError:
                    pass
        try:
            number = Decimal(value)
            if number.is_finite():
                return int(number) if number == number.to_integral_value() else float(number)
        except InvalidOperation:
            pass
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if pd.isna(value):
            return None
        if 'date' in key.lower() and abs(value) > 10**10:
            return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
        return value
    return None if pd.isna(value) else value


def stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def unique(rows):
    return [json.loads(s) for s in sorted({stable(row) for row in rows})]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        handle.write(stable(value) + '\n')
        temporary = handle.name
    os.replace(temporary, path)


class SourceCache:
    def __init__(self, refresh=False):
        self.refresh = refresh
    def get(self, base, params=None, text=False):
        url = base + ('?' + urlencode(sorted(params.items())) if params else '')
        path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if path.exists() and not self.refresh:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record['url'] != url:
                raise ValueError('Cache URL mismatch')
            return record['data'], {'url': url, 'sha256': record['sha256']}
        session = requests.Session()
        session.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])))
        response = session.get(url, timeout=(15, 60))
        response.raise_for_status()
        data = response.text if text else response.json()
        if isinstance(data, dict) and data.get('error'):
            raise ValueError(f'{url}: {data["error"]}')
        digest = hashlib.sha256(response.content).hexdigest()
        write(path, {'url': url, 'sha256': digest, 'data': data})
        return data, {'url': url, 'sha256': digest}


def arcgis(cache, base, where):
    """Page with stable OID order; use source field types to normalize dates."""
    schema, schema_provenance = cache.get(base, {'f': 'json'})
    fields = {f['name']: f['type'] for f in schema['fields']}
    oid = next(k for k, v in fields.items() if v == 'esriFieldTypeOID')
    rows, provenance, offset = [], [schema_provenance], 0
    while True:
        result, source = cache.get(base + '/query', {
            'f': 'json', 'where': where, 'outFields': '*', 'returnGeometry': 'false',
            'orderByFields': oid, 'resultOffset': offset, 'resultRecordCount': 1000,
        })
        provenance.append(source)
        features = result['features']
        for feature in features:
            row = feature['attributes']
            for key, typ in fields.items():
                if typ == 'esriFieldTypeDate' and row.get(key) is not None:
                    row[key] = datetime.fromtimestamp(row[key] / 1000, timezone.utc).date().isoformat()
            rows.append(clean(row))
        if not result.get('exceededTransferLimit'):
            break
        if not features:
            raise ValueError('ArcGIS pagination made no progress')
        offset += len(features)
    return unique(rows), provenance


def lake_details(result):
    """Normalize surveyed observations without interpreting raw totalWeight."""
    result = result or {}
    surveys, lengths, catches = [], [], []
    for raw in result.get('surveys', []):
        survey = clean(raw)
        sid = str(raw.get('surveyID', raw.get('headerInfo', {}).get('survey_id', '')))
        date = clean(raw.get('surveyDate'), 'surveyDate')
        for species, values in (raw.get('lengths') or {}).items():
            for length, count in values.get('fishCount', []):
                length, count = clean(length), clean(count)
                if isinstance(length, (int, float)) and isinstance(count, (int, float)) and length > 0 and count > 0:
                    lengths.append({'survey_id': sid, 'date': date, 'species': species, 'length_inches': length, 'count': count})
        for catch in raw.get('fishCatchSummaries', []):
            row = clean(catch)
            row['average_weight_lb'] = row.pop('averageWeight', None)
            row['cpue'] = row.pop('CPUE', None)
            row.update(survey_id=sid, date=date)
            catches.append(row)
        survey.pop('lengths', None)
        survey.pop('fishCatchSummaries', None)
        surveys.append(survey)
    return {
        'surveys': unique(surveys), 'fish_lengths': unique(lengths), 'fish_catches': unique(catches),
        'clarity': unique([{'date': clean(r[0], 'date'), 'clarity_ft': clean(r[1])} for r in result.get('waterClarity', []) if isinstance(r, list) and len(r) >= 2]),
        'access': unique(clean(result.get('accesses') or [])),
        'plants': unique(clean(result.get('sampledPlants') or [])),
        'lake_info': clean({k: v for k, v in result.items() if k not in ('surveys', 'waterClarity', 'accesses', 'sampledPlants')}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--allow-incomplete', action='store_true')
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    cache = SourceCache(args.refresh)
    lakes = pd.read_parquet(ROOT / 'Data/processed/bwca_lakes.parquet')
    lakes['dowlknum'] = lakes.dowlknum.map(normalize_dow)
    lakes['unique_guid'] = lakes.unique_guid.astype(str)
    project = lakes[lakes.dowlknum.notna()].sort_values('unique_guid')
    if project.unique_guid.duplicated().any():
        raise ValueError('Duplicate polygon GUIDs')
    dows = sorted(set(project.dowlknum))
    failures = []
    def fetch_lake(dow):
        provenance, data = [], {}
        for key, base, params in (
            ('metadata', METADATA, {'id': dow}),
            ('details', DETAIL, {'type': 'lake_survey', 'id': dow}),
        ):
            try:
                response, source = cache.get(base, params)
                provenance.append(source)
                if key == 'metadata':
                    results = response.get('results') or []
                    if response.get('status') != 'OK' and response.get('message') != 'Search returned no results.':
                        raise ValueError(f'Unexpected metadata status: {response.get("status")}')
                    if results and normalize_dow(results[0].get('id')) != dow:
                        raise ValueError('Metadata DOW mismatch')
                    data[key] = results[0] if results else {}
                else:
                    if response.get('status') != 'SUCCESS' and response.get('message') != 'The requested lake survey data is not available.':
                        raise ValueError(f'Unexpected details status: {response.get("status")}')
                    data[key] = response.get('result') or {}
                    if data[key] and normalize_dow(data[key].get('DOWNumber')) != dow:
                        raise ValueError('Details DOW mismatch')
            except Exception as exc:
                failures.append({'source': key, 'dowlknum': dow, 'error': str(exc)})
                data[key] = {}
        return dow, data, provenance
    per_dow = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, (dow, data, provenance) in enumerate(pool.map(fetch_lake, dows), 1):
            per_dow[dow] = (data, provenance)
            if n % 100 == 0:
                print(f'LakeFinder {n}/{len(dows)}', flush=True)
    inventory_lakes, inventory, morphology, global_sources = [], [], [], []
    quoted = ','.join("'" + d + "'" for d in dows)
    # Chunk predicates avoid oversized URLs and keep each source response reusable.
    tasks = []
    for start in range(0, len(dows), 100):
        where = 'dowlknum IN (' + ','.join("'" + d + "'" for d in dows[start:start+100]) + ')'
        tasks.extend((key, base, target, where) for key, base, target in (
            ('inventory_lakes', INVENTORY + '/0', inventory_lakes),
            ('morphology', MORPHOLOGY, morphology)))
    def fetch_arcgis(task):
        key, base, target, where = task
        try:
            rows, sources = arcgis(cache, base, where)
            return target, rows, sources, None
        except Exception as exc:
            return target, [], [], {'source': key, 'error': str(exc)}
    with ThreadPoolExecutor(max_workers=min(args.workers, 6)) as pool:
        for target, rows, sources, failure in pool.map(fetch_arcgis, tasks):
            target.extend(rows)
            global_sources.extend(sources)
            if failure:
                failures.append(failure)
    print(f'ArcGIS lake inventory: {len(inventory_lakes)} rows; morphology: {len(morphology)} rows', flush=True)
    fw_ids = sorted({str(int(r['fw_id'])) for r in inventory_lakes if r.get('fw_id') is not None})
    for start in range(0, len(fw_ids), 100):
        try:
            rows, sources = arcgis(cache, INVENTORY + '/1', 'fw_id IN (' + ','.join(fw_ids[start:start+100]) + ')')
            inventory.extend(rows)
            global_sources.extend(sources)
        except Exception as exc:
            failures.append({'source': 'inventory', 'error': str(exc)})
    assessments = []
    for huc in HUC8:
        try:
            response, source = cache.get(MPCA + '/assessments', {'format': 'json', 'huc8': huc})
            global_sources.append(source)
            rows = response if isinstance(response, list) else response.get('results', response.get('data'))
            if not isinstance(rows, list):
                raise ValueError('Unrecognized MPCA assessment schema')
            assessments.extend(clean(rows))
        except Exception as exc:
            failures.append({'source': 'mpca', 'huc8': huc, 'error': str(exc)})
    species = {}
    try:
        js, source = cache.get(SPECIES, text=True)
        global_sources.append(source)
        match = re.search(r'var fish_species\s*=\s*({.*?});', js, re.S)
        species = json.loads(match[1])
    except Exception as exc:
        failures.append({'source': 'species', 'error': str(exc)})
    if failures and not args.allow_incomplete:
        write(CACHE / 'failures.json', sorted(failures, key=stable))
        raise SystemExit(f'{len(failures)} source failures; existing bundles untouched. See .cache/lake-data/failures.json')
    project_source = {'path': 'Data/processed/bwca_lakes.parquet', 'sha256': hashlib.sha256((ROOT / 'Data/processed/bwca_lakes.parquet').read_bytes()).hexdigest()}
    bundles, fish_index, survey_index = {}, {}, {}
    for row in project.to_dict('records'):
        guid, dow = row['unique_guid'], row['dowlknum']
        data, sources = per_dow[dow]
        metadata = clean(data['metadata'])
        bundle = lake_details(data['details'])
        inv_lakes = [r for r in inventory_lakes if normalize_dow(r.get('dowlknum')) == dow]
        inv_fw = {r['fw_id'] for r in inv_lakes}
        inv = [r for r in inventory if r.get('fw_id') in inv_fw]
        matched_assessments = []
        for assessment in assessments:
            aid = assessment.get('dowlknum') or assessment.get('lakeId') or assessment.get('wid') or assessment.get('assessmentUnitId') or assessment.get('auid')
            if assessment.get('wuType', '').lower() != 'lake':
                continue
            if isinstance(aid, str):
                aid = aid.replace('-', '')[:8]
            if normalize_dow(aid) == dow:
                matched_assessments.append(assessment)
        bundle.update(schema_version=3, unique_guid=guid, dowlknum=dow,
            name=clean(row.get('map_label')) or clean(row.get('pw_basin_name')) or 'Unnamed',
            project={'fw_id': clean(row.get('fw_id')), 'area_acres': clean(row.get('acres')), 'shoreline_miles': clean(row.get('shore_mi'))},
            metadata=metadata, known_species=metadata.get('fishSpecies', []), invasives=metadata.get('invasiveSpecies', []),
            special_regulations=metadata.get('specialFishingRegs', []), resource_flags=metadata.get('resources', {}),
            morphology=unique([r for r in morphology if normalize_dow(r.get('dowlknum')) == dow]),
            assessments=unique(matched_assessments), survey_inventory_lakes=unique(inv_lakes), survey_inventory=unique(inv),
            join_keys={'unique_guid': guid, 'dowlknum': dow, 'inventory_fw_ids': sorted(inv_fw)},
            provenance=unique(sources + global_sources + [project_source]), incomplete=bool(failures))
        # Resource availability flags in metadata are encoded as 0/1 by DNR.
        bundle['resource_flags'] = {k: bool(v) if v in (0, 1) else v for k, v in bundle['resource_flags'].items()}
        write(OUT / (guid + '.json'), bundle)
        bundles[guid] = {'dowlknum': dow, 'name': bundle['name']}
        fish_index[guid] = sorted({r['species'] for r in bundle['fish_lengths'] + bundle['fish_catches']})
        survey_index[guid] = {'detailed': len(bundle['surveys']), 'inventory': len(inv)}
    counts = {'bundles': len(bundles), 'distinct_dow': len(dows)}
    for key, field in [('detailed_surveys', 'surveys'), ('fish_observations', 'fish_catches'), ('clarity_lakes', 'clarity')]:
        counts[key] = sum(bool(lake_details(v[0]['details'])[field]) for v in per_dow.values())
    counts['survey_inventory_lakes'] = len({normalize_dow(r['dowlknum']) for r in inventory_lakes})
    counts['survey_inventory_records'] = len(unique(inventory))
    for name, value in [('_index', bundles), ('_fish_index', fish_index), ('_survey_index', survey_index), ('species', species),
                        ('_manifest', {'schema_version': 3, 'counts': counts, 'failures': sorted(failures, key=stable), 'incomplete': bool(failures), 'sources': unique(global_sources), 'excluded_no_dow_polygons': len(lakes)-len(project)})]:
        write(OUT / (name + '.json'), value)
    print(stable(counts))


if __name__ == '__main__':
    main()
