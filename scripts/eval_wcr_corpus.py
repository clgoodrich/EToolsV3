"""Run parse_wcr_pdf across every WCR PDF in tests/ and report metrics.

Usage:
    .venv/Scripts/python scripts/eval_wcr_corpus.py [--mode rules|rules+llm] [--all-pages]

Output:
    A CSV (corpus_eval.csv) with one row per PDF, plus a stdout summary
    showing per-field success rates and the worst-performing PDFs.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from etools.core.pdf.wcr_parser import parse_wcr_pdf  # noqa: E402


CRITICAL_FIELDS = (
    "well_name",
    "api",
    "operator",
    "elevation_ft",
    "total_md_ft",
    "spud_date",
    "completion_date",
)


def evaluate(path: Path, *, mode: str, max_pages: int | None, skip_docling: bool) -> dict:
    row: dict = {
        "path": path.name,
        "ok": False,
        "error": "",
        "elapsed_s": 0.0,
    }
    started = time.time()
    try:
        data = parse_wcr_pdf(
            path,
            mode=mode,
            max_pages=max_pages,
            use_llm=(mode != "rules"),
            skip_docling=skip_docling,
        )
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:200]
        row["elapsed_s"] = round(time.time() - started, 1)
        return row

    row["elapsed_s"] = round(time.time() - started, 1)
    row["ok"] = True
    row["well_name"] = data.well_name or ""
    row["api"] = data.api or ""
    row["operator"] = (data.operator or "")[:60]
    row["elevation_ft"] = data.elevation_ft or ""
    row["total_md_ft"] = data.total_md_ft or ""
    row["pbtd_md_ft"] = data.pbtd_md_ft or ""
    row["spud_date"] = data.spud_date or ""
    row["completion_date"] = data.completion_date or ""
    row["n_positions"] = len(data.positions)
    row["n_casing"] = len(data.casing)
    row["n_formations"] = len(data.formations)
    row["n_perf_stages"] = len(data.perf_stages)
    row["n_ddrs"] = len(data.ddrs)
    row["n_ddr_events"] = sum(len(d.key_events) for d in data.ddrs)
    row["missing"] = ",".join(
        f for f in CRITICAL_FIELDS if not getattr(data, f)
    )
    row["missing_count"] = len(row["missing"].split(",")) if row["missing"] else 0
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="rules", choices=["rules", "rules+llm", "llm"])
    ap.add_argument("--all-pages", action="store_true", help="Run on every page (default: first 5)")
    ap.add_argument(
        "--no-docling",
        action="store_true",
        help="Skip Docling (PyMuPDF text only). Much faster, slightly less accurate.",
    )
    ap.add_argument("--out", default=str(REPO / "output" / "corpus_eval.csv"), help="Output CSV")
    args = ap.parse_args()
    max_pages = None if args.all_pages else 5

    wcr_dir = REPO / "tests" / "fixtures" / "wcr"
    pdfs = sorted(p for p in wcr_dir.glob("*.pdf") if p.name.lower().startswith("wcr"))
    print(f"Evaluating {len(pdfs)} PDFs (mode={args.mode}, max_pages={max_pages or 'all'})…")

    rows: list[dict] = []
    for i, p in enumerate(pdfs, 1):
        print(f"  [{i:>2}/{len(pdfs)}] {p.name} … ", end="", flush=True)
        row = evaluate(
            p, mode=args.mode, max_pages=max_pages, skip_docling=args.no_docling
        )
        rows.append(row)
        if row["error"]:
            print(f"FAILED — {row['error']}")
        else:
            miss = row["missing_count"]
            print(
                f"{row['elapsed_s']:>5.1f}s  miss={miss}  "
                f"stages={row['n_perf_stages']}  ddrs={row['n_ddrs']}  "
                f"ddr_events={row['n_ddr_events']}  api={row['api'] or '—'}"
            )

    # Write CSV
    out_path = REPO / args.out
    if rows:
        fieldnames = sorted({k for r in rows for k in r.keys()})
        with out_path.open("w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow(r)
    print(f"\nWrote {out_path}")

    # Summary
    n = len(rows)
    ok = sum(1 for r in rows if r["ok"])
    print(f"\nSummary: {ok}/{n} parsed without errors")
    print("Per-field success rate:")
    for f in CRITICAL_FIELDS + ("n_positions", "n_perf_stages", "n_ddrs"):
        if f.startswith("n_"):
            present = sum(1 for r in rows if r.get(f, 0) and int(r[f]) > 0)
        else:
            present = sum(1 for r in rows if r.get(f))
        print(f"  {f:<20}  {present:>3}/{n}  ({present / max(n, 1) * 100:>3.0f}%)")

    # Worst offenders
    print("\nWorst PDFs (most missing critical fields):")
    worst = sorted(
        (r for r in rows if r["ok"]),
        key=lambda r: r.get("missing_count", 0),
        reverse=True,
    )[:8]
    for r in worst:
        print(f"  {r['path']}: miss={r['missing']}")
    failed = [r for r in rows if not r["ok"]]
    if failed:
        print(f"\nParser raised on {len(failed)} PDFs:")
        for r in failed:
            print(f"  {r['path']}: {r['error']}")


if __name__ == "__main__":
    main()
