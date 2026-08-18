"""Independent sniff-test of the APD frac-gradient extraction (BUG-09)."""
import sys, re, pathlib
sys.path.insert(0, r"C:\ETools_Portable\app")
from etools.core.pdf.apd_parser import parse_apd_pdf, _extract_text, _extract_frac_gradient
from etools.models import APDPdfData
import openpyxl

PAIRS = [
    (r"C:\ETools_Portable\APD\application_43013537270000.pdf",
     r"C:\ETools_Portable\APD\Casing Review_43013537270000_Myton City UT 16-23 3-2-25-36-7H.xlsx"),
    (r"C:\ETools_Portable\APD\application_43013537010000 Check.pdf",
     r"C:\ETools_Portable\APD\Casing Review_43013537010000_UT 16-9 3-2-16-21-1H.xlsx"),
]

def find_frac_in_excel(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    hits = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and "frac" in c.value.lower():
                    rowvals = [cc.value for cc in row if cc.value not in (None, "")]
                    # also grab the cell to the right and below for the value
                    hits.append((ws.title, c.coordinate, c.value, rowvals))
    return hits

for pdf, xlsx in PAIRS:
    print("=" * 80)
    print("PDF :", pathlib.Path(pdf).name)
    p = pathlib.Path(pdf)
    if not p.exists():
        print("  !! PDF missing"); continue

    # rules-only, isolate the regex
    d_rules = parse_apd_pdf(pdf, mode="rules")
    print("  [rules-only]    frac =", getattr(d_rules, "frac_gradient_psi_per_ft", None))
    # rules+llm (default)
    d_full = parse_apd_pdf(pdf, mode="rules+llm")
    print("  [rules+llm]     frac =", getattr(d_full, "frac_gradient_psi_per_ft", None))

    # raw regex on a fresh object to see exactly what it picks
    txt = _extract_text(p)
    m = re.search(r"Frac\s*\n?\s*Grad[^\n]*\n?\s*@?\s*Shoe[^\n]*\n", txt, re.I)
    if m:
        tail = txt[m.end(): m.end()+400]
        nums = [float(x) for x in re.findall(r"\b(\d+(?:\.\d+)?)\b", tail) if 0 < float(x) <= 25]
        print("  label found. nums<=25 after label:", nums[:12])
        print("    max(nums[:4]) =", max(nums[:4]) if len(nums)>=4 else "n/a", " nums[-1] =", nums[-1] if nums else "n/a")
        print("  --- fitz text window around Frac Grad ---")
        print(txt[max(0,m.start()-60): m.end()+300])
        print("  --- end ---")
    else:
        print("  !! 'Frac Grad @ Shoe' pattern NOT found in fitz text")
        # broader search
        m2 = re.search(r"Frac", txt, re.I)
        if m2:
            print("  ...but 'Frac' appears; context:")
            print(txt[max(0,m2.start()-40): m2.end()+200])

    if pathlib.Path(xlsx).exists():
        print("  --- GROUND-TRUTH Excel 'frac' cells ---")
        for sheet, coord, label, rowvals in find_frac_in_excel(xlsx):
            print(f"    [{sheet}]{coord} {label!r} -> {rowvals}")
    print()
