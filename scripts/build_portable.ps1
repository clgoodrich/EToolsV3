<#
.SYNOPSIS
  Build a self-contained, drag-and-drop ETools folder for 64-bit Windows.
  The result needs no Python, no Ollama, and no admin rights on the target.

.DESCRIPTION
  Assembles, from this dev machine:
    runtime\python\        embeddable CPython (standalone interpreter)
    runtime\site-packages\ every dependency, vendored from the dev .venv
    app\                   the etools source + plats DB + .env
    cache\hf\              Docling document-AI models (for offline PDF parsing)
    ollama\                ollama.exe + CPU/CUDA runners + the chosen LLM model
    ETools.bat             launcher (starts Ollama + the app, opens the browser)

  The big LLM model blob is hard-linked when the bundle is on the same volume
  as the Ollama store (zero extra disk); a plain copy is used otherwise. Either
  way, copying the finished folder to another drive/PC materializes a real file.

.NOTES
  Run from the repo root with the dev .venv already populated (it is the source
  of truth for the vendored libraries, including docling/torch which are not in
  pyproject.toml). Re-run any time to refresh code or swap the model.
#>
[CmdletBinding()]
param(
  [string]$Bundle   = "C:\Users\colto\Documents\ETools_Portable",
  [string]$Repo     = "C:\Users\colto\Documents\GitHub\EToolsV3",
  [string]$PyVersion= "3.12.4",          # must match the dev venv's 3.12.x minor
  [string]$Model    = "qwen3.5:9b",
  [switch]$IncludeCuda = $true,          # keep cuda_v12 runner (NVIDIA speedup)
  [switch]$Clean       = $true
)
$ErrorActionPreference = "Stop"
function Robo($s,$d,$xd){ robocopy $s $d /E /XD $xd __pycache__ /XF *.pyc /MT:16 /NFL /NDL /NJH /NJS /NP | Out-Null; if($LASTEXITCODE -ge 8){ throw "robocopy failed ($s -> $d): $LASTEXITCODE" } }

$venvSP   = "$Repo\.venv\Lib\site-packages"
$hfHub    = "$env:USERPROFILE\.cache\huggingface\hub"
$ollProg  = "$env:LOCALAPPDATA\Programs\Ollama"
$ollStore = "$env:USERPROFILE\.ollama\models"

if($Clean -and (Test-Path $Bundle)){ Write-Host "Removing existing $Bundle"; Remove-Item $Bundle -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$Bundle\runtime\site-packages","$Bundle\app","$Bundle\ollama\models\blobs","$Bundle\cache\hf\hub" | Out-Null

# --- 1. Embeddable Python ------------------------------------------------
Write-Host "[1/6] Embeddable Python $PyVersion"
$zip = "$Bundle\runtime\pyembed.zip"
Invoke-WebRequest -UseBasicParsing "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath "$Bundle\runtime\python" -Force
Remove-Item $zip
# Enable site + put vendored libs and the app on the path. Paths are relative
# to the python.exe directory (runtime\python).
$tag = "python" + ($PyVersion.Split('.')[0]) + ($PyVersion.Split('.')[1])   # e.g. python312
@("$tag.zip",".","..\site-packages","..\..\app","","# Enable .pth processing (pywin32 etc.)","import site") |
  Set-Content "$Bundle\runtime\python\$tag._pth" -Encoding ASCII

# --- 2. Vendored dependencies -------------------------------------------
Write-Host "[2/6] Vendoring site-packages (excludes legacy PyQt5)"
Robo $venvSP "$Bundle\runtime\site-packages" @("PyQt5","PyQt5_sip")

# --- 3. App source + data + config --------------------------------------
Write-Host "[3/6] App source + plats DB + .env"
Robo "$Repo\etools" "$Bundle\app\etools" @(".pytest_cache")
Copy-Item "$Repo\data\Board_DB_Plss_Sections.db" "$Bundle\app\data\" -Force  # location_data.db is unused -> skipped
Set-Content "$Bundle\app\.env" @"
ETOOLS_LLM__ENABLED=true
ETOOLS_LLM__BASE_URL=http://localhost:11434
ETOOLS_LLM__MODEL=$Model
ETOOLS_DB__SERVER=localhost\SQLEXPRESS
ETOOLS_DB__DATABASE=UTRBDMSNET
ETOOLS_DB__TRUSTED=true
ETOOLS_PORT=8080
ETOOLS_LOG_LEVEL=INFO
"@ -Encoding ASCII

# --- 4. Docling models (offline) ----------------------------------------
Write-Host "[4/6] Docling models"
foreach($m in @("models--docling-project--docling-layout-heron","models--docling-project--docling-models")){
  if(Test-Path "$hfHub\$m"){ Robo "$hfHub\$m" "$Bundle\cache\hf\hub\$m" @() } else { Write-Warning "missing $m - run a PDF through Docling once to populate the cache" }
}

# --- 5. Ollama engine + model -------------------------------------------
Write-Host "[5/6] Ollama engine + model '$Model'"
Copy-Item "$ollProg\ollama.exe" "$Bundle\ollama\" -Force
$dropGpu = @("rocm_v7_1","cuda_v13","vulkan"); if(-not $IncludeCuda){ $dropGpu += "cuda_v12" }
Robo "$ollProg\lib\ollama" "$Bundle\ollama\lib\ollama" $dropGpu
# Parse the model manifest for its blob digests (robust to model changes).
$name,$tagName = $Model.Split(':'); if(-not $tagName){ $tagName = "latest" }
$manSrc = "$ollStore\manifests\registry.ollama.ai\library\$name\$tagName"
$manDst = "$Bundle\ollama\models\manifests\registry.ollama.ai\library\$name"
New-Item -ItemType Directory -Force -Path $manDst | Out-Null
Copy-Item $manSrc "$manDst\" -Force
$man = Get-Content $manSrc -Raw | ConvertFrom-Json
$digests = @($man.config.digest) + ($man.layers | ForEach-Object { $_.digest })
foreach($d in $digests){
  $blob = "sha256-" + $d.Split(':')[1]
  $src = "$ollStore\blobs\$blob"; $dst = "$Bundle\ollama\models\blobs\$blob"
  $sameVol = ([IO.Path]::GetPathRoot($src) -eq [IO.Path]::GetPathRoot($dst))
  if($sameVol){ New-Item -ItemType HardLink -Path $dst -Target $src | Out-Null }  # zero extra disk
  else        { Copy-Item $src $dst -Force }
}

# --- 6. Launcher + docs --------------------------------------------------
Write-Host "[6/6] Launcher + README"
Copy-Item "$Repo\scripts\portable_assets\ETools.bat"      "$Bundle\" -Force -ErrorAction SilentlyContinue
Copy-Item "$Repo\scripts\portable_assets\Stop ETools.bat" "$Bundle\" -Force -ErrorAction SilentlyContinue
Copy-Item "$Repo\scripts\portable_assets\README.txt"      "$Bundle\" -Force -ErrorAction SilentlyContinue

$gb = [math]::Round((Get-ChildItem -Recurse $Bundle -File | Measure-Object Length -Sum).Sum/1GB,1)
Write-Host "`nDone. Bundle at $Bundle  (~$gb GB apparent). Double-click ETools.bat to run." -ForegroundColor Green
