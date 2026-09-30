<#
.SYNOPSIS
    Vendor GrapesJS + the newsletter preset into app/ui/static/vendor/grapesjs.

.DESCRIPTION
    One-time (re-runnable) script. It pulls the two BSD-3-Clause npm tarballs,
    extracts only their dist bundles + licenses, and writes them into the repo
    so the running app never touches npm, a CDN or the network.

    The output is committed on purpose: nobody else has to run this.

.EXAMPLE
    .\scripts\vendor_grapesjs.ps1
    .\scripts\vendor_grapesjs.ps1 -Version 0.23.6 -PresetVersion 1.0.2
#>
[CmdletBinding()]
param(
    [string]$Version = "0.23.6",
    [string]$PresetVersion = "1.0.2",
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
if (-not $Destination) {
    $Destination = Join-Path $PSScriptRoot "..\app\ui\static\vendor\grapesjs"
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required to fetch the tarballs (runtime does NOT need npm - only this script does)."
}

$dest = (Resolve-Path -LiteralPath (Split-Path $Destination -Parent) -ErrorAction SilentlyContinue)
$target = if ($dest) { Join-Path $dest.Path (Split-Path $Destination -Leaf) } else { [System.IO.Path]::GetFullPath($Destination) }
$work = Join-Path ([System.IO.Path]::GetTempPath()) "noloop-vendor-grapesjs"
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $work | Out-Null
New-Item -ItemType Directory -Force -Path $target | Out-Null

Push-Location $work
try {
    Write-Host "fetching grapesjs@$Version and grapesjs-preset-newsletter@$PresetVersion ..."
    npm pack "grapesjs@$Version" "grapesjs-preset-newsletter@$PresetVersion" --silent | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "npm pack failed" }

    $core = Get-ChildItem $work -Filter "grapesjs-$Version.tgz" | Select-Object -First 1
    $preset = Get-ChildItem $work -Filter "grapesjs-preset-newsletter-$PresetVersion.tgz" | Select-Object -First 1
    if (-not $core -or -not $preset) { throw "expected tarballs not found in $work" }

    $coreDir = Join-Path $work "core"; $presetDir = Join-Path $work "preset"
    New-Item -ItemType Directory -Force -Path $coreDir, $presetDir | Out-Null
    tar -xf $core.FullName -C $coreDir
    tar -xf $preset.FullName -C $presetDir
    if ($LASTEXITCODE -ne 0) { throw "tar extraction failed" }

    $copies = @{
        (Join-Path $coreDir "package\dist\grapes.min.js")      = "grapes.min.js"
        (Join-Path $coreDir "package\dist\css\grapes.min.css") = "grapes.min.css"
        (Join-Path $coreDir "package\LICENSE")                 = "LICENSE.grapesjs"
        (Join-Path $presetDir "package\dist\index.js")         = "preset-newsletter.min.js"
        (Join-Path $presetDir "package\LICENSE")               = "LICENSE.preset-newsletter"
    }
    foreach ($src in $copies.Keys) {
        if (-not (Test-Path $src)) { throw "missing $src" }
        Copy-Item -LiteralPath $src -Destination (Join-Path $target $copies[$src]) -Force
    }

    # optional: GrapesJS ships locales; only the ones we can actually use (UI is en)
    $localeDir = Join-Path $target "locale"
    New-Item -ItemType Directory -Force -Path $localeDir | Out-Null
    foreach ($lang in @("en", "es", "pt")) {
        $f = Join-Path $coreDir "package\locale\$lang.js"
        if (Test-Path $f) { Copy-Item $f (Join-Path $localeDir "$lang.js") -Force }
    }

    $notice = @"
# Third-party assets vendored in this folder

| File | Package | Version | License | Source |
|---|---|---|---|---|
| ``grapes.min.js``, ``grapes.min.css``, ``locale/*`` | grapesjs | $Version | BSD-3-Clause (``LICENSE.grapesjs``) | https://www.npmjs.com/package/grapesjs |
| ``preset-newsletter.min.js`` | grapesjs-preset-newsletter | $PresetVersion | BSD-3-Clause (``LICENSE.preset-newsletter``) | https://www.npmjs.com/package/grapesjs-preset-newsletter |

Regenerate with ``scripts\vendor_grapesjs.ps1`` (needs npm **once**; the app
itself never calls npm, a CDN or any network service at runtime).

Loaded only by ``app/ui/static/js/core/grapesjs_loader.js`` when the user opens
``#/builder``; torn down again on route leave.
"@
    Set-Content -Path (Join-Path $target "NOTICE.md") -Value $notice -Encoding utf8

    Get-ChildItem -Recurse $target -File | ForEach-Object {
        "{0,10}  {1}" -f $_.Length, $_.FullName.Substring($target.Length + 1)
    }
    Write-Host "vendored into $target" -ForegroundColor Green
}
finally {
    Pop-Location
}
