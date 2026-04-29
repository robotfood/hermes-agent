from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = REPO_ROOT / "setup-hermes.ps1"


def test_setup_hermes_windows_script_exists():
    assert SETUP_SCRIPT.exists()


def test_setup_hermes_windows_script_is_valid_powershell():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is not installed")

    command = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{SETUP_SCRIPT}', [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count) { $errors | ForEach-Object { $_.Message }; exit 1 }"
    )
    result = subprocess.run([shell, "-NoProfile", "-Command", command], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_setup_hermes_windows_script_targets_current_checkout():
    content = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path" in content
    assert "Set-Location $ScriptDir" in content
    assert "git clone" not in content
    assert "NousResearch/hermes-agent.git" not in content


def test_setup_hermes_windows_script_installs_like_unix_setup():
    content = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "$PythonVersion = \"3.11\"" in content
    assert "& $UvCmd venv $VenvDir --python $PythonVersion" in content
    assert "[switch]$ResetVenv" in content
    assert "Using existing venv" in content
    assert "& $UvCmd sync --all-extras --locked" in content
    assert "& $UvCmd pip install -e \".[all]\"" in content
    assert ".env.example" in content
    assert "tools\\skills_sync.py" in content


def test_setup_hermes_windows_script_has_windows_command_shim():
    content = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert ".local\\bin" in content
    assert "Scripts\\hermes.exe" in content
    assert "hermes.ps1" in content
    assert "hermes.cmd" in content
    assert "[System.IO.File]::WriteAllText" in content
    assert "[Environment]::SetEnvironmentVariable(\"Path\"" in content


def test_setup_hermes_windows_script_handles_optional_node_and_tui_deps():
    content = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$NoNode" in content
    assert "[switch]$NoPlaywright" in content
    assert "npm ci --silent" in content
    assert "npm install --silent" in content
    assert "npx playwright install chromium" in content
    assert "ui-tui" in content


def test_setup_hermes_windows_script_has_noninteractive_mode_and_verbose_errors():
    content = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$Yes" in content
    assert "[switch]$NonInteractive" in content
    assert "Write-Verbose" in content
    assert "Skipping setup wizard (-NonInteractive)" in content
    assert "Write-BaseCompletion" in content
