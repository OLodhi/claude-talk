<#
Sets up Claude Talk on this PC, or updates it after a git pull. Safe to run again.
Finds (or installs) Python 3.13, creates .venv, installs Claude Talk into it, then adds the Claude Code
hooks and the /talk command. -ClaudeDir points at a different Claude Code folder (used by the tests).
Run it through setup.cmd, which gets past PowerShell's script policy.
#>
param([string]$ClaudeDir)

$root = $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

function Fail([string]$message) {
    Write-Host "Setup failed: $message" -ForegroundColor Red
    exit 1
}

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $exe = py -3.13 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { return "$exe".Trim() }
    }
    $usual = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:ProgramFiles\Python313\python.exe",
        "C:\Python313\python.exe"
    )
    return $usual | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not (Test-Path $venvPython)) {
    $python = Find-Python
    if (-not $python) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Fail "Python 3.13 isn't installed. Install it from https://www.python.org/downloads/ and run setup again."
        }
        Write-Host "Installing Python 3.13 with winget..."
        winget install --id Python.Python.3.13 --exact --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $python = Find-Python
        if (-not $python) { Fail "Python 3.13 still can't be found. Open a new terminal and run setup again." }
    }
    Write-Host "Creating .venv with $python"
    & $python -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "couldn't create .venv." }
}

Write-Host "Installing Claude Talk into .venv..."
& $venvPython -m pip install --quiet --disable-pip-version-check -e $root
if ($LASTEXITCODE -ne 0) { Fail "pip couldn't install Claude Talk. Check the internet connection and run setup again." }

$installArgs = @("-P", "-m", "talk.install")  # -P: never import a talk folder from the current directory
if ($ClaudeDir) { $installArgs += @("--claude-dir", $ClaudeDir) }
& $venvPython @installArgs
if ($LASTEXITCODE -ne 0) { Fail "couldn't add the Claude Code hooks." }

Write-Host ""
Write-Host "Claude Talk is ready. Start a new Claude Code session and type /talk." -ForegroundColor Green
