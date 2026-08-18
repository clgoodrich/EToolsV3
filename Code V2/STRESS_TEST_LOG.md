# ETools Stress Test Log
**Date:** 2026-07-07  
**Tester:** Claude (AI)  
**Model:** Sonnet 4.6 (1M context)  
**Server:** http://localhost:8080 (NiceGUI / Python 3.12)

---

## Test Environment

- ETools Portable running on Windows 11
- Server started via `ETools.bat` → port 8080
- Python runtime: `runtime\python\python.exe`
- Ollama: **not started** during tests (AI mode falls back to rules-only)
- Tests run by directly importing Python modules + HTTP requests

---

## BUGS FOUND

### BUG-01 — Silent NaN corruption in `grid_convergence`
**Severity:** HIGH  
**Location:** `app/etools/core/coordinates/converter.py:grid_convergence`

`grid_convergence(float('nan'), float('nan'))` returns `inf` instead of raising.  
If NaN coordinates flow from a failed parse, the convergence angle silently becomes `inf`.  
This corrupts every downstream calculation (azimuth correction, wellbore placement on map, clearances).

**Reproduction:**
```python
from etools.core.coordinates.converter import grid_convergence
result = grid_convergence(float('nan'), float('nan'))
# Returns: inf  (should raise ValueError)
```

---

### BUG-02 — NaN in survey data produces cryptic pyproj error
**Severity:** HIGH  
**Location:** `app/etools/core/survey/processor.py:process_survey`

NaN values in `Inclination` or `MeasuredDepth` columns propagate into the lat/lon reprojection and raise `OutOfRangeError: latitude out of range` from `pyproj`, with no indication that the input data contains NaN. A clear early validation step is missing.

**Reproduction:**
```python
import pandas as pd, numpy as np
df = pd.DataFrame({"MeasuredDepth":[0,100,np.nan,300], "Inclination":[0,0,np.nan,5], "Azimuth":[0,0,np.nan,90]})
process_survey(df, surface_lat=40.0, surface_lon=-109.5, ...)
# Raises: OutOfRangeError (from pyproj, not a clear validation error)
```

---

### BUG-03 — `proposed_bope_psi(NaN)` silently returns max rating
**Severity:** MEDIUM  
**Location:** `app/etools/core/casing_review/bope.py:proposed_bope_psi`

`proposed_bope_psi(float('nan'))` returns `15000` (the highest standard BOPE rating) because `nan > threshold` is always `False` — the comparison falls through all thresholds to the last-resort return. This is an incorrect BOPE recommendation from bad input.

**Reproduction:**
```python
from etools.core.casing_review.bope import proposed_bope_psi
result = proposed_bope_psi(float('nan'))
# Returns: 15000  (should return None)
```

---

### BUG-04 — `lookup_magnetic_field(NaN, NaN)` returns NaN silently
**Severity:** MEDIUM  
**Location:** `app/etools/core/survey/magnetic.py:lookup_magnetic_field`

Passing NaN lat/lon returns a result with `declination = nan`. This NaN propagates as the magnetic declination into `process_survey`, corrupting the computed azimuth for the entire well trajectory without any error.

**Reproduction:**
```python
from etools.core.survey.magnetic import lookup_magnetic_field
r = lookup_magnetic_field(float('nan'), float('nan'), altitude_m=0.0)
print(r.declination)  # nan
```

---

### BUG-05 — No validation on casing frac gradient (zero, negative, NaN, inf)
**Severity:** MEDIUM  
**Location:** `app/etools/services/casing_review_service.py:generate`

`CasingReviewService.generate()` accepts any value for `frac_gradient_override_psi_per_ft` without validation. Zero, negative, NaN, and `inf` all silently produce a `CasingReviewResult` with potentially nonsensical engineering outputs. A frac gradient of 0 would make all burst-load calculations collapse; `inf` would make every well fail the burst design factor check.

**Reproduction:**
```python
svc = CasingReviewService()
r = svc.generate(apd_data=apd_data, frac_gradient_override_psi_per_ft=float('nan'))
# Returns: CasingReviewResult — no error raised
```

---

### BUG-06 — Survey processor accepts arbitrarily large inclination/azimuth
**Severity:** MEDIUM  
**Location:** `app/etools/core/survey/processor.py:process_survey`

Inclination of 9,999,999 degrees and azimuth of 9,999,999 degrees are silently accepted and processed. The `welleng` library wraps/computes these without complaint. The resulting trajectory is meaningless but no error is raised, so downstream calculations (clearances, footages, map) receive garbage data.

**Reproduction:**
```python
df = pd.DataFrame({"MeasuredDepth":[0,1000,5000], "Inclination":[0,9999999,9999999], "Azimuth":[0,9999999,9999999]})
r = process_survey(df, ...)  # Runs without error, produces nonsensical trajectory
```

---

### BUG-07 — `annular_capacity_ft3_per_ft` returns negative value when OD > hole
**Severity:** LOW  
**Location:** `app/etools/core/casing_review/domain.py:CasingStringDesign.annular_capacity_ft3_per_ft`

When `od_in > hole_size_in` (physically impossible casing in a too-small hole), the annular capacity formula returns a negative number (`-0.34`). The property `cement_height_ft` guards against this (`if cap <= 0: return None`), but `annular_capacity_ft3_per_ft` itself returns the negative without raising, which could surprise callers that use it directly.

**Reproduction:**
```python
s = CasingStringDesign(hole_size_in=5.0, od_in=9.625, ...)
s.annular_capacity_ft3_per_ft  # Returns: -0.34
```

---

### BUG-08 — `dms_to_decimal` accepts 60 seconds (mathematically invalid)
**Severity:** LOW  
**Location:** `app/etools/core/coordinates/converter.py:dms_to_decimal`

`dms_to_decimal("40 30 60.0")` returns `40.5167°` instead of raising. 60 seconds equals 1 minute, so the result is off by a rounding inconsistency. Valid seconds range is [0, 60).

**Reproduction:**
```python
from etools.core.coordinates.converter import dms_to_decimal
dms_to_decimal("40 30 60.0")  # Returns 40.5166... instead of raising ValueError
```

---

## SILENT FAILURES (not errors per se, but may surprise users)

### SF-01 — `PlatRepository.fetch_for_point(NaN, NaN)` returns empty bundle silently
No exception is raised; the warning is only in the server log. A caller that doesn't check for empty sections may proceed as if the well has no PLSS location.

### SF-02 — `PlatRepository.fetch_for_point(inf, inf)` returns empty bundle silently
Same as SF-01.

### SF-03 — `PlatRepository.fetch_bbox(inverted_min, inverted_max)` returns empty bundle silently
Inverted bounding box (min > max) produces an empty result with only a server-side log warning.

### SF-04 — `displayed_to_native_azimuth(NaN)` returns NaN without raising
Propagates silently into the survey re-computation.

---

## PERFORMANCE FINDINGS

### PERF-01 — KOP detection is O(n²) on large surveys
**Impact:** Blocks UI thread for ~17 seconds on 10,001-point surveys

`detect_kop` runs `_kop_piecewise` which iterates over every possible split point (O(n²) piecewise linear regressions). A 10,001-point survey takes **16.6 seconds**.

A typical as-drilled survey has 100–300 points (< 0.5 s). Edge cases with high-frequency logging (every 10 ft over a 30,000 ft well) would trigger this; the app would appear frozen.

```
test: KOP detect on large survey (10001 pts) → time=16.603s
```

### PERF-02 — Casing Review Excel generation takes ~31 seconds
Each call to `CasingReviewService.generate()` writes an Excel workbook and takes **~31 seconds** per run. This is long for a user interaction; the UI shows a spinner but no progress indication.

### PERF-03 — Root page serves at ~0.5 requests/second
The NiceGUI root page takes ~2 seconds to render on each HTTP request (renders Leaflet map, Plotly 3D chart, all tabs). This is expected for a full-page WebSocket app but means:
- 20 concurrent connections would each wait in line
- Rapid browser refresh/reconnect loops take a long time to recover

---

## HAPPY-PATH RESULTS (all passed)

| Test | Result |
|------|--------|
| APD parse (rules-only) on 3 real APD PDFs | PASS |
| APD parse invalid mode string | Correct ValueError |
| APD parse non-existent file | Correct FileNotFoundError |
| APD parse empty file | Correct EmptyFileError |
| APD parse text-file-as-PDF | Correct FileDataError |
| APD parse file with space in name | PASS |
| Survey process normal 4-point well | PASS |
| Survey process pure vertical (all 0 inclination) | PASS |
| Survey process negative MDs | PASS |
| Survey process duplicate MDs (dedup) | PASS |
| Survey process inclination > 90 | PASS |
| Survey process azimuth > 360 | PASS |
| Survey process zero / negative elevation | PASS |
| Survey editor: insert station (interpolated) | PASS |
| Survey editor: insert station (explicit inc/azi) | PASS |
| Survey editor: delete existing station | PASS |
| Survey editor: update station inclination | PASS |
| Survey editor: NaN MD rejected | Correct ValueError |
| KOP detection on empty survey | Returns None (no crash) |
| KOP detection on all-vertical survey | Returns a KOP (piecewise finds optimum) |
| KOP detection with NaN in inclination | Returns best-guess KOP (NaN filtered by numpy) |
| Landing point: never reaches horizontal | Returns None (no crash) |
| Clearance calculation: normal well | PASS |
| Clearance calculation: pure vertical | PASS |
| Clearance calculation: 30,000 ft deep well | PASS (1.5 s) |
| Clearance calculation: near section boundary | PASS |
| Casing catalog: normal lookup N-80 | PASS |
| Casing catalog: SQL injection in grade | Returns None (no crash, no injection) |
| BOPE review: single string | PASS |
| BOPE review: empty design | PASS |
| CasingReviewService.generate: no args | Correct ValueError |
| CasingReviewService.generate: full real APD | PASS (31 s) |
| Grid convergence: normal | PASS |
| UTM conversion: normal | PASS |
| UTM conversion: invalid zone 99 | Correct OutOfRangeError |
| parse_coord_pair: normal lat/lon | PASS |
| parse_coord_pair: UTM metres | PASS |
| parse_coord_pair: None / empty / garbage | Correct ValueError |
| PlatRepository: fetch_for_point (Utah) | PASS |
| PlatRepository: fetch_bbox (normal) | PASS |
| locate_points: 3 points in Utah | PASS (all 3 matched) |
| locate_points: 5000 points (perf) | PASS (0.08 s) |
| Concurrent survey processing: 10x, 5 workers | PASS — thread-safe |
| HTTP: POST/DELETE to root | HTTP 405 (correct) |
| HTTP: Path traversal attempts | HTTP 404 (no disclosure) |
| HTTP: Huge query string (50 kB) | HTTP 200 (handled) |
| HTTP: 30 serial GET requests | 30/30 OK |

---

## APD vs EXISTING EXCEL COMPARISON (2026-07-07)

Three APD PDFs each had a corresponding existing Casing Review Excel (generated at an earlier date by a human reviewer). Generated fresh Excel files and compared cell-by-cell.

### Pairs compared:
1. `application_43013537270000.pdf` ↔ `Casing Review_43013537270000_Myton City UT 16-23 3-2-25-36-7H.xlsx`
2. `application_43013537010000 Check.pdf` ↔ `Casing Review_43013537010000_UT 16-9 3-2-16-21-1H.xlsx`
3. `application_13067.pdf` ↔ `Casing Review_43019500930000_Federal 1-15H-20-21.xlsx`

---

### BUG-09 — `_extract_frac_gradient` picks wrong column value (CRITICAL)
> ⚠️ **SUPERSEDED — see OPUS RE-VERIFICATION RV-1: this is a FALSE POSITIVE. Parser correctly extracts 14 ppg → 0.7273 psi/ft on the real files.**
**Severity:** CRITICAL  
**Location:** `app/etools/core/pdf/apd_parser.py:_extract_frac_gradient` (line 457–478)

The function uses `max(nums[:4])` to identify the frac gradient from the casing Safety Factors table. The PDF text is linearized by pdfplumber, so the first numbers appearing after the "Frac Grad @ Shoe" header are not always the frac gradient values — the casing **weight (ppf)** column often appears first.

**APD 13067 (Federal 1-15H-20-21):**
- First number after the header is `24` (surface casing weight, 24 ppf)
- Algorithm treats 24 as **ppg** and converts: 24 × 0.052 = **1.2468 psi/ft** (WRONG)
- Correct frac gradient: ~8.6 ppg × 0.052 = **0.447 psi/ft**
- Burst DF in generated file: inflated by factor of 2.8× — would hide a burst design failure

**APD 43013537270000 (Myton City):**
- Algorithm picks production shoe frac grad (14 ppg → 0.7273 psi/ft) which is consistent with the APD
- Existing Excel used a conservative 1.0 psi/ft override (user manually overrode)
- Burst loads are 27% lower in generated vs existing Excel: X12 GEN=1381.87, EXIST=1894.19 (27% diff)
- Burst DF Y12: GEN=2.547 vs EXIST=1.858 (37% diff) — same root cause

**Root cause:** The `max(nums[:4])` heuristic:
```python
# Line 469: extracts ALL numbers 0 < x ≤ 25 after the header
nums = [float(x) for x in re.findall(r"\b(\d+(?:\.\d+)?)\b", tail) if 0 < float(x) <= 25]
# Line 475: takes max of first 4
chosen = max(nums[:4]) if len(nums) >= 4 else nums[-1]
# Line 476-477: converts large numbers as ppg
if chosen > 5:
    chosen = round(chosen * 0.05194806, 4)
```
The casing weight column (e.g., 24 ppf, 36 ppf) is inside the ≤25 guard and appears before the frac gradient values in the linearized text. With `max()` it often wins.

**Fix needed:** Parse the frac gradient from its specific column position, or find and use only the per-interval "Frac" column (not weight), ideally matched with known column sequence in the table header.

---

### BUG-10 — DataPrint sheet missing header/company/well/API rows (regression vs v8.6)
**Severity:** MEDIUM  
**Location:** `app/etools/services/casing_review_service.py` (DataPrint sheet writer)

The existing Excel files (version 8.6) populate the DataPrint sheet's header rows with:
- Company name (rows 2, columns A, P, AE, AT)
- Well name (rows 3)
- API (rows 4)
- Design factors (row 5)
- Per-string computed data in rows 7, 15, 23 (one row per string starting at row 7)

The current code leaves these cells as None (not written) and instead starts string data at row 11 — 4 rows later than the existing format. This is a sheet layout regression that means the DataPrint printed output (which drives the formal printed casing review submission) is broken.

**Evidence:** `DataPrint: 269 differences` across all 3 pairs; A2, P2, AE2, AT2 all GEN=None, EXIST='NEWFIELD PRODUCTION COMPANY'.

---

### BUG-11 — Formations sheet layout mismatch vs v8.6
**Severity:** LOW  
**Location:** `app/etools/services/casing_review_service.py` (Formations sheet writer)

The existing Excel (v8.6) writes formation data to:
- Column A: sequential row numbers (0, 6, 11, 16, ...)
- Column H: formation names (Uinta, Green River, Garden Gulch, Uteland Butte)
- Column J: same sequential row numbers

The current code writes TVD depths to column C (rows 4–6) and does not write formation names to column H or row numbers to A/J. Formation names are entirely absent from generated files.

**Evidence:** `Formations: 36–39 differences` per pair; H3=Uinta, H4=Green River, H5=Garden Gulch, H6=Uteland Butte all GEN=None.

---

### BUG-12 — All existing Excel section sheets contain wrong well (template not cleared)
**Severity:** DATA MANAGEMENT (not a code bug)  
**Finding:** All three existing Excel files share the same "Butcher Butte 19-134H-22" (API 43013537460000) data in the SHL/BHL Section sheets. This means when the existing Excels were created, the section sheet template from a different well was never replaced with the correct well's data. Generated files correctly use the current well's data.

---

### BUG-13 — Casing string count mismatch: 4 strings in APD, 3 written to Excel (MEDIUM)
**Severity:** MEDIUM  
**Location:** `app/etools/services/casing_review_service.py`

APD parse log shows `casing=4` (4 strings: Conductor, Surface, Intermediate, Production). Generated Excel log shows `strings=3`. The 4th string (Production liner: 6" hole, 4.5" casing, 18592 ft MD, P-110 BTC) is present in the Casing Review sheet at row 42 (generated) but was at row 57 in the existing Excel's layout (v8.6).

The existing Excel has the 4th string in row 57 (GEN=None, EXIST has all values). The generated file wrote it at row 42 (GEN has values, EXIST has zeros). This means the template row placement for the 4th string has shifted: the generated 4th string at row 42 does not align with the existing file's row 57 position. In the existing file, row 42 is all zeros (empty string slot), and the values at row 57 came from the 4th string.

This is a sheet row-layout change between v8.6 and current. The conductor is apparently now included in the row count as a "string" slot, shifting positions.

---

### TVD DIFFERENCES (expected, not a bug)
All generated files used `had_welltrack=False` (no survey). Without a survey, TVDs use a "straight vertical then lateral" fallback approximation. The existing Excels were generated WITH a survey from the State database, giving accurate TVDs. This explains:
- B24 (intermediate set depth TVD): GEN=7650 (from APD), EXIST=8237.92 (from survey)
- Formation top TVDs differ by 7–16% across all strings

---

## SUMMARY

**CRITICAL — wrong engineering output, no error raised:**
- BUG-09: APD frac gradient parser picks casing weight column → burst loads off by up to 2.8×
- BUG-01: NaN grid convergence returns `inf` (silent corruption)
- BUG-03: NaN MASP returns wrong BOPE rating (15000)
- BUG-04: NaN magnetic declination propagates silently
- BUG-06: Extreme inclination/azimuth accepted, nonsensical trajectory produced

**MEDIUM — output regression vs v8.6:**
- BUG-10: DataPrint sheet missing header/company/well/API rows (layout shifted 4 rows)
- BUG-11: Formations sheet missing formation names in column H (regression)
- BUG-13: 4th casing string written at wrong row (v8.6 vs current layout shift)

**MEDIUM — error quality:**
- BUG-02: NaN in survey data → cryptic pyproj error instead of "survey contains NaN"
- BUG-05: Zero/negative/NaN/inf frac gradient accepted without validation

**LOW:**
- BUG-07: annular_capacity_ft3_per_ft returns negative when OD > hole
- BUG-08: dms_to_decimal accepts 60 seconds (off-by-rounding)

**DATA MANAGEMENT (not a code bug):**
- BUG-12: Existing Excel section sheets contain wrong well (template not cleared by users)

**PERFORMANCE:**
- PERF-01: KOP detection O(n²) — blocks UI ~17s on >10k-point surveys
- PERF-02: Excel generation ~31 seconds
- PERF-03: Page render ~2 seconds/request

**The core happy path is solid:** real APD PDFs parse correctly, surveys process correctly, clearances compute correctly, and the Excel output is generated. Thread safety is good. Error handling at system boundaries (missing files, wrong formats) is correct.

---

## WCR STRESS TEST (2026-07-07)

Script: `wcr_stress_test.py` — 4 sections, 233-line report at `wcr_stress_report.txt`

### Files tested:
- **46 WCR PDFs** (all in `WCR/` root folder) parsed with `mode="rules", skip_docling=True`
- **3 matched pairs** generated to WCR Excel and compared cell-by-cell vs existing Excel in `WCR/CG Files/`
- **LLM mode** tested with Ollama not running

---

### WCR-BUG-01 — No form-type validation: APD PDF silently accepted as WCR
**Severity:** MEDIUM  
**Location:** `app/etools/core/pdf/wcr_parser.py:parse_wcr_pdf`

Parsing an APD PDF as a WCR returns `api=None, well=None, casing=0, formations=0` with no error, no warning in `data.warnings`, and no indication of the wrong form type. Users who accidentally upload an APD file to the WCR workflow get a silently empty result.

**Evidence:**
```
PASS [APD file as WCR]: api=None well=None casing=0 formations=0 stages=0 positions=2 warnings=[]
```

**Fix needed:** Check for APD-specific header text (e.g., "Application for Permit to Drill") early in the parse and raise a descriptive error.

---

### WCR-BUG-02 — Template placeholder accepted as well name
**Severity:** LOW  
**Location:** `app/etools/core/pdf/wcr_parser.py`

A WCR template PDF (blank form with placeholder text) returns `well_name='Autofill from system data'` with no flags. If a user mistakenly uploads a blank template, the system will generate a WCR Excel titled "Autofill from system data."

**Evidence:**
```
PASS [Template PDF]: api=None well='Autofill from system data' casing=0 formations=0 stages=0
```

---

### WCR-BUG-03 — Perf stage parser extracts garbage data for WCR format variants (MEDIUM)
> ✅ **CONFIRMED — root cause found in OPUS RE-VERIFICATION RV-4 (Section 33 TVD columns mis-mapped into num_perfs/size_in; the garbage is NOT from DDR tables as originally guessed).**

**Severity:** MEDIUM  
**Location:** `app/etools/core/pdf/wcr_parser.py` (perf stage extraction)

For 20 out of 46 WCR PDFs, perf stage data is wildly out of range:
- `size_in` values ranging 7,000–10,000 inches (real perf sizes are 0.3–0.5 in)
- `num_perfs` values ranging 7,000–10,000 (real values are 10–200 per stage)

The parser is reading the wrong section of the PDF — likely extracting numeric values from the DDR (daily drilling report) event tables rather than the completion/perforation table. The pattern is consistent across all affected files (WCR 43013543xxx family and others).

**Representative samples:**
```
WCR 43013543050000.pdf: SUSPICIOUS PERF SIZE: 9595.0, SUSPICIOUS PERF COUNT: 9166
WCR 43013543060000.pdf: SUSPICIOUS PERF SIZE: 10037.0, SUSPICIOUS PERF COUNT: 9719
WCR 43047576330000.pdf: SUSPICIOUS PERF SIZE: 8565.0, SUSPICIOUS PERF COUNT: 6889
```
20/46 PDFs affected (43%).

---

### WCR-BUG-04 — Two WCR PDFs have total_md_ft = 2.0 ft (implausible)
**Severity:** MEDIUM  
**Location:** `app/etools/core/pdf/wcr_parser.py` (total MD extraction)

Two PDFs (`WCR 43013545420000.pdf`, `WCR 43013545560000.pdf`) return `md=2.0`. A real well total depth of 2 ft is not physically possible — the parser is picking up a 2-digit number from the wrong field (possibly a version number or form field number).

**Evidence:**
```
WCR 43013545420000.pdf: api=4301354542, well='Goose 52-2423-23E', md=2.0
WCR 43013545560000.pdf: api=4301354556, well='Goose 72-2423-23D', md=2.0
```

---

### WCR-BUG-05 — WCR API mismatch: filename vs parsed API for South Moon 5 wells
**Severity:** LOW (data cross-check finding)  
**Location:** `app/etools/core/pdf/wcr_parser.py` (API field extraction)

For `WCR 43013544520000.pdf` and `WCR 43013544530000.pdf`, the parsed API does not match the filename API:
- `WCR 43013544520000.pdf` → parses as `api=4301354452` (filename says ...520000)
- `WCR 43013544530000.pdf` → parses as `api=4301354453` (filename says ...530000)

This indicates two consecutive South Moon wells' WCR PDFs contain swapped API numbers, or the filenames are wrong. Either the PDFs were mislabeled or the API field was incorrectly transcribed.

---

### WCR-BUG-06 — WCR Excel layout schema change breaks comparison with older files
> ⚠️ **REFRAMED — see OPUS RE-VERIFICATION RV-3: largely a TEST ARTIFACT (compared clean output vs. raw-DB-export files). The remaining issue is a product decision about target format, not a defect.**

**Severity:** HIGH (data integrity)  
**Location:** `app/etools/core/wcr/__init__.py` or `generate_wcr_excel`

The WCR Excel generator produces a layout incompatible with files generated previously. Key differences:
- Row 4: GEN uses `'WellType'` label, EXIST uses `'ConstructKeyWellType'`
- All rows B4–B8 are shifted by one row relative to existing files
- GEN writes a header row at row 9 (MeasuredDepth, TVD, Easting, etc.) that EXIST does not have
- Location data rows start at row 10 in GEN vs row 9 in EXIST

Both Federal wells (43013540190000 and 43013540300000) show **100–101 differences** with this structural shift pattern. The South Moon well (43013539960000) shows only **44 differences** (mostly trajectory values from synthetic vs real survey, plus Perf Top/Bottom/Date columns now present in GEN but absent in older EXIST).

This is a **breaking schema change** — any tool or query that reads WCR Excels by row/column position will break across versions.

---

### WCR-BUG-07 — `surface_elevation_ft=0.0` is silently ignored
**Severity:** LOW  
**Location:** `app/etools/services/wcr_pdf_service.py:generate` (line 111)

```python
elev = surface_elevation_ft or pdf_data.elevation_ft
```

Python's `or` treats `0.0` as falsy, so passing `surface_elevation_ft=0.0` silently falls back to the PDF elevation. A surface elevation of exactly 0 ft (at sea level) cannot be explicitly set.

**Evidence:**
```
PASS [Zero elevation]: output=...WCR.xlsx (18.3s)
# Should use elev=0.0, actually uses pdf_data.elevation_ft=5742.0
```

---

### WCR-BUG-08 — `surface_lat=NaN` raises bare AssertionError with no message
**Severity:** LOW (error quality)  
**Location:** Somewhere in survey/coordinate pipeline

Passing `surface_lat=float('nan')` raises `AssertionError: latitude out of bounds` — a bare assertion with no actionable message. Should be a `ValueError("surface_lat is NaN — provide a valid latitude")`.

**Evidence:**
```
RAISE [NaN surface lat]: AssertionError: latitude out of bounds (0.00s)
```

---

### WCR-BUG-09 — Extreme lat/lon (91°) raises `ProjError` with no user-friendly message
**Severity:** LOW (error quality)  
**Location:** Survey/projection pipeline

Passing `surface_lat=91.0` raises `ProjError: proj error: Invalid coordinate: (Internal Proj Error: lcc: Invalid latitude)` — raw PROJ library error, not a validated user-facing error.

---

### WCR-BUG-10 — LLM mode (Ollama offline) silently returns empty parse, no fallback
**Severity:** MEDIUM  
**Location:** `app/etools/core/pdf/wcr_parser.py` (LLM branch)

When `mode="llm"` and Ollama is not running, the parser times out after ~10 seconds, then returns `api=None, well=None, casing=0` (all fields empty). The failure is logged to `data.warnings` but the return value is indistinguishable from "successfully parsed empty form." There is no automatic fallback to `mode="rules"`.

**Evidence:**
```
PASS [mode=llm (no ollama)]: api=None well=None casing=0 ...
  warnings=["LLM extraction failed: 1 validation error for LLMWCRExtraction\n
  Invalid JSON: EOF while parsing an object at line 1 column 1"]
```

The LLM also returns only `{` (incomplete JSON) after 10 seconds, suggesting Ollama was available but returned a partial response (possibly killed by OOM).

---

## WCR Parse Summary: 46 PDFs

| Category | Count |
|---|---|
| Fully parsed (OK) | 21 |
| Suspicious perf data | 20 |
| No API / well name (old form or blank) | 8 |
| md=2.0 (implausible) | 2 |
| Form-15 (old WCR format, not supported) | 5 |

---

## WCR Excel Generation Edge Cases (Section 4)

| Test | Result |
|---|---|
| No args (no pdf path or data) | RAISE ValueError (correct) |
| Empty survey DataFrame | RAISE ValueError: Cannot process an empty survey (correct) |
| NaN surface lat | RAISE AssertionError: latitude out of bounds |
| None surface lat (falls back to PDF UTM) | PASS — uses UTM from PDF |
| Extreme lat=91° | RAISE ProjError (no user-friendly message) |
| Survey with NaN rows | RAISE OutOfRangeError from pyproj |
| surface_elevation_ft=0.0 | PASS — but silently uses PDF elevation (BUG-07) |
| surface_elevation_ft=-500.0 | PASS — generates Excel with negative elevation |
| Normal run (baseline) | PASS — WCR Excel generated in ~17-18s |

---

## UPDATED SUMMARY

**CRITICAL:**
- BUG-09 (APD): Frac gradient parser picks casing weight column → burst loads off up to 2.8×
- BUG-01: NaN grid convergence → silent `inf` propagation

**HIGH:**
- WCR-BUG-06: WCR Excel schema change breaks row/column layout vs older files

**MEDIUM:**
- WCR-BUG-03: Perf stage parser extracts garbage data (43% of WCR PDFs affected)
- WCR-BUG-04: Two WCR PDFs return total_md=2.0 ft (implausible, wrong field extracted)
- WCR-BUG-10: LLM mode offline = empty parse, no rules fallback
- WCR-BUG-01: No form-type validation (APD accepted as WCR silently)
- BUG-02: NaN in survey → cryptic pyproj error
- BUG-05: Invalid frac gradient accepted without validation
- BUG-10 (APD): DataPrint sheet layout shifted 4 rows
- BUG-13 (APD): 4th casing string at wrong row position

**LOW:**
- WCR-BUG-02: Template placeholder treated as well name
- WCR-BUG-05: API mismatch between filename and parsed content
- WCR-BUG-07: `surface_elevation_ft=0.0` silently falls back to PDF elevation
- WCR-BUG-08: NaN lat raises bare AssertionError (no message)
- WCR-BUG-09: Extreme lat raises raw ProjError (no user-friendly message)
- BUG-07 (APD): annular_capacity returns negative when OD > hole
- BUG-08 (APD): dms_to_decimal accepts 60 seconds

---
---

# OPUS 4.8 RE-VERIFICATION PASS (2026-07-07)
**Model:** Opus 4.8  
**Ollama:** running (`qwen3.5:9b`) this pass — unlike the original Sonnet run  
**Method:** Every prior finding re-checked against the REAL ground-truth Excel
corpus rather than the earlier bug list — APD ground-truth in `APD/` (matched
`Casing Review_*.xlsx`), WCR ground-truth in `WCR/` + `WCR/CG Files/` (65 files).
Goal: separate genuine code defects from test-methodology artifacts. Two prior
findings did **not** survive scrutiny.

## RV-1 — BUG-09 (APD frac gradient) = ❌ FALSE POSITIVE (overturns CRITICAL)

The original claim (parser picks casing weight column, "off by up to 2.8×") does
**not reproduce** against the actual PDFs.

- Both matched APD PDFs literally print `Frac Grad @ Shoe = 14` (ppg) in the
  Safety Factors table. Raw fitz text window confirms `...Frac Grad @ Shoe \n 14 \n Burst 2.79...`.
- Parser correctly extracts 14 → `14 × 0.05194806 = 0.7273 psi/ft` — a normal frac gradient.
- The regex picks `max([14.0, 2.79, 3.3, 9.34]) = 14.0`. Casing weight (36/29 ppf)
  appears far later in the linearized text, OUTSIDE `nums[:4]`, so it never competes.
- Verified identical in `mode="rules"` and `mode="rules+llm"` → it's the rules
  regex producing the correct value, not an LLM rescue.

Residual note: `max(nums[:4])` (apd_parser.py ~475) is heuristic/fragile by
construction, but it yields the CORRECT value on every real file tested. Downgrade
from CRITICAL bug to "latent fragility, not manifest."

## RV-2 — APD frac gradient: program vs Excel assumption (REAL difference, NOT a bug)

Ground-truth Excel `A9 = "Frac Gradient | 1 | psi/ft"` and BOPE sheet notes read
literally *"Assumes 1psi/ft frac gradient."* So:
- Program uses the PDF's ACTUAL frac gradient (0.7273 psi/ft).
- Human workbook uses a conservative **1.0 psi/ft** assumption.
Downstream burst/BOPE max-pressure-at-shoe numbers therefore differ **by design**
(a modeling assumption), not because of a computation error. Program is more
data-faithful; Excel is more conservative. Decision for the user, not a fix.

## RV-3 — WCR-BUG-06 (schema shift) = ⚠️ REFRAMED, largely TEST ARTIFACT (was HIGH)

The corpus contains TWO different workbook families, not one format that changed:

| Family | Row 4 label | Headers | Count | What it is |
|---|---|---|---|---|
| Clean deliverable | `WellType` | TitleCase (`MeasuredDepth`,`TVD`) | ~2–3 (incl. South Moon) | What the generator targets & emits; label aligns with value (`WellType\|OW`) |
| Raw DB export | `ConstructKeyWellType` | lowercase (`measured_depth`,`tvd`) | 63/65 | Extra ConstructKey field; values shifted down 1 row (`SpudDate` cell holds `OW`, `0000` = API construct-key suffix) |

The original "100-cell schema shift" came from comparing the program's CLEAN output
against the **Federal raw-export files** (`CG Files/Federal_*_WCR.xlsx`) — an
apples-to-oranges reference. South Moon (same clean family as the generator's
target) matched far better (44 diffs), confirming the diff was reference-type
mismatch, not a program defect.

**Open product question (not a bug):** ~97% of the corpus is ConstructKey raw-export
style. Decide whether the generator should emit that format or the clean South-Moon
format it currently produces — depends on what the downstream consumer reads.

## RV-4 — WCR-BUG-03 (perf garbage) = ✅ CONFIRMED REAL + ROOT CAUSE FOUND

Confirmed: 29/63 root WCR PDFs collapse to ONE perf stage with impossible
`size_in ≈ 9595`, `num_perfs ≈ 9166`. Good path verified clean (South Moon: 43
stages, `size 0.4"`, `n 16–24`). Root cause is now pinned down — TWO compounding
causes:

**(a) `_STAGE_ROW_RE` is not anchored to the per-stage perf table.** The regex
(`wcr_parser.py:769`) is a free-floating `^ int  num  num  int  num` in MULTILINE
mode. Because PyMuPDF puts each cell on its own line and `\s+` spans newlines, it
matches the **Section 33 (COMPLETED and TESTED INTERVALS)** row and mis-maps columns:

```
33. COMPLETED and TESTED INTERVALS
FR | TOP(MD) | BOTTOM(MD) | TOP(TVD) | BOTTOM(TVD) | STIMULATION | STATUS
4  | 10213   | 20391      | 9166     | 9595        | Fracture Stimulated | PRODUCING
```

| Regex field | Grabs | Actually is |
|---|---|---|
| `stage` | 4 | FR (formation reference) |
| `top` | 10213 | ✓ perf top MD (correct) |
| `bot` | 20391 | ✓ perf bottom MD (correct) |
| `num_perfs` | 9166 | ✗ **TOP TVD** |
| `size_in` | 9595 | ✗ **BOTTOM TVD** |

So the intervals are actually right; only `num_perfs`/`size_in` are garbage — they
are the TVD columns. That is why every garbage value sits in the depth range and why
the two numbers track each other (near-constant lateral TVD; e.g. `43013544890000`:
n=8637, sz=8388).

**(b) The greedy match suppresses the correct fallback.** Pipeline order
(`wcr_parser.py:143-144`):
```
_extract_perf_stages(combined, data)          # greedy — grabs the S33 row as a fake stage
_extract_section_33_intervals(combined, data)  # CORRECT S33 parser, but…
```
`_extract_section_33_intervals` begins with `if data.perf_stages: return` (line 793).
Since step (a) already inserted one bogus stage, the dedicated Section-33 parser —
which reads top/bottom MD properly and sets `num_perfs=None, size_in=None` — never
runs. The wrong parser pre-empts the right one.

**Why only these files:** they report ONLY the Section 33 summary interval (no
per-stage perf table). Wells that include the real per-stage table parse correctly.
The separate `nperf=0` misses (Federal 4019/4030 — real perfs 3298–3697 ft exist in
ground truth) are a DIFFERENT failure: their S33 layout matches neither regex.

**Missing guard:** the sanity check validates only the two depth columns
(`top<bot`, both >1000). No plausibility bound on `num_perfs` (<~500 real) or
`size_in` (<~1 in real), so TVDs pass as a shot count and a hole diameter.

**Fix direction (NOT executed, per instruction):** anchor `_STAGE_ROW_RE` to the
per-stage table header; and/or add plausibility bounds on perfs/size; and/or reorder
so Section-33 parsing wins when only the summary interval is present.

## RV-5 — WCR-BUG-04 (TD) = ✅ CONFIRMED (minor)

2 files return `total_md_ft = 2.0` (43013545420000, 43013545560000); 7 files return
`TD = None`. Unchanged from original finding.

## Revised verdict table

| Prior finding | Original severity | Opus verdict |
|---|---|---|
| BUG-09 APD frac gradient | CRITICAL | **False positive** — extraction correct (14 ppg → 0.7273 psi/ft) |
| WCR-BUG-06 schema shift | HIGH | **Largely test artifact** (wrong reference family); real open format question |
| WCR-BUG-03 perf garbage | MEDIUM | **Confirmed real** — S33 TVD cols mis-mapped into num_perfs/size_in; root cause found |
| WCR-BUG-04 TD=2.0/None | MEDIUM | **Confirmed** (minor) |
| APD frac 1.0 vs 0.7273 psi/ft | (new) | **Not a bug** — conservative assumption difference |

Net: the two headline defects from the original run (one CRITICAL, one HIGH) were
methodology artifacts. The genuinely real WCR defect is the perf-table parser
(RV-4), now root-caused.
