"""Compare a Stealing-fish checkout with the normalized BWCA lake bundles.

This is a lineage/reconciliation check, not an alternate production input.
The BWCA app continues to fetch the official sources directly.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Scripts.sync_lake_bundles import clean, plain_text, stable


COMPARABLE = ("surveys", "catches", "lengths", "clarity", "access", "plants")


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value):
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def row_key(value):
    return stable(canonical(clean(value)))


def project_rows():
    by_dow = {}
    for path in (ROOT / "maps/fisheries").glob("{*.json"):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        by_dow.setdefault(bundle["dowlknum"], bundle)

    output = {key: [] for key in (*COMPARABLE, "lake_info", "inventory_lakes", "inventory")}
    seen_inventory_lakes = set()
    seen_inventory = set()
    for dow, bundle in by_dow.items():
        for row in bundle["surveys"]:
            header = row.get("headerInfo") or {}
            output["surveys"].append({
                "dowlknum": dow,
                "survey_id": str(row.get("surveyID") or header.get("survey_id") or ""),
                "survey_date": row.get("surveyDate"),
                "survey_type": row.get("surveyType"),
                "survey_subtype": row.get("surveySubType"),
                "lake_name": header.get("wb_name"),
                "county": header.get("county"),
                "narrative": row.get("narrative"),
            })
        for row in bundle["fish_catches"]:
            output["catches"].append({
                "dowlknum": dow,
                "survey_id": str(row.get("survey_id") or ""),
                "survey_date": row.get("date"),
                "species": row.get("species"),
                "gear": row.get("gear"),
                "gearCount": row.get("gearCount"),
                "totalCatch": row.get("totalCatch"),
                "cpue": row.get("cpue"),
                "average_weight_lb": row.get("average_weight_lb"),
                "quartileWeight": row.get("quartileWeight"),
                "quartileCount": row.get("quartileCount"),
            })
        for row in bundle["fish_lengths"]:
            output["lengths"].append({
                "dowlknum": dow,
                "survey_id": str(row.get("survey_id") or ""),
                "survey_date": row.get("date"),
                "species": row.get("species"),
                "length_inches": row.get("length_inches"),
                "fish_count": row.get("count"),
            })
        output["clarity"].extend(
            {"dowlknum": dow, "date": row.get("date"), "clarity_ft": row.get("clarity_ft")}
            for row in bundle["clarity"]
        )
        output["access"].extend({
            "dowlknum": dow,
            "location": row.get("location"),
            "access_type": row.get("accessTypeId"),
            "public_use_authorization": row.get("publicUseAuthCode"),
            "owner_type": row.get("ownerTypeId"),
            "comments": row.get("lakeAccessComments"),
        } for row in bundle["access"])
        output["plants"].extend(
            {"dowlknum": dow, "plant": plant} for plant in bundle["plants"]
        )
        info = bundle["lake_info"]
        if info:
            output["lake_info"].append({
                "dowlknum": dow,
                "lake_name": info.get("lakeName"),
                "mean_depth_ft": info.get("meanDepthFeet"),
                "max_depth_ft": info.get("maxDepthFeet"),
                "area_acres": info.get("areaAcres"),
                "littoral_acres": info.get("littoralAcres"),
                "shoreline_miles": info.get("shoreLengthMiles"),
                "county": info.get("county"),
                "office_code": info.get("officeCode"),
                "average_water_clarity_ft": info.get("averageWaterClarity"),
            })
        for row in bundle["survey_inventory_lakes"]:
            key = row_key(row)
            if key not in seen_inventory_lakes:
                output["inventory_lakes"].append(row)
                seen_inventory_lakes.add(key)
        for row in bundle["survey_inventory"]:
            key = row_key(row)
            if key not in seen_inventory:
                output["inventory"].append(row)
                seen_inventory.add(key)
    return output


def _parquet_rows(path):
    return [{key: clean(value, key) for key, value in row.items()}
            for row in pd.read_parquet(path).to_dict("records")]


def _arcgis_rows(path):
    rows = pd.read_parquet(path).to_dict("records")
    for row in rows:
        for key, value in row.items():
            if (key.endswith("_date") or key == "srv_date") and isinstance(value, (int, float)) and pd.notna(value):
                row[key] = datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
    return [{key: clean(value, key) for key, value in row.items()} for row in rows]


def stealing_rows(checkout):
    directory = checkout / "fisheries"
    output = {
        "surveys": _parquet_rows(directory / "dnr_surveys.parquet"),
        "catches": _parquet_rows(directory / "dnr_fish_catches.parquet"),
        "lengths": _parquet_rows(directory / "dnr_fish_lengths.parquet"),
        "clarity": _parquet_rows(directory / "dnr_water_clarity.parquet"),
        "access": _parquet_rows(directory / "dnr_accesses.parquet"),
        "plants": _parquet_rows(directory / "dnr_plants.parquet"),
        "lake_info": _parquet_rows(directory / "dnr_lake_info.parquet"),
        "inventory_lakes": _arcgis_rows(directory / "dnr_arcgis_surveyed_lakes.parquet"),
        "inventory": _arcgis_rows(directory / "dnr_arcgis_all_surveys.parquet"),
    }
    for row in output["surveys"]:
        row["narrative"] = plain_text(row["narrative"]) if row.get("narrative") else None
    for row in output["catches"]:
        row.pop("total_weight", None)
        row["average_weight_lb"] = row.pop("average_weight", None)
        row["gearCount"] = row.pop("gear_count", None)
        row["totalCatch"] = row.pop("total_catch", None)
        row["quartileWeight"] = row.pop("quartile_weight", None)
        row["quartileCount"] = row.pop("quartile_count", None)
    raw_length_count = len(output["lengths"])
    output["lengths"] = [
        row for row in output["lengths"]
        if (row.get("length_inches") or 0) > 0 and (row.get("fish_count") or 0) > 0
    ]
    output["excluded_length_bins"] = raw_length_count - len(output["lengths"])
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path, help="Stealing-fish checkout at commit 0d2e770")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    project_lakes = ROOT / "Data/processed/bwca_lakes.parquet"
    stealing_lakes = checkout / "bwca_lakes.parquet"
    if not stealing_lakes.exists():
        raise SystemExit(f"Missing Stealing-fish lake file: {stealing_lakes}")
    lake_hash = file_sha256(project_lakes)
    stealing_lake_hash = file_sha256(stealing_lakes)
    print(f"bwca_lakes SHA256 official={lake_hash} stealing={stealing_lake_hash}")
    if lake_hash != stealing_lake_hash:
        raise SystemExit("Stealing-fish uses a different bwca_lakes.parquet")
    project = project_rows()
    stealing = stealing_rows(checkout)
    print(f"Excluded {stealing['excluded_length_bins']} non-positive Stealing-fish length bins")
    problems = []
    for category in (*COMPARABLE, "inventory_lakes", "inventory"):
        official = {row_key(row) for row in project[category]}
        discovered = {row_key(row) for row in stealing[category]}
        print(f"{category:16s} official={len(official):5d} stealing={len(discovered):5d} "
              f"stealing_only={len(discovered - official):3d} "
              f"official_only={len(official - discovered):3d}")
        if discovered - official:
            problems.append(category)

    official_info = {row["dowlknum"]: row_key(row) for row in project["lake_info"]}
    stealing_info = {row["dowlknum"]: row_key(row) for row in stealing["lake_info"]}
    changed = sum(official_info.get(dow) != row for dow, row in stealing_info.items())
    missing_dows = set(stealing_info) - set(official_info)
    print(f"{'lake_info':16s} same_dows={len(set(official_info) & set(stealing_info)):5d} "
          f"changed_values={changed:3d} missing_official={len(missing_dows):3d}")
    if missing_dows:
        problems.append("lake_info")
    if problems:
        raise SystemExit("Stealing-fish has unmatched additive data in: " + ", ".join(problems))


if __name__ == "__main__":
    main()
