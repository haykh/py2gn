<#
.SYNOPSIS
    Link this checkout into a Blender version's extensions directory (editable install).

.DESCRIPTION
    Creates a directory junction (no admin rights needed)
        %APPDATA%\Blender Foundation\Blender\<Version>\extensions\<Repository>\py2gn -> this folder
    so Blender loads the add-on straight from the checkout. Re-running is safe. With
    -Uninstall only the link is removed; the checkout is never touched.

.PARAMETER Version
    Blender version, e.g. 5.2. Omit to list the versions that have a config directory.

.PARAMETER Repository
    Extensions repository to link into. Default: user_default.

.PARAMETER Enable
    Also enable the add-on and save preferences, by running that Blender version in the
    background. Close that Blender version first: a running instance saves its own
    preferences on exit and would undo this.

.PARAMETER Blender
    blender.exe for -Enable. Default: C:\Program Files\Blender Foundation\Blender <Version>\blender.exe

.PARAMETER Force
    Replace an existing link that points somewhere else.

.EXAMPLE
    .\install.ps1 5.2 -Enable

.EXAMPLE
    .\install.ps1 5.2 -Uninstall
#>

#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Version,
    [string]$Repository = 'user_default',
    [switch]$Enable,
    [string]$Blender,
    [switch]$Uninstall,
    [switch]$Force,
    # Advanced/testing: Blender's per-user config root.
    [string]$ConfigRoot = (Join-Path $env:APPDATA 'Blender Foundation\Blender')
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path.TrimEnd('\')
$addonId = 'py2gn'
$minVersion = [version]'5.2'   # blender_version_min in blender_manifest.toml

if (-not $Version) {
    $found = @(Get-ChildItem -LiteralPath $ConfigRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+\.\d+$' } | Sort-Object { [version]$_.Name } | ForEach-Object Name)
    Write-Host 'Usage: .\install.ps1 <version> [-Enable] [-Uninstall]'
    if ($found.Count) { Write-Host ('Blender versions with a config directory: ' + ($found -join ', ')) }
    else { Write-Host "No Blender config directories under $ConfigRoot" }
    exit 1
}
if ($Version -notmatch '^\d+\.\d+$') { throw "Version must look like 5.2, got '$Version'." }
if ([version]$Version -lt $minVersion) { throw "py2gn requires Blender $minVersion or newer (blender_manifest.toml)." }

$repoDir = Join-Path $ConfigRoot "$Version\extensions\$Repository"
$link = Join-Path $repoDir $addonId

function Get-LinkTarget([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item -or -not $item.LinkType) { return $null }
    return ((@($item.Target)[0]) -replace '^\\\\\?\\', '').TrimEnd('\')
}

function Remove-Link([string]$Path) {
    # rmdir on a junction removes only the link, never the contents of its target
    cmd /c rmdir "$Path"
    if ($LASTEXITCODE -ne 0) { throw "Could not remove link $Path" }
}

$existing = Test-Path -LiteralPath $link
$target = if ($existing) { Get-LinkTarget $link } else { $null }

if ($Uninstall) {
    if (-not $existing) { Write-Host "Not installed: $link"; exit 0 }
    if (-not $target) { throw "$link is a real directory, not a link (installed from a zip?). Remove it in Blender's preferences instead." }
    Remove-Link $link
    Write-Host "Removed link $link (checkout untouched)."
    exit 0
}

if ($existing) {
    if ($target -and ($target -eq $root)) {
        Write-Host "Already installed: $link -> $root"
    }
    elseif ($target) {
        if (-not $Force) { throw "$link already links to '$target'. Use -Force to replace it." }
        Remove-Link $link
        $existing = $false
    }
    else {
        throw "$link is a real directory (installed from a zip?). Remove it in Blender's preferences first."
    }
}
if (-not $existing) {
    New-Item -ItemType Directory -Path $repoDir -Force | Out-Null
    New-Item -ItemType Junction -Path $link -Target $root | Out-Null
    Write-Host "Linked $link -> $root"
}

if ($Enable) {
    if (-not $Blender) { $Blender = "C:\Program Files\Blender Foundation\Blender $Version\blender.exe" }
    if (-not (Test-Path -LiteralPath $Blender -PathType Leaf)) { throw "Blender not found at '$Blender'. Pass -Blender <path>." }
    $module = "bl_ext.$Repository.$addonId"
    $expr = "import bpy; bpy.ops.extensions.repo_refresh_all(); " +
            "r = bpy.ops.preferences.addon_enable(module='$module'); " +
            "bpy.ops.wm.save_userpref(); print('py2gn-install: enable', r)"
    $out = & $Blender --background --python-exit-code 1 --python-expr $expr 2>&1
    if ($LASTEXITCODE -ne 0 -or -not ($out -match "py2gn-install: enable \{'FINISHED'\}")) {
        $out | Select-Object -Last 20 | Write-Host
        throw 'Enabling failed.'
    }
    Write-Host "Enabled $module in Blender $Version (preferences saved)."
}
else {
    Write-Host 'Enable it in Blender: Preferences > Add-ons > py2gn (or re-run with -Enable).'
}
