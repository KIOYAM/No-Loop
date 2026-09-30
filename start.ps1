<#
.SYNOPSIS
    No_Loop - one command to start the local UI.

.DESCRIPTION
    First run builds .\.venv from the pinned requirements, then starts the UI
    on 127.0.0.1. Everything after this script is handed straight to the
    server, so:

        .\start.ps1                  build the venv if needed, then start
        .\start.ps1 --port 9000      use a different port
        .\start.ps1 --no-browser     don't auto-open a tab
        .\start.ps1 --no-banner      one-liner instead of the splash
        .\start.ps1 --no-color       plain text, no ANSI

    Nothing leaves this machine: the interpreter, the packages pinned in
    requirements.lock.txt and the records in .local-data all live in this
    folder.

.EXAMPLE
    .\start.ps1 --no-browser --port 9000

.NOTES
    There is deliberately no param() block: the server owns its own flags
    (--port, --no-browser, ...) and an advanced script would try to bind them
    as PowerShell parameters. A simple script hands them straight to $args.

    If Windows blocks the script, either run .\start.bat (it bypasses the
    policy for you) or:
        powershell -ExecutionPolicy Bypass -File .\start.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$Lock = Join-Path $Root 'requirements.lock.txt'

Set-Location $Root

function Test-BasePython {
    # Returns "3.12" when $Exe (plus $Prefix) is Python 3.12+, else $null.
    param([string]$Exe, [string[]]$Prefix)

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Exe @Prefix -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
        $ok = ($LASTEXITCODE -eq 0)
    } catch {
        $ok = $false
        $out = $null
    } finally {
        $ErrorActionPreference = $previous
    }
    if (-not $ok) { return $null }
    if ("$out" -notmatch '^(\d+)\.(\d+)$') { return $null }
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 12)) { return $null }
    return "$major.$minor"
}

function Find-BasePython {
    # py launcher first (it can pin a version), then a real python on PATH.
    # The WindowsApps stub is skipped: it opens the Store instead of running.
    $candidates = @()
    $py = Get-Command 'py' -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandType -eq 'Application' } |
        Select-Object -First 1
    if ($py) {
        foreach ($version in @('-3.13', '-3.12', '-3')) {
            $candidates += , @($py.Source, @($version))
        }
    }
    $python = Get-Command 'python' -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandType -eq 'Application' -and $_.Source -notlike '*\WindowsApps\*' } |
        Select-Object -First 1
    if ($python) { $candidates += , @($python.Source, @()) }

    foreach ($candidate in $candidates) {
        $exe = $candidate[0]
        $prefix = $candidate[1]
        $version = Test-BasePython -Exe $exe -Prefix $prefix
        if ($version) {
            return [pscustomobject]@{
                Exe     = $exe
                Prefix  = $prefix
                Version = $version
            }
        }
    }
    return $null
}

if (-not (Test-Path $VenvPython)) {
    Write-Host ''
    Write-Host '  No_Loop - first run' -ForegroundColor Cyan

    $base = Find-BasePython
    if (-not $base) {
        Write-Host '  Need Python 3.12 or newer, and none was found.' -ForegroundColor Red
        Write-Host '  Install it ( winget install Python.Python.3.13 ) and run this again.' -ForegroundColor Yellow
        Write-Host '  Nothing else has to be installed or configured.' -ForegroundColor Yellow
        Write-Host ''
        exit 1
    }

    $baseExe = $base.Exe
    $basePrefix = $base.Prefix

    Write-Host "  creating .venv with Python $($base.Version) ..." -ForegroundColor DarkGray
    & $baseExe @basePrefix -m venv $Venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host '  installing pinned dependencies (requirements.lock.txt) ...' -ForegroundColor DarkGray
    & $VenvPython -m pip install --disable-pip-version-check --quiet -r $Lock
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  dependency install failed - check the output above.' -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host '  ready.' -ForegroundColor Green
    Write-Host ''
}

& $VenvPython -m app.serve_ui @args
exit $LASTEXITCODE
