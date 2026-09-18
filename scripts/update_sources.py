"""Refresh verifiable public sources and write a bilingual provenance report.

The script only refreshes sources with a documented public endpoint. Curated
historical datasets are never forward-filled: their observed coverage is
reported so users can decide whether a newer source is required.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any
import urllib.request

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
EN = ROOT / "data_processed" / "english"
CN = ROOT / "data_processed" / "chinese"
META = ROOT / "metadata"
RAW.mkdir(exist_ok=True)
EN.mkdir(parents=True, exist_ok=True)
CN.mkdir(parents=True, exist_ok=True)
META.mkdir(exist_ok=True)

NOW = datetime.now(timezone.utc)
CHECKED_AT = NOW.isoformat(timespec="seconds").replace("+00:00", "Z")
CURRENT_YEAR = NOW.year


def _world_bank_country(value: Any) -> str:
    """Return the human-readable country name from the API response."""
    if isinstance(value, dict):
        return str(value.get("value") or value.get("id") or "")
    return str(value or "")


def world_bank_gdp(
    indicator: str = "NY.GDP.MKTP.CD",
    date_start: int = 1960,
    date_end: int = CURRENT_YEAR,
) -> dict[str, Any]:
    """Download World Bank GDP (current US$) and write raw + bilingual files."""
    source_url = (
        "https://api.worldbank.org/v2/country/all/indicator/"
        f"{indicator}?format=json&per_page=20000&date={date_start}:{date_end}"
    )
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "Yile-Wang-Lab-Data-Hub/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)

    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError("World Bank API returned an unexpected response")
    _meta, records = payload[0], payload[1]
    rows = []
    for item in records:
        rows.append(
            {
                "country_code": item.get("countryiso3code"),
                "country": _world_bank_country(item.get("country")),
                "year": int(item["date"]) if item.get("date") else None,
                "value": item.get("value"),
                "indicator": indicator,
                "source": "World Bank",
                "source_url": source_url,
                "downloaded_at": CHECKED_AT,
            }
        )
    raw = pd.DataFrame(rows).sort_values(
        ["country_code", "year"], ascending=[True, False], na_position="last"
    )
    raw.to_csv(
        RAW / f"worldbank_{indicator}.csv", index=False, encoding="utf-8-sig"
    )

    english = raw.rename(
        columns={"value": "gdp_current_usd", "indicator": "indicator_code"}
    )
    english.to_csv(
        EN / "worldbank_gdp_current_usd__worldbank_en.csv",
        index=False,
        encoding="utf-8-sig",
    )
    chinese = english.rename(
        columns={
            "country_code": "国家代码",
            "country": "国家",
            "year": "年份",
            "gdp_current_usd": "国内生产总值（现价美元）",
            "indicator_code": "指标代码",
            "source": "来源",
            "source_url": "来源链接",
            "downloaded_at": "下载时间",
        }
    )
    chinese.to_csv(
        CN / "worldbank_gdp_current_usd__worldbank_cn.csv",
        index=False,
        encoding="utf-8-sig",
    )

    years = pd.to_numeric(raw["year"], errors="coerce").dropna().astype(int)
    return {
        "source_id": "worldbank_gdp_current_usd",
        "source_name_en": "World Bank GDP (current US$)",
        "source_name_cn": "世界银行国内生产总值（现价美元）",
        "source_url": source_url,
        "source_type": "official_public_api",
        "status": "verified_live_api",
        "records": int(len(raw)),
        "first_year": int(years.min()) if len(years) else None,
        "latest_year": int(years.max()) if len(years) else None,
        "checked_at": CHECKED_AT,
        "license_note_en": "World Bank open data; verify the current terms before redistribution.",
        "license_note_cn": "世界银行开放数据；再分发前仍应核对当前使用条款。",
    }


def _year_signal(path: Path) -> tuple[int | None, int | None]:
    """Find a conservative year range from a CSV without inventing years."""
    years: list[int] = []
    try:
        for chunk in pd.read_csv(path, chunksize=10000, low_memory=False):
            for column in chunk.columns:
                name = str(column)
                values = chunk[column].dropna().astype(str)
                if re.search(r"year|date|time|年份|年度|日期|时间", name, flags=re.I):
                    extracted = values.str.extract(r"^\s*((?:19|20)\d{2})\s*$", expand=False)
                    years.extend(pd.to_numeric(extracted, errors="coerce").dropna().astype(int).tolist())
                if re.fullmatch(r"\s*(?:19|20)\d{2}\s*", name):
                    years.append(int(name.strip()))
    except Exception:
        return None, None
    if not years:
        return None, None
    return min(years), max(years)


def repository_sources() -> list[dict[str, Any]]:
    """Read the local inventory and attach official GitHub source links."""
    inventory_path = META / "repository_inventory.json"
    if not inventory_path.exists():
        return []
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    rows = []
    for item in inventory:
        repo = item.get("repo", "")
        rows.append(
            {
                "source_id": repo.replace("/", "__"),
                "source_name_en": repo,
                "source_name_cn": repo,
                "source_url": f"https://github.com/{repo}",
                "source_type": "public_github_repository",
                "status": "repository_snapshot_checked",
                "records": item.get("files"),
                "first_year": None,
                "latest_year": None,
                "checked_at": CHECKED_AT,
                "upstream_updated_at": item.get("updated_at"),
                "license_note_en": "Repository-level license status must be checked before reuse or redistribution.",
                "license_note_cn": "复用或再分发前必须核对该仓库的许可证状态。",
            }
        )
    return rows


def dataset_coverage() -> list[dict[str, Any]]:
    """Write a file-level coverage table for the standardized English files."""
    index_path = META / "usable_dataset_index_bilingual.csv"
    if not index_path.exists():
        return []
    index = pd.read_csv(index_path, dtype=str).fillna("")
    rows = []
    for item in index.to_dict("records"):
        english_file = ROOT / item.get("english_file", "")
        first_year, latest_year = _year_signal(english_file) if english_file.exists() else (None, None)
        rows.append(
            {
                "dataset_id": item.get("dataset_id", ""),
                "english_file": item.get("english_file", ""),
                "chinese_file": item.get("chinese_file", ""),
                "rows": item.get("rows", ""),
                "columns": item.get("columns", ""),
                "source_paths": item.get("source_paths", ""),
                "first_year_detected": first_year,
                "latest_year_detected": latest_year,
                "coverage_status": "observed_from_file; no forward fill",
                "checked_at": CHECKED_AT,
            }
        )
    return rows


def write_reports(public_sources: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> None:
    source_rows = public_sources + repository_sources()
    pd.DataFrame(source_rows).to_csv(
        META / "source_verification_bilingual.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(coverage).to_csv(
        META / "data_coverage_audit_bilingual.csv",
        index=False,
        encoding="utf-8-sig",
    )

    manifest = {
        "checked_at": CHECKED_AT,
        "latest_requested_year": CURRENT_YEAR,
        "public_sources": public_sources,
        "repository_sources": repository_sources(),
        "coverage_file": "metadata/data_coverage_audit_bilingual.csv",
        "rule": "Only observed source years are reported; no year is extrapolated or forward-filled.",
    }
    (META / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (META / "update_run.json").write_text(
        json.dumps(
            {
                "checked_at": CHECKED_AT,
                "latest_requested_year": CURRENT_YEAR,
                "public_source_count": len(public_sources),
                "repository_source_count": len(repository_sources()),
                "dataset_coverage_rows": len(coverage),
                "rule": "No forward filling or fabricated latest-year observations.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    public_sources = [world_bank_gdp()]
    coverage = dataset_coverage()
    write_reports(public_sources, coverage)
    print(
        json.dumps(
            {
                "checked_at": CHECKED_AT,
                "world_bank_latest_year": public_sources[0]["latest_year"],
                "dataset_coverage_rows": len(coverage),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
