"""OCR a plat/survey PDF page with EasyOCR + spatial reconstruction.

Extracts every text region with bounding boxes, then categorizes:
  - bearings (N/S dd[deg]mm'ss" E/W)
  - distances/footages (FNL/FSL/FEL/FWL or NNNN.NN')
  - lat/long / API / well name / operator headers

Also writes an annotated PNG and a JSON dump for inspection.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Bearing: N 89°42'15" E  (or with d/deg, ', ", spaces optional)
BEARING_RE = re.compile(
    r"""[NS]\s*\d{1,3}\s*[°dD\*]\s*\d{1,2}\s*['’]?\s*\d{1,2}(?:\.\d+)?\s*["”]?\s*[EW]""",
    re.X,
)
# Distance: 2640.18'  or  2640.18 ft  or  2640'
DISTANCE_RE = re.compile(r"\b\d{2,5}(?:\.\d{1,3})?\s*(?:['’]|ft|FT|feet|FEET)\b")
# Footage: 660 FNL  /  1980 FEL etc.
FOOTAGE_RE = re.compile(r"\b\d{2,5}\s*(?:'|’)?\s*F(NL|SL|EL|WL)\b", re.I)
# Lat/Long: 40°11'58.45"  -110°07'51.25"
LATLON_RE = re.compile(r"-?\d{1,3}\s*[°dD\*]\s*\d{1,2}\s*['’]\s*\d{1,2}(?:\.\d+)?\s*[\"”]?")
# Section number near a "Sec" label
SECTION_RE = re.compile(r"\bSec(?:tion)?\.?\s*(\d{1,2})\b", re.I)
# Township/Range/Meridian
TRM_RE = re.compile(r"\bT\s*\d{1,2}\s*[NSns]\s*,?\s*R\s*\d{1,2}\s*[EWew]\b")
# API number
API_RE = re.compile(r"\b4[34]-?\d{3}-?\d{5}\b")


def categorize(text: str) -> list[str]:
    cats = []
    if BEARING_RE.search(text):
        cats.append("bearing")
    if DISTANCE_RE.search(text):
        cats.append("distance")
    if FOOTAGE_RE.search(text):
        cats.append("footage")
    if LATLON_RE.search(text):
        cats.append("latlon")
    if SECTION_RE.search(text):
        cats.append("section")
    if TRM_RE.search(text):
        cats.append("trm")
    if API_RE.search(text):
        cats.append("api")
    return cats


def render_page(pdf: Path, page_num: int, dpi: int) -> tuple[np.ndarray, tuple[int, int]]:
    doc = fitz.open(pdf)
    if page_num < 1 or page_num > len(doc):
        raise SystemExit(f"page {page_num} out of range ({len(doc)} pages)")
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return img, (pix.width, pix.height)


def box_center(box) -> tuple[float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return sum(xs) / 4.0, sum(ys) / 4.0


def box_angle(box) -> float:
    """Approximate orientation in degrees (0 = horizontal). Uses top edge."""
    (x0, y0), (x1, y1) = box[0], box[1]
    return float(np.degrees(np.arctan2(y1 - y0, x1 - x0)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("page", type=int)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--gpu", action="store_true", default=True)
    ap.add_argument("--no-gpu", dest="gpu", action="store_false")
    ap.add_argument("--out-dir", type=Path, default=Path("tests"))
    args = ap.parse_args()

    print(f"Rendering {args.pdf.name} page {args.page} @ {args.dpi} dpi...")
    img, (w, h) = render_page(args.pdf, args.page, args.dpi)
    print(f"  image size: {w} x {h}")

    print("Loading EasyOCR (first run downloads models)...")
    t0 = time.time()
    import easyocr
    reader = easyocr.Reader(["en"], gpu=args.gpu, verbose=False)
    print(f"  loaded in {time.time()-t0:.1f}s   gpu={args.gpu}")

    print("Running OCR...")
    t0 = time.time()
    # detail=1 -> (bbox, text, confidence)
    results = reader.readtext(img, detail=1, paragraph=False)
    print(f"  ocr done in {time.time()-t0:.1f}s   regions={len(results)}")

    args.out_dir.mkdir(exist_ok=True)
    stem = f"{args.pdf.stem}_p{args.page}"

    # ---- Build structured record ----
    items = []
    for box, text, conf in results:
        cx, cy = box_center(box)
        ang = box_angle(box)
        items.append({
            "text": text,
            "conf": round(float(conf), 3),
            "cx": round(cx, 1),
            "cy": round(cy, 1),
            "angle_deg": round(ang, 1),
            "bbox": [[float(p[0]), float(p[1])] for p in box],
            "categories": categorize(text),
        })

    by_cat: dict[str, list[dict]] = {}
    for it in items:
        for c in it["categories"]:
            by_cat.setdefault(c, []).append(it)

    summary = {
        "pdf": str(args.pdf),
        "page": args.page,
        "image_size": [w, h],
        "region_count": len(items),
        "categorized_counts": {k: len(v) for k, v in by_cat.items()},
        "items": items,
    }
    json_path = args.out_dir / f"{stem}_ocr.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"  wrote {json_path}")

    # ---- Print human summary ----
    print()
    print("=" * 80)
    print("OCR SUMMARY")
    print("=" * 80)
    print(f"Total regions: {len(items)}")
    for k, v in by_cat.items():
        print(f"  {k}: {len(v)}")

    for cat in ("bearing", "footage", "distance", "latlon", "trm", "api", "section"):
        if cat not in by_cat:
            continue
        print(f"\n--- {cat.upper()} ({len(by_cat[cat])}) ---")
        for it in sorted(by_cat[cat], key=lambda x: (x["cy"], x["cx"])):
            print(f"  ({it['cx']:>6.0f},{it['cy']:>6.0f})  ang={it['angle_deg']:>5.1f}  "
                  f"conf={it['conf']:.2f}  {it['text']!r}")

    # ---- Annotated overlay ----
    pil = Image.fromarray(img).convert("RGB")
    draw = ImageDraw.Draw(pil)
    cat_color = {
        "bearing": (220, 30, 30),
        "footage": (30, 120, 220),
        "distance": (30, 170, 30),
        "latlon": (200, 120, 0),
        "trm": (160, 30, 200),
        "api": (200, 30, 200),
        "section": (0, 150, 150),
    }
    for it in items:
        cats = it["categories"]
        color = (140, 140, 140)
        for c in cats:
            if c in cat_color:
                color = cat_color[c]
                break
        pts = [(p[0], p[1]) for p in it["bbox"]]
        draw.polygon(pts, outline=color, width=2)
    overlay_path = args.out_dir / f"{stem}_ocr_overlay.png"
    pil.save(overlay_path)
    print(f"\nAnnotated overlay: {overlay_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
