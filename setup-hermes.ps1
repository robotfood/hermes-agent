# ============================================================================
# Hermes Agent Setup Script for Windows
# ============================================================================
# Quick setup for developers who cloned the repo manually.
# Uses uv for Python provisioning and package management.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\setup-hermes.ps1
#
# Options:
#   -SkipSetup        Do not run the setup wizard at the end
#   -NoNode          Skip Node.js checks and npm installs
#   -NoRipgrepPrompt Do not prompt to install ripgrep
#   -NoPlaywright    Skip Playwright Chromium installation
#   -ResetVenv       Delete and recreate .\venv even if it already exists
#   -Yes             Accept interactive prompts with the default yes answer
#   -NonInteractive  Do not prompt; skip optional prompt-driven actions
#
# This script:
# 1. Creates a Python 3.11 virtual environment in .\venv
# 2. Installs Hermes dependencies, preferring uv.lock when available
# 3. Creates .env from template in this checkout if it does not exist
# 4. Creates a hermes.cmd shim in %USERPROFILE%\.local\bin
# 5. Installs optional Node/TUI dependencies when Node is available
# 6. Syncs bundled skills and optionally runs the setup wizard
# ============================================================================

[CmdletBinding()]
param(
    [switch]$SkipSetup,
    [switch]$NoNode,
    [switch]$NoRipgrepPrompt,
    [switch]$NoPlaywright,
    [switch]$ResetVenv,
    [switch]$Yes,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$PythonVersion = "3.11"
$VenvDir = Join-Path $ScriptDir "venv"
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:USERPROFILE ".hermes" }
$UserBinDir = Join-Path $env:USERPROFILE ".local\bin"
$PowerShellCmd = $null

function Write-Info {
    param([string]$Message)
    Write-Host "-> $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERR] $Message" -ForegroundColor Red
}

function Write-Detail {
    param([string]$Message)
    Write-Verbose $Message
}

function Add-SessionPath {
    param([string]$Path)
    if (-not ($env:Path.Split(";") -contains $Path)) {
        $env:Path = "$Path;$env:Path"
    }
}

function Get-PowerShellCommand {
    if ($script:PowerShellCmd) {
        return $script:PowerShellCmd
    }

    try {
        $currentProcess = Get-Process -Id $PID -ErrorAction Stop
        if ($currentProcess.Path -and (Test-Path $currentProcess.Path)) {
            $script:PowerShellCmd = $currentProcess.Path
            return $script:PowerShellCmd
        }
    } catch {
        Write-Detail "Could not resolve current PowerShell executable: $_"
    }

    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwsh) {
        $script:PowerShellCmd = $pwsh.Source
        return $script:PowerShellCmd
    }

    $powershell = Get-Command powershell -ErrorAction SilentlyContinue
    if ($powershell) {
        $script:PowerShellCmd = $powershell.Source
        return $script:PowerShellCmd
    }

    throw "PowerShell executable not found."
}

function Invoke-NpmInstall {
    param(
        [string]$Directory,
        [string]$Label
    )

    Push-Location $Directory
    try {
        if ((Test-Path "package-lock.json") -or (Test-Path "npm-shrinkwrap.json")) {
            try {
                npm ci --silent
            } catch {
                Write-Detail "$Label npm ci failed, falling back to npm install: $_"
                npm install --silent
            }
        } else {
            npm install --silent
        }
        Write-Success "$Label dependencies installed"
    } finally {
        Pop-Location
    }
}

function Find-Uv {
    Write-Info "Checking for uv..."

    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        $script:UvCmd = $uvCommand.Source
        $version = & $script:UvCmd --version
        Write-Success "uv found ($version)"
        return
    }

    $uvPaths = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    )

    foreach ($uvPath in $uvPaths) {
        if (Test-Path $uvPath) {
            $script:UvCmd = $uvPath
            $version = & $script:UvCmd --version
            Write-Success "uv found ($version)"
            return
        }
    }

    Write-Info "Installing uv..."
    try {
        $powerShell = Get-PowerShellCommand
        & $powerShell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
    } catch {
        Write-Err "Failed to install uv. Install manually from https://docs.astral.sh/uv/"
        Write-Detail "uv install error: $_"
        throw
    }

    foreach ($uvPath in $uvPaths) {
        if (Test-Path $uvPath) {
            $script:UvCmd = $uvPath
            $version = & $script:UvCmd --version
            Write-Success "uv installed ($version)"
            return
        }
    }

    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        $script:UvCmd = $uvCommand.Source
        $version = & $script:UvCmd --version
        Write-Success "uv installed ($version)"
        return
    }

    throw "uv installed but was not found. Restart PowerShell and re-run this script."
}

function Ensure-Python {
    Write-Info "Checking Python $PythonVersion..."

    try {
        $pythonPath = & $UvCmd python find $PythonVersion 2>$null
        if ($pythonPath) {
            $version = & $pythonPath --version 2>$null
            Write-Success "$version found"
            return
        }
    } catch {
        Write-Detail "uv python find failed: $_"
    }

    Write-Info "Python $PythonVersion not found, installing via uv..."
    & $UvCmd python install $PythonVersion
    $pythonPath = & $UvCmd python find $PythonVersion
    $version = & $pythonPath --version 2>$null
    Write-Success "$version installed"
}

function Ensure-Venv {
    Write-Info "Setting up virtual environment..."

    if (Test-Path $VenvDir) {
        $existingPython = Join-Path $VenvDir "Scripts\python.exe"
        if ((Test-Path $existingPython) -and -not $ResetVenv) {
            $env:VIRTUAL_ENV = $VenvDir
            $script:SetupPython = $existingPython
            $version = & $script:SetupPython --version 2>$null
            Write-Success "Using existing venv ($version)"
            return
        }

        if ($ResetVenv) {
            Write-Info "Removing old venv (-ResetVenv)..."
        } else {
            Write-Warn "Existing venv is missing Scripts\python.exe; recreating it"
        }
        Remove-Item -Recurse -Force $VenvDir
    }

    & $UvCmd venv $VenvDir --python $PythonVersion
    $env:VIRTUAL_ENV = $VenvDir
    $script:SetupPython = Join-Path $VenvDir "Scripts\python.exe"
    Write-Success "venv created (Python $PythonVersion)"
}

function Install-PythonDependencies {
    Write-Info "Installing dependencies..."

    if (Test-Path (Join-Path $ScriptDir "uv.lock")) {
        Write-Info "Using uv.lock for hash-verified installation..."
        $env:UV_PROJECT_ENVIRONMENT = $VenvDir
        try {
            & $UvCmd sync --all-extras --locked
            Write-Success "Dependencies installed (lockfile verified)"
        } catch {
            Write-Warn "Lockfile install failed, falling back to editable install..."
            Write-Detail "uv sync error: $_"
            try {
                & $UvCmd pip install -e ".[all]"
            } catch {
                Write-Detail "Editable install with extras failed: $_"
                & $UvCmd pip install -e "."
            }
            Write-Success "Dependencies installed"
        } finally {
            Remove-Item Env:\UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue
        }
    } else {
        try {
            & $UvCmd pip install -e ".[all]"
        } catch {
            Write-Detail "Editable install with extras failed: $_"
            & $UvCmd pip install -e "."
        }
        Write-Success "Dependencies installed"
    }
}

function Install-OptionalSubmodules {
    Write-Info "Installing optional submodules..."

    $tinkerProject = Join-Path $ScriptDir "tinker-atropos\pyproject.toml"
    if (Test-Path $tinkerProject) {
        try {
            & $UvCmd pip install -e ".\tinker-atropos"
            Write-Success "tinker-atropos installed"
        } catch {
            Write-Warn "tinker-atropos install failed (RL tools may not work)"
            Write-Detail "tinker-atropos install error: $_"
        }
    } else {
        Write-Warn "tinker-atropos not found (run: git submodule update --init --recursive)"
    }
}

function Install-RipgrepIfWanted {
    Write-Info "Checking ripgrep (optional, for faster search)..."

    if (Get-Command rg -ErrorAction SilentlyContinue) {
        Write-Success "ripgrep found"
        return
    }

    Write-Warn "ripgrep not found (file search will use fallback search)"
    if ($NoRipgrepPrompt -or ($NonInteractive -and -not $Yes)) {
        return
    }

    if (-not $Yes) {
        $response = Read-Host "Install ripgrep for faster search? [Y/n]"
        if ($response -ne "" -and $response -notmatch "^[Yy]") {
            return
        }
    }

    $installed = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try {
            winget install BurntSushi.ripgrep.MSVC --silent --accept-package-agreements --accept-source-agreements | Out-Null
            $installed = $true
        } catch {
            Write-Detail "winget ripgrep install failed: $_"
        }
    }
    if (-not $installed -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        try {
            choco install ripgrep -y | Out-Null
            $installed = $true
        } catch {
            Write-Detail "choco ripgrep install failed: $_"
        }
    }
    if (-not $installed -and (Get-Command scoop -ErrorAction SilentlyContinue)) {
        try {
            scoop install ripgrep | Out-Null
            $installed = $true
        } catch {
            Write-Detail "scoop ripgrep install failed: $_"
        }
    }

    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($installed -and (Get-Command rg -ErrorAction SilentlyContinue)) {
        Write-Success "ripgrep installed"
    } else {
        Write-Warn "Auto-install failed. Try: winget install BurntSushi.ripgrep.MSVC"
    }
}

function Ensure-EnvFile {
    $envPath = Join-Path $ScriptDir ".env"
    $examplePath = Join-Path $ScriptDir ".env.example"

    if (Test-Path $envPath) {
        Write-Success ".env exists"
        return
    }

    if (Test-Path $examplePath) {
        Copy-Item $examplePath $envPath
        Write-Success "Created .env from template"
    }
}

function Install-HermesShim {
    Write-Info "Setting up hermes command..."

    New-Item -ItemType Directory -Force -Path $UserBinDir | Out-Null

    $hermesExe = Join-Path $VenvDir "Scripts\hermes.exe"
    if (-not (Test-Path $hermesExe)) {
        throw "Hermes CLI was not installed at $hermesExe. Re-run the dependency install step or try: $UvCmd pip install -e '.[all]'"
    }

    $psShimPath = Join-Path $UserBinDir "hermes.ps1"
    $shimPath = Join-Path $UserBinDir "hermes.cmd"
    $powerShell = Get-PowerShellCommand
    $psShimContent = @"
& "$hermesExe" @args
exit `$LASTEXITCODE
"@
    $shimContent = @"
@echo off
"$powerShell" -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\.local\bin\hermes.ps1" %*
"@
    [System.IO.File]::WriteAllText($psShimPath, $psShimContent, [System.Text.UTF8Encoding]::new($false))
    Set-Content -Path $shimPath -Value $shimContent -Encoding ASCII
    Write-Success "Created shim: $shimPath"

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathParts = @()
    if ($userPath) { $pathParts = $userPath.Split(";") }

    if ($pathParts -notcontains $UserBinDir) {
        $newPath = if ($userPath) { "$UserBinDir;$userPath" } else { $UserBinDir }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Success "Added $UserBinDir to user PATH"
    } else {
        Write-Success "$UserBinDir already on user PATH"
    }

    Add-SessionPath $UserBinDir
}

function Install-NodeDeps {
    if ($NoNode) {
        Write-Info "Skipping Node.js dependencies (-NoNode)"
        return
    }

    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Warn "Node.js not found; browser tools and hermes --tui dependencies were not installed"
        Write-Host "       Install Node.js LTS, then run this script again or run npm install manually."
        return
    }

    if (Test-Path (Join-Path $ScriptDir "package.json")) {
        Write-Info "Installing Node.js dependencies..."
        try {
            Invoke-NpmInstall -Directory $ScriptDir -Label "Node.js"
        } catch {
            Write-Warn "npm install failed (browser tools may not work)"
            Write-Detail "root npm install error: $_"
        }

        if ($NoPlaywright) {
            Write-Info "Skipping Playwright Chromium (-NoPlaywright)"
        } elseif (Get-Command npx -ErrorAction SilentlyContinue) {
            Write-Info "Installing Playwright Chromium..."
            try {
                npx playwright install chromium
                Write-Success "Playwright Chromium installed"
            } catch {
                Write-Warn "Playwright install failed (browser tools may need manual setup)"
                Write-Detail "Playwright install error: $_"
            }
        }
    }

    $tuiDir = Join-Path $ScriptDir "ui-tui"
    if (Test-Path (Join-Path $tuiDir "package.json")) {
        Write-Info "Installing TUI dependencies..."
        try {
            Invoke-NpmInstall -Directory $tuiDir -Label "TUI"
        } catch {
            Write-Warn "TUI npm install failed (hermes --tui may not work)"
            Write-Detail "TUI npm install error: $_"
        }
    }
}

function Sync-Skills {
    $skillsDir = Join-Path $HermesHome "skills"
    New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null

    Write-Info "Syncing bundled skills to $skillsDir ..."
    $syncScript = Join-Path $ScriptDir "tools\skills_sync.py"
    if ((Test-Path $SetupPython) -and (Test-Path $syncScript)) {
        try {
            & $SetupPython $syncScript 2>$null
            Write-Success "Skills synced"
            return
        } catch {
            Write-Detail "skills_sync.py failed: $_"
        }
    }

    $bundledSkills = Join-Path $ScriptDir "skills"
    if (Test-Path $bundledSkills) {
        Copy-Item -Path (Join-Path $bundledSkills "*") -Destination $skillsDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Success "Skills copied"
    }
}

function Invoke-SetupWizard {
    if ($SkipSetup) {
        Write-Info "Skipping setup wizard (-SkipSetup)"
        return
    }

    if ($NonInteractive -and -not $Yes) {
        Write-Info "Skipping setup wizard (-NonInteractive)"
        return
    }

    if ($Yes) {
        & $SetupPython -m hermes_cli.main setup
        return
    }

    $response = Read-Host "Would you like to run the setup wizard now? [Y/n]"
    if ($response -eq "" -or $response -match "^[Yy]") {
        & $SetupPython -m hermes_cli.main setup
    }
}

function Write-BaseCompletion {
    Write-Host ""
    Write-Success "Base setup complete."
}

function Write-Completion {
    Write-Host ""
    Write-Success "Setup complete!"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Restart PowerShell if this is the first time $UserBinDir was added to PATH"
    Write-Host "  2. Run the setup wizard if you skipped it:"
    Write-Host "     hermes setup"
    Write-Host "  3. Start chatting:"
    Write-Host "     hermes"
    Write-Host ""
    Write-Host "Other commands:"
    Write-Host "  hermes status          # Check configuration"
    Write-Host "  hermes gateway         # Run gateway in foreground"
    Write-Host "  hermes cron list       # View scheduled jobs"
    Write-Host "  hermes doctor          # Diagnose issues"
}

function Main {
    Write-Host ""
    Write-Host "Hermes Agent Setup" -ForegroundColor Cyan
    Write-Host ""

    Find-Uv
    Ensure-Python
    Ensure-Venv
    Install-PythonDependencies
    Install-OptionalSubmodules
    Install-RipgrepIfWanted
    Ensure-EnvFile
    Install-HermesShim
    Install-NodeDeps
    Sync-Skills
    Write-BaseCompletion
    Invoke-SetupWizard
    Write-Completion
}

try {
    Main
} catch {
    Write-Host ""
    Write-Err "Setup failed: $_"
    Write-Host ""
    Write-Host "Try re-running from the repository root:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\setup-hermes.ps1"
    exit 1
}
