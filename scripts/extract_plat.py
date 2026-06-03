"""Extract plat/survey data from a single PDF page using qwen2.5vl."""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

import fitz
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5vl:7b"

PROMPT = """You are reading a SURVEYOR'S PLAT page from an Application for Permit to Drill (APD).

Extract every piece of structured data you can see. Be exhaustive and literal — transcribe
exactly what is shown, do not paraphrase or convert units. If a value is unreadable, write "?".

Return strict JSON with this schema (omit keys that are not present on the page):

{
  "well_name": "<string>",
  "operator": "<string>",
  "api_number": "<string>",
  "location": {
    "section": "<int>",
    "township": "<string, e.g. 3S>",
    "range": "<string, e.g. 2W>",
    "meridian": "<string, e.g. USM/SLBM>",
    "county": "<string>",
    "state": "<string>"
  },
  "surface_hole_location": {
    "ns_footage": "<e.g. 660 FNL>",
    "ew_footage": "<e.g. 1980 FEL>",
    "latitude": "<string>",
    "longitude": "<string>",
    "elevation": "<string>"
  },
  "bottom_hole_location": {
    "ns_footage": "<...>",
    "ew_footage": "<...>",
    "latitude": "<...>",
    "longitude": "<...>"
  },
  "section_lines": [
    {
      "label": "<e.g. North line of Sec 23>",
      "bearing": "<e.g. N 89°42'15\\" E>",
      "distance": "<e.g. 2640.18 ft>"
    }
  ],
  "wellbore_segments": [
    {
      "from": "<KOP / SHL / etc.>",
      "to": "<PPP / LTP / BHL / etc.>",
      "bearing": "<...>",
      "distance": "<...>"
    }
  ],
  "surveyor": {
    "company": "<string>",
    "name": "<string>",
    "license": "<string>",
    "date": "<string>"
  },
  "other_text": "<anything notable not captured above>"
}

Return ONLY the JSON. No commentary."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("page", type=int, help="1-based page number")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--num-gpu", type=int, default=20)
    ap.add_argument("--save-image", type=Path, default=None)
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    if args.page < 1 or args.page > len(doc):
        print(f"page {args.page} out of range (PDF has {len(doc)} pages)", file=sys.stderr)
        return 2

    page = doc[args.page - 1]
    mat = fitz.Matrix(args.dpi / 72, args.dpi / 72)
    img = page.get_pixmap(matrix=mat, alpha=False).tobytes("png")
    print(f"PDF: {args.pdf.name}  page={args.page}/{len(doc)}  dpi={args.dpi}  img_bytes={len(img):,}")

    if args.save_image:
        args.save_image.write_bytes(img)
        print(f"saved image: {args.save_image}")

    b64 = base64.b64encode(img).decode("ascii")
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "images": [b64],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_gpu": args.num_gpu, "num_ctx": 4096},
    }

    print(f"sending to {MODEL} (num_gpu={args.num_gpu})...")
    t0 = time.time()
    r = requests.post(OLLAMA_URL, json=payload, timeout=1800)
    dt = time.time() - t0
    r.raise_for_status()
    d = r.json()

    print(f"elapsed: {dt:.1f}s   eval_count: {d.get('eval_count')}   "
          f"prompt_eval_s: {d.get('prompt_eval_duration',0)/1e9:.1f}   "
          f"eval_s: {d.get('eval_duration',0)/1e9:.1f}")
    print("-" * 80)
    raw = d.get("response", "")
    try:
        parsed = json.loads(raw)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print("(unparseable JSON — raw response below)")
        print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
