from __future__ import annotations

import csv, hashlib, json, shutil, sys, zipfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

START = date(2021, 7, 12)
END = date(2026, 7, 11)
COMMIT = "c6b3e94d6680b26ab1289706f0964fcd6bac84d2"
PRODUCTS = ("bingo18", "keno", "lotto535", "max3d", "max3dpro", "max4d", "mega645", "power655")
RAW = ("product", "draw_id", "draw_date", "draw_status", "result_json", "attributes_json", "official_pdf_urls_json", "source_url", "prize_status", "validation_status", "validation_warnings_json", "fetched_at")
FLAT = ("product", "draw_id", "draw_date", "draw_time", "draw_status", "result_type", "result_display", "numbers", "special_numbers", "digits", "tiers_json", "data_source", "official_verification_status", "prize_status", "validation_status", "validation_warnings", "source_url", "official_pdf_urls", "fetched_at", "result_json", "attributes_json")

SRC = Path("source/datasets")
OUT = Path("export")
if OUT.exists():
    shutil.rmtree(OUT)
NAME = "vietlott_ket_qua_5_nam_2021-07-12_2026-07-11"
ROOT = OUT / NAME
META = ROOT / "metadata"
for p in (ROOT / "raw", ROOT / "flat", META):
    p.mkdir(parents=True, exist_ok=True)
csv.field_size_limit(sys.maxsize)


def jload(text, fallback):
    if not text:
        return fallback
    return json.loads(text)


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def nums(values):
    if not isinstance(values, list):
        return ""
    return "-".join(f"{v:02d}" if isinstance(v, int) else str(v) for v in values)


def flatten(row):
    result = jload(row["result_json"], {})
    attrs = jload(row["attributes_json"], {})
    pdfs = jload(row["official_pdf_urls_json"], [])
    warns = jload(row["validation_warnings_json"], [])
    rtype, display, numbers, special, digits, tiers = "other", compact(result), "", "", "", ""
    if isinstance(result, dict) and isinstance(result.get("numbers"), list):
        rtype, numbers = "numbers", nums(result["numbers"])
        special = nums(result.get("special_numbers", []))
        display = numbers + (f" | ĐB {special}" if special else "")
    elif isinstance(result, dict) and isinstance(result.get("digits"), list):
        rtype = "digits"
        digits = "".join(str(v) for v in result["digits"])
        display = digits
    elif isinstance(result, dict) and isinstance(result.get("tiers"), dict):
        rtype, tiers = "tiers", compact(result["tiers"])
        display = "; ".join(f"{k}:{'|'.join(map(str, v)) if isinstance(v, list) else v}" for k, v in result["tiers"].items())
    if not isinstance(attrs, dict):
        attrs = {}
    return {
        "product": row["product"], "draw_id": row["draw_id"], "draw_date": row["draw_date"],
        "draw_time": str(attrs.get("draw_time", "")), "draw_status": row["draw_status"],
        "result_type": rtype, "result_display": display, "numbers": numbers,
        "special_numbers": special, "digits": digits, "tiers_json": tiers,
        "data_source": str(attrs.get("data_source", "")),
        "official_verification_status": str(attrs.get("official_verification_status", "")),
        "prize_status": row["prize_status"], "validation_status": row["validation_status"],
        "validation_warnings": compact(warns), "source_url": row["source_url"],
        "official_pdf_urls": compact(pdfs), "fetched_at": row["fetched_at"],
        "result_json": row["result_json"], "attributes_json": row["attributes_json"],
    }


def files_for(product):
    folder = SRC / "draws" / product
    all_file = folder / "all.csv"
    return [all_file] if all_file.exists() else sorted(folder.glob("????-??.csv"))


seen = set()
stats = {}
total_status = Counter()
total_validation = Counter()
combined_raw = ROOT / "raw/vietlott_draws_5y_raw.csv"
combined_flat = ROOT / "flat/vietlott_draws_5y_flat.csv"
combined_raw.parent.mkdir(parents=True, exist_ok=True)
combined_flat.parent.mkdir(parents=True, exist_ok=True)

with combined_raw.open("w", newline="", encoding="utf-8-sig") as arf, combined_flat.open("w", newline="", encoding="utf-8-sig") as aff:
    arw, afw = csv.DictWriter(arf, RAW), csv.DictWriter(aff, FLAT)
    arw.writeheader(); afw.writeheader()
    for product in PRODUCTS:
        source_files = files_for(product)
        if not source_files:
            raise RuntimeError(f"Không thấy tệp nguồn cho {product}")
        count, first, last = 0, None, None
        statuses, validations, sources = Counter(), Counter(), Counter()
        for src in source_files:
            if src.stat().st_size == 0:
                continue
            with src.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != RAW:
                    raise RuntimeError(f"Sai schema: {src}")
                for row in reader:
                    d = date.fromisoformat(row["draw_date"][:10])
                    if d < START or d > END:
                        continue
                    if row["product"] != product:
                        raise RuntimeError(f"Sai product trong {src}: {row['product']}")
                    key = (product, row["draw_id"])
                    if key in seen:
                        raise RuntimeError(f"Trùng khóa: {key}")
                    seen.add(key)
                    flat = flatten(row)
                    raw_row = {k: row.get(k, "") for k in RAW}
                    arw.writerow(raw_row); afw.writerow(flat)
                    count += 1; first = first or row["draw_date"]; last = row["draw_date"]
                    statuses[row["draw_status"]] += 1; validations[row["validation_status"]] += 1
                    total_status[row["draw_status"]] += 1; total_validation[row["validation_status"]] += 1
                    attrs = jload(row["attributes_json"], {})
                    sources[str(attrs.get("data_source", "unknown")) if isinstance(attrs, dict) else "unknown"] += 1
        if not count:
            raise RuntimeError(f"Không có kỳ nào trong cửa sổ ngày: {product}")
        stats[product] = {"rows": count, "first_date": first, "last_date": last,
                          "draw_status": dict(statuses), "validation_status": dict(validations),
                          "data_sources": dict(sources)}

total = sum(v["rows"] for v in stats.values())
manifest = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "date_window": {"start_inclusive": str(START), "end_inclusive": str(END),
                    "excluded_partial_date": "2026-07-12"},
    "source": {"repository": "NhanAZ-Data/vietlott-data-research", "commit": COMMIT},
    "row_count": total, "unique_key": ["product", "draw_id"], "duplicate_key_count": 0,
    "draw_status": dict(total_status), "validation_status": dict(total_validation),
    "products": stats, "raw_schema": RAW, "flat_schema": FLAT,
}
(META / "export_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
for name in ("dataset-summary.json", "quality-report.json", "snapshot-manifest.json"):
    src = SRC / "metadata" / name
    if src.exists(): shutil.copy2(src, META / f"source_{name}")
exclusions = SRC / "exclusions.csv"
if exclusions.exists(): shutil.copy2(exclusions, META / "source_exclusions.csv")

lines = ["# Bộ dữ liệu kết quả Vietlott 5 năm", "", f"- Khoảng ngày: **{START} đến {END}** (tính cả hai đầu).",
         f"- Snapshot nguồn: `{COMMIT}`.", f"- Tổng số kỳ: **{total:,}**.",
         "- Khóa `(product, draw_id)` đã được kiểm tra, không có bản ghi trùng.",
         "- Ngày 2026-07-12 bị loại vì snapshot trong ngày chưa hoàn tất.", "", "| product | số kỳ | ngày đầu | ngày cuối |", "|---|---:|---|---|"]
for p in PRODUCTS:
    s = stats[p]; lines.append(f"| {p} | {s['rows']:,} | {s['first_date']} | {s['last_date']} |")
lines += ["", "## Tệp chính", "", "- `raw/vietlott_draws_5y_raw.csv`: giữ nguyên JSON và trường nguồn.",
          "- `flat/vietlott_draws_5y_flat.csv`: bản phẳng cho Python/R/Excel.",
          "- `metadata/export_manifest.json`: thống kê và provenance.", "",
          "Dữ liệu lịch sử phục vụ nghiên cứu; không bảo đảm khả năng dự đoán kết quả tương lai."]
(ROOT / "README_VI.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

zip_path = OUT / f"{NAME}.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in sorted(ROOT.rglob("*")):
        if path.is_file(): zf.write(path, f"{NAME}/{path.relative_to(ROOT)}")
sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
(OUT / f"{NAME}.zip.sha256").write_text(f"{sha}  {zip_path.name}\n", encoding="utf-8")
(OUT / "export_summary.json").write_text(json.dumps({"zip": zip_path.name, "zip_sha256": sha,
    "zip_bytes": zip_path.stat().st_size, "row_count": total, "date_window": [str(START), str(END)],
    "products": stats}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False, indent=2))
print(f"ZIP={zip_path} bytes={zip_path.stat().st_size} sha256={sha}")
