from pathlib import Path
import subprocess


def test_installer_rejects_other_instance_and_missing_autostart():
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'installer-functions.ps1'
    escaped = str(script).replace("'", "''")
    command = f". '{escaped}'\n" + r'''
$status = [pscustomobject]@{version='2.0.0';running=$true;pid=123;autostart=$true;data_directory='C:\data'}
if (Test-KMCounterReady $status 456 'C:\data') { exit 1 }
$status.autostart = $false
if (Test-KMCounterReady $status 123 'C:\data') { exit 2 }
$status.autostart = $true
if (-not (Test-KMCounterReady $status 123 'C:\data')) { exit 3 }
'''
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', command],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
