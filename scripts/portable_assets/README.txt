==============================================================
 ETools - Portable Edition
 Directional survey, clearance, WCR & Casing Review tooling
==============================================================

WHAT THIS IS
------------
A fully self-contained copy of ETools. It includes its own Python
runtime, every library, the local AI engine (Ollama) and the AI model,
and the offline document models. Nothing needs to be installed on the
computer you run it on - no Python, no Ollama, no admin rights.

It is built for 64-bit Windows.


HOW TO RUN
----------
1. Double-click  ETools.bat
2. A console window opens and your default browser opens to
   http://localhost:8080/
3. Use the app in the browser. Keep the console window open.
4. To quit: close the console window, or double-click "Stop ETools.bat".

If the browser does not open on its own, open it yourself and go to:
   http://localhost:8080/


HOW TO MOVE IT TO ANOTHER COMPUTER
----------------------------------
Copy the ENTIRE "ETools_Portable" folder (about 12 GB) to the other
machine - an external/USB drive is easiest. Then double-click
ETools.bat there. That's it.

Copy the whole folder, not just some of it. The pieces depend on each
other and on their relative locations.


WHAT WORKS OFFLINE
------------------
Everything except the live SQL Server connection:

  - Survey processing, editing, KOP/landing detection
  - Clearances and PLSS section geometry
  - 2D map (streets + satellite imagery needs internet for tiles) and
    3D trajectory
  - WCR generation and Casing Review
  - PDF -> WCR auto-extraction (Docling + the local AI model)

The legacy "load a well straight from the State database" path needs a
reachable SQL Server (UTRBDMSNET); it will be unavailable on a machine
that has none. All the tools above work without it.


==============================================================
 HOW EVERYTHING WORKS
==============================================================

ETools is one browser page with a row of tabs across the top. Almost
every job starts on the LOAD WELL tab; loading a well fills in the
other tabs automatically. Whatever you load or edit is shared across
every tab, so a change in one place (a moved surface location, an
edited survey station, a casing override) recomputes everywhere -
the survey, the clearances, the map, and the generated workbooks.

TOP-OF-PAGE CONTROLS (always visible)
-------------------------------------
  - Well switcher (dropdown, top left) - if you have loaded more than
    one well, pick which one is active. Every tab reloads to it.
  - Clear all - wipes the current session (loaded well, parsed PDFs,
    surveys, and edits) and resets every tab to empty.

A phrase you will see a lot is "Use as active well" (also called
"promote"). It takes data parsed from a PDF and turns it into a real
loaded well: it builds the well header, cleans up the survey, then
runs the full pipeline - process survey, calculate clearances, build
the section geometry, refresh every tab. Promotion only fully
succeeds if the well can be placed on the map (from its PLSS section
or a surface location); if it cannot, upload a survey PDF or load the
well from the database.


1. LOAD WELL  (start here)
--------------------------
The single front door. Load a well one of three ways, then it routes
you to the right tab.

  A) From Database
     Type a 10-digit API and a 4-character Lateral (default 0000),
     click "Load Well". Pulls the survey straight from the State
     SQL Server. Needs a reachable database.

  B) From APD PDF
     Drag in a drilling-permit (APD) PDF. Pick a parse mode
     (Rules only / Rules + AI backfill / AI only), click "Parse APD".
     On success it jumps you to the CASING REVIEW tab and, when it
     can locate the well, promotes it automatically. It also tries to
     find a matching survey in the database and grabs the frac
     gradient if the permit lists one.

  C) From WCR PDF
     Drag in a DOGM Form 8 (Well Completion Report) PDF. Pick a
     parse mode and a scope:
        - First 5 pages   (just the Form 8 fields - fastest)
        - Whole PDF       (read fields off every page)
        - Whole PDF + Parse Operations (also has the AI write a
          plain-English operations summary - slow, minutes per job)
     Click "Parse WCR". On success it jumps you to the WCR tab and
     promotes the well.

  At the bottom is a well-summary card: name, operator, API/lateral,
  survey company/type, surface lat/lon, elevation, north reference,
  grid convergence and scale, UTM zone, PLSS location, and how many
  survey points were found.

  Parse modes that use "AI" need the local AI engine (Ollama)
  running - it is bundled, so it just works. If it is unavailable
  the parse quietly falls back to rules only.


2. SURVEY
---------
View and edit the directional survey. Requires a loaded well.

  - Citing dropdown: which survey (e.g. Planned / As-Drilled).
  - Frame toggle: True north vs Grid north.
  - "Process Survey": computes TVD, finds the kick-off point (KOP)
    and the landing point, and shows the detection method and
    confidence.

  Editing (every edit re-runs the whole pipeline downstream):
    - Double-click a grid cell (MD / inclination / azimuth) to edit.
    - "Interpolate + Add": type a depth, it inserts a station with
      interpolated inclination/azimuth.
    - "Reprocess with new SHL": type a new surface hole location
      (decimal lat/lon, degrees-minutes-seconds, or UTM 12N metres)
      to move the well and recompute.
    - "Apply convergence": override the grid-convergence angle.
    - "Delete selected station" / "Restore original survey".

  Only original survey stations can be edited or deleted;
  interpolated rows cannot.


3. CLEARANCE
------------
Computes the footages from the wellbore to each section boundary
(FNL/FSL/FEL/FWL - feet from the North/South/East/West line).
Requires a processed survey.

  - Pick the citing, click "Calculate Clearances".
  - Shows a summary grid for the key points (Surface, KOP, Landing,
    Bottom-hole) and a full grid of every survey point with MD,
    inclination, azimuth, TVD, its section, and the four footages.

  These clearances feed the Map and the WCR.


4. MAP & VIZ
------------
2D map, 3D wellbore, and section summary. Requires clearances first.

  Top bar: citing dropdown, True/Grid toggle, and setback checkboxes
  (100 / 330 / 500 ft) that draw dashed rings inset that far inside
  each section boundary.

  2D Map:
    - Section polygons, the well path (red), and station markers.
    - Streets vs Satellite basemap toggle.
    - Click anywhere to identify the nearest station (popup with
      MD/Inc/Azi/TVD, section, and footages), the nearest path point,
      or the section under the cursor.
    - "Add point": type a Lat/Lon or UTM plus a label to drop your
      own marker; remove them individually or "Clear points".

  3D Trajectory:
    - Rotatable 3D wellbore in North/East/Depth; hover any point for
      MD/Inc/Azi/TVD, coordinates, and (where lined up) the section
      and footages. Key stations are labeled.

  The map only re-centers when the active well changes - toggling
  layers or adding points will not throw away your pan/zoom.


5. WCR  (Well Completion Report)
--------------------------------
Generate the WCR Excel from a parsed Form 8 PDF plus a survey, review
the parsed data, and log your review to a personal tracker. You are
routed here after parsing a WCR PDF.

  Action bar:
    - Survey status pill: green if a survey was found (database or
      PDF), amber if not. When amber, an upload box appears - drop a
      survey PDF and it extracts the stations and surface location.
    - "Use as active well" to promote.
    - "Generate WCR Excel" - enabled once both the WCR data and a
      survey exist.

  Review panels:
    - Parsed WCR data: every extracted Form 8 field (dates,
      elevations, TD/PBTD, perforation stages, formation tops,
      surface location). Warns if the PDF is actually a different
      form.
    - Operation Summary Reports (from daily drilling reports):
      rules-flagged problems (stuck pipe, equipment failure...),
      the operations log as written, an AI narrative summary, and -
      if you chose "Parse Operations" at load - plain-English
      translations of each entry, plus a key-events table.

  After you Generate, an editable 15-column table of the location
  rows appears. MD, Easting, and Northing are editable; changing them
  recomputes TVD, footages, and PLSS labels automatically. "Save
  updated Excel" rewrites the file; "Open folder" / "Download" get
  you the file.

  Personal record (TrackingWCR.xlsx): tick what the submission
  included and what you edited, set a Returns count, and click
  "Update Personal Record" to log one row per API. If that workbook
  is open in Excel the update fails until you close it.


6. CASING REVIEW
----------------
Turns a parsed APD permit into an engineered Casing Review workbook
(design checks, BOPE, section sheets, wellbore diagram). You are
routed here after parsing an APD PDF.

  Action bar:
    - Survey status: green if a directional survey is loaded; amber
      warns that TVDs use a straight vertical-then-lateral fallback
      if no survey is present (an upload box lets you add one).
    - Frac gradient input (psi/ft, default 1.00) - editing it
      recomputes the design in place.
    - "Use as active well" to promote.
    - "Generate Excel" - writes the workbook (about 20 seconds).

  Sub-tabs:
    - Parsed APD: extracted permit fields, the Section 20 well
      locations, and the Hole/Casing/Cement table.
    - Casing inputs (editable): one row per string (including the
      conductor) - hole and casing size, set depth, weight, grade,
      collar, max mud weight, cement sacks and yields, plus washout %
      and internal gradient on engineered strings. Pre-filled with
      engine defaults; tab away to recompute.
    - BOPE (editable): per-string blowout-preventer inputs (previous
      shoe TVD, proposed BOPE pressure, operator's max anticipated
      pressure). Blank cells use the computed default shown as a
      placeholder; your edits are marked and cascade everywhere.
      Renders the full BOPE review table with adequacy checks and a
      "Print BOPE" button.
    - Computed design: the casing-design table with pass/fail against
      minimum design factors (collapse, burst, tension), loads,
      top-of-cement, and a check mark or warning per string.
    - Sections: one sub-tab per PLSS section the well crosses (the
      Surface section, then each Bottom-hole section). Each has a
      coordinate switcher (footages <-> lat/lon <-> UTM, all kept in
      sync), a north-reference toggle, the permit's locations, and a
      3x3 grid of editable boundary segments pre-filled from the Grid
      Numbers data. A center plat preview draws the walked section
      polygon, the segments, the well path, and a non-closure gap
      readout; zoom with the wheel, drag to pan, double-click to
      reset. Segment edits reshape the polygon on the Map tab too.
    - WBD: the vertical Wellbore Diagram with formation marks, and a
      "Print WBD" button.
    - Output: after Generate - Open folder / Download / saved path.


7. PLAT SEARCHER
----------------
A standalone PLSS section lookup - no well needs to be loaded.

  - By TRS: Section, Township (e.g. 2S), Range (e.g. 5W), and
    Meridian (Salt Lake / Uintah), then "Search".
  - By UTM: Easting and Northing metres, then "Search by UTM"
    (finds sections near that point).
  - Results in three sub-tabs: Sections (identity, centroid, acreage,
    vertex count), Adjacency (which sections touch which), and a
    Distance Checker (perpendicular distance from a point to a line
    segment, in feet and metres).

  Uses the plat / Grid Numbers data.


WHAT NEEDS WHAT (quick reference)
---------------------------------
  - State SQL Server database: loading a well by API, database survey
    lookups, WCR tracking sundries, and plat / grid-corner data.
  - Local AI engine (bundled): AI-backfill parse modes and the
    plain-English drilling-report summaries. Optional - parsing falls
    back to rules if it is off.
  - Generated Excel files land in app\output\ and can be opened or
    downloaded from the tab that made them.
  - One rule ties it together: editing the survey, the surface
    location, the casing inputs, the BOPE inputs, or a section
    segment recomputes everything downstream, live.


FIRST-RUN / SPEED NOTES
-----------------------
- The first PDF you parse loads the 6.6 GB AI model into memory and can
  take a minute or two. Later parses are faster.
- The model runs on the GPU if the machine has a recent NVIDIA card
  (CUDA runners are bundled); otherwise it runs on the CPU, which is
  noticeably slower (several minutes for a long PDF). This is normal.


FOLDER LAYOUT
-------------
  ETools.bat            <- start here
  Stop ETools.bat       <- stop the app + AI engine
  runtime\python\       <- bundled Python 3.12 (standalone)
  runtime\site-packages\<- all Python libraries
  app\                  <- the ETools program + data + .env config
  app\output\           <- generated WCRs / Casing Reviews / logs land here
  ollama\               <- bundled AI engine + the qwen3.5:9b model
  cache\hf\             <- offline document-AI models (Docling)


TROUBLESHOOTING
---------------
- Windows SmartScreen / antivirus may warn about ollama.exe or the
  Python runtime the first time. They are the stock, unmodified
  binaries; allow them to run.
- "Port already in use": something else is on :8080 or :11434. Run
  "Stop ETools.bat", then try again.
- To change the port, edit app\.env (ETOOLS_PORT=...).
- Logs are written to app\output\logs\etools.log.
