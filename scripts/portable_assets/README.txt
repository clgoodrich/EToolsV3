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
