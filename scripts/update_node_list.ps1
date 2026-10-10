<#
.SYNOPSIS
    Regenerate NODES.md, the checklist of Geometry Nodes (tools/node_checklist.py in a background Blender).
#>
#Requires -Version 5.1
[CmdletBinding()]
param([string]$Blender = $env:BLENDER_BIN)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $Blender) {
    $Blender = Get-ChildItem -Path 'C:\Program Files\Blender Foundation' -Filter 'Blender *' -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'blender.exe' } |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Blender) { throw 'Blender not found: pass -Blender <path> or set BLENDER_BIN.' }
& $Blender --background --factory-startup --quiet --python-exit-code 1 --python (Join-Path $root 'tools\node_checklist.py') 2>&1 |
    Where-Object { "$_" -match 'node checklist' } | ForEach-Object { Write-Host $_ }
exit $LASTEXITCODE
