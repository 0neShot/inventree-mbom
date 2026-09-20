# sync-mbom-static.ps1
# Synchronizes mBOM static assets and package files between:
# 1. External git repo (..\inventree-mbom if present)
# 2. Container package (data\packages\inventree-mbom)
# 3. Django collected static dirs (data\static\plugins\... and data\static\inventree_mbom\...)
#
# IMPORTANT: It also restarts 'inventree-server' so Whitenoise / Gunicorn
# updates its in-memory file size cache (preventing truncated JS / SyntaxErrors).
#
# Usage:
#   .\sync-mbom-static.ps1 [-NoRestart]

param(
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$parentDir = Split-Path $PSScriptRoot -Parent
if (Test-Path (Join-Path $PSScriptRoot "data\packages\inventree-mbom")) {
    # Run from InventreePlugin
    $workspaceRoot = $PSScriptRoot
    $externalRepo  = Join-Path $parentDir "inventree-mbom"
} elseif (Test-Path (Join-Path $parentDir "InventreePlugin\data\packages\inventree-mbom")) {
    # Run from inventree-mbom
    $workspaceRoot = Join-Path $parentDir "InventreePlugin"
    $externalRepo  = $PSScriptRoot
} else {
    $workspaceRoot = $PSScriptRoot
    $externalRepo  = Join-Path $parentDir "inventree-mbom"
}

$dataPkg    = Join-Path $workspaceRoot "data\packages\inventree-mbom"
$staticRoot = Join-Path $workspaceRoot "data\static"

Write-Host "=== SmartParts & mBOM Static Sync Utility ===" -ForegroundColor Cyan

# 1. Sync between external repo and data\packages if external repo exists
if (Test-Path $externalRepo) {
    Write-Host "[1/3] Synchronizing external repo ($externalRepo) <-> data\packages..." -ForegroundColor Yellow
    
    $extMbom = Join-Path $externalRepo "inventree_mbom"
    $pkgMbom = Join-Path $dataPkg "inventree_mbom"
    $excludeRegex = '(\\__pycache__|\\\.git|\.pyc$|\.pyo$)'

    function Sync-BidirectionalTree($srcDir, $dstDir, $srcLabel, $dstLabel) {
        if (-not (Test-Path $srcDir) -or -not (Test-Path $dstDir)) { return }
        
        Get-ChildItem -Path $srcDir -Recurse -File | Where-Object { $_.FullName -notmatch $excludeRegex } | ForEach-Object {
            $rel = $_.FullName.Substring($srcDir.Length)
            $target = Join-Path $dstDir $rel
            if (-not (Test-Path $target) -or ($_.LastWriteTime -gt (Get-Item $target).LastWriteTime)) {
                $parent = Split-Path $target -Parent
                if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force $parent | Out-Null }
                Copy-Item -Force $_.FullName $target
                Write-Host "  $srcLabel -> $dstLabel : $rel" -ForegroundColor Green
            }
        }
    }

    if ((Test-Path $extMbom) -and (Test-Path $pkgMbom)) {
        Sync-BidirectionalTree $extMbom $pkgMbom "Repo" "DataPkg"
        Sync-BidirectionalTree $pkgMbom $extMbom "DataPkg" "Repo"
    }

    # Also sync root package files (setup.py, pyproject.toml, README.md, MANIFEST.in)
    foreach ($file in @("setup.py", "pyproject.toml", "README.md", "MANIFEST.in")) {
        $extF = Join-Path $externalRepo $file
        $pkgF = Join-Path $dataPkg $file
        if ((Test-Path $extF) -and (Test-Path $pkgF)) {
            if ((Get-Item $extF).LastWriteTime -gt (Get-Item $pkgF).LastWriteTime) {
                Copy-Item -Force $extF $pkgF
                Write-Host "  Repo -> DataPkg : $file" -ForegroundColor Green
            } elseif ((Get-Item $pkgF).LastWriteTime -gt (Get-Item $extF).LastWriteTime) {
                Copy-Item -Force $pkgF $extF
                Write-Host "  DataPkg -> Repo : $file" -ForegroundColor Green
            }
        }
    }
}

# 2. Deploy static files into InvenTree static directories
Write-Host "[2/3] Deploying static files to Django static directories..." -ForegroundColor Yellow
$pkgStaticDir = Join-Path $dataPkg "inventree_mbom\static\inventree_mbom"

if (Test-Path $pkgStaticDir) {
    $targets = @(
        (Join-Path $staticRoot "plugins\inventree-mbom\inventree_mbom"),
        (Join-Path $staticRoot "inventree_mbom")
    )

    foreach ($tgt in $targets) {
        if (-not (Test-Path $tgt)) { New-Item -ItemType Directory -Force $tgt | Out-Null }
        Copy-Item -Path "$pkgStaticDir\*" -Destination $tgt -Recurse -Force
        Write-Host "  Synced -> $tgt" -ForegroundColor Green
    }
} else {
    Write-Error "Could not find source static dir at $pkgStaticDir"
}

# 3. Invalidate Whitenoise / Gunicorn cache
if (-not $NoRestart) {
    Write-Host "[3/3] Invalidating Whitenoise static cache (restarting inventree-server)..." -ForegroundColor Yellow
    try {
        $serverRunning = (docker ps -q -f "name=inventree-server" 2>$null)
        if ($serverRunning) {
            docker restart inventree-server | Out-Null
            Write-Host "  inventree-server container restarted successfully." -ForegroundColor Green
        } else {
            Write-Host "  inventree-server is not running; skipping restart." -ForegroundColor Gray
        }
    } catch {
        Write-Warning "Failed to restart inventree-server container: $_"
    }
} else {
    Write-Host "[3/3] Restart skipped (-NoRestart specified)." -ForegroundColor Gray
}

Write-Host "`nSync complete! Hard-refresh the browser (Ctrl+Shift+R or Ctrl+F5) to load updated assets." -ForegroundColor Cyan

