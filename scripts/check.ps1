<#
.SYNOPSIS
    Lint, type-check and optionally compile py2gn function files.

.EXAMPLE
    .\scripts\check.ps1 temp\my_funcs.py -Compile
#>
#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0, ValueFromRemainingArguments)]
    [string[]]$Path,
    [switch]$Compile,
    [string]$Blender = $env:BLENDER_BIN
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path  # the checkout
$bin = Join-Path $root '.venv\Scripts'
if (-not (Test-Path -LiteralPath (Join-Path $bin 'ruff.exe'))) { throw 'No .venv: run .\scripts\setup_venv.ps1 first.' }
$files = @($Path | ForEach-Object { (Resolve-Path -LiteralPath $_).Path })
$failed = $false

Write-Host '== ruff' -ForegroundColor Cyan
& (Join-Path $bin 'ruff.exe') check @files
if ($LASTEXITCODE -ne 0) { $failed = $true }

Write-Host '== pyrefly' -ForegroundColor Cyan
Push-Location -LiteralPath $root
try {
    & (Join-Path $bin 'pyrefly.exe') check @files --output-format min-text
    if ($LASTEXITCODE -ne 0) { $failed = $true }
}
finally { Pop-Location }

if ($Compile) {
    Write-Host '== compile (background Blender, factory settings)' -ForegroundColor Cyan
    if (-not $Blender) {
        $Blender = Get-ChildItem -Path 'C:\Program Files\Blender Foundation' -Filter 'Blender *' -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'blender.exe' } |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $Blender) { throw 'Blender not found: pass -Blender <path> or set BLENDER_BIN.' }
    $out = & $Blender --background --factory-startup --quiet --python-exit-code 2 `
        --python (Join-Path $root 'tools\compile_check.py') -- @files 2>&1
    $code = $LASTEXITCODE
    $out | Where-Object { "$_" -match ': (ok|error): ' } | ForEach-Object { Write-Host $_ }
    if ($code -ne 0) {
        $failed = $true
        if ($code -eq 2) { $out | Select-Object -Last 15 | Write-Host }
    }
}

if ($failed) { Write-Host 'FAILED' -ForegroundColor Red; exit 1 }
Write-Host 'OK' -ForegroundColor Green
