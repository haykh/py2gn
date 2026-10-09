<#
.SYNOPSIS
    Create .venv (Python 3.13, matching Blender 5.2) with fake-bpy-module, ruff and pyrefly.

.DESCRIPTION
    Uses uv when available, otherwise `py -3.13 -m venv`. Adds a .pth file so
    `import py2gn` (as in `from py2gn.lang import *`) resolves to this checkout,
    which gives LSP completion in function files anywhere on disk when VS Code
    uses this interpreter.
#>
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root '.venv'
$py = Join-Path $venv 'Scripts\python.exe'

if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv venv $venv --python 3.13 --allow-existing
    uv pip install --python $py -r (Join-Path $root 'requirements.txt')
} else {
    py -3.13 -m venv $venv
    & $py -m pip install --upgrade pip
    & $py -m pip install -r (Join-Path $root 'requirements.txt')
}

$site = & $py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"
Set-Content -LiteralPath (Join-Path $site 'py2gn_dev.pth') -Value (Split-Path -Parent $root) -Encoding ascii
Write-Host "Ready: $py"
