"""Find plat/survey pages in an APD PDF using a local Ollama vision model."""
import argparse
import base64
import io
import json
import sys
import time
from pathlib import Path

import fitz
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5vl:7b"

PROMPT = (
    "You are looking at one page of an Application for Permit to Drill (APD) PDF. "
    "Does this page contain a SURVEYOR'S PLAT or SURVEY DIAGRAM showing a section/township "
    "layout with bearings (e.g. N 89 deg 42' 15\" E), distances/footages along section lines, "
    "and wellbore surface/bottom-hole location markers? "
    "Pure text pages, narrative descriptions, casing tables, logs, or maps without "
    "bearing/distance call-outs do NOT count.\n\n"
    "Respond with strict JSON only, no prose:\n"
    '{"is_plat": true|false, "confidence": 0.0-1.0, "reason": "<short>"}'
)


def render_page_png(page: fitz.Page, dpi: int = 150) -> bytes:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def ask_ollama(img_bytes: bytes, timeout: int = 180) -> dict:
    b64 = base64.b64encode(img_bytes).decode("ascii")
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "images": [b64],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    r.raise_for_status()
    raw = r.json().get("response", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"is_plat": None, "confidence": None, "reason": f"unparseable: {raw[:200]}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--max-pages", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    if not args.pdf.exists():
        print(f"not found: {args.pdf}", file=sys.stderr)
        return 2

    doc = fitz.open(args.pdf)
    n = len(doc) if args.max_pages == 0 else min(args.max_pages, len(doc))
    print(f"PDF: {args.pdf.name}  pages={len(doc)}  scanning={n}  model={MODEL}")
    print("-" * 80)

    hits = []
    t_total = time.time()
    for i in range(n):
        page = doc[i]
        img = render_page_png(page, dpi=args.dpi)
        t0 = time.time()
        try:
            res = ask_ollama(img)
        except Exception as e:
            print(f"p{i+1:>3}  ERROR  {e}")
            continue
        dt = time.time() - t0
        is_plat = res.get("is_plat")
        conf = res.get("confidence")
        reason = (res.get("reason") or "")[:90]
        flag = "**" if is_plat else "  "
        print(f"{flag} p{i+1:>3}  plat={str(is_plat):<5}  conf={conf}  ({dt:5.1f}s)  {reason}")
        if is_plat:
            hits.append(i + 1)

    print("-" * 80)
    print(f"total elapsed: {time.time()-t_total:.1f}s")
    print(f"plat pages: {hits if hits else 'NONE FOUND'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
