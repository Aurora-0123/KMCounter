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


def test_startup_registration_uses_system_registry_and_verifies_readback():
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'installer-functions.ps1'
    escaped = str(script).replace("'", "''")
    command = "$ErrorActionPreference='Stop'\n" + f". '{escaped}'\n" + r'''
$script:storedStartup = $null
$script:writeCount = 0
function Invoke-CimMethod {
    param($Namespace, $ClassName, $MethodName, $Arguments)
    if ($ClassName -ne 'StdRegProv' -or $Arguments.hDefKey -ne [uint32]2147483651) {
        throw 'Must use the actual user hive through the system registry provider'
    }
    switch ($MethodName) {
        'CreateKey' { return [pscustomobject]@{ReturnValue=0} }
        'SetStringValue' {
            $script:writeCount++
            $script:storedStartup = $Arguments.sValue
            return [pscustomobject]@{ReturnValue=0}
        }
        'GetStringValue' { return [pscustomobject]@{ReturnValue=0;sValue=$script:storedStartup} }
        default { throw 'Unexpected registry operation' }
    }
}
Register-KMCounterStartup 'C:\Example User\KMCounter.exe'
if ($script:writeCount -ne 1 -or $script:storedStartup -ne '"C:\Example User\KMCounter.exe" --background') { exit 1 }
function Invoke-CimMethod {
    param($Namespace, $ClassName, $MethodName, $Arguments)
    if ($MethodName -eq 'GetStringValue') { return [pscustomobject]@{ReturnValue=1;sValue=$null} }
    return [pscustomobject]@{ReturnValue=0}
}
$caught = $false
try { Register-KMCounterStartup 'C:\Example User\KMCounter.exe' } catch { $caught = $true }
if (-not $caught) { exit 2 }
function Invoke-CimMethod {
    param($Namespace, $ClassName, $MethodName, $Arguments)
    return [pscustomobject]@{ReturnValue=2;sNames=$null}
}
Remove-KMCounterStartup
'''
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', command],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
