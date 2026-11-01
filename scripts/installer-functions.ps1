param([ValidateSet('Enable', 'Disable', 'Check')][string]$StartupAction)

function Test-KMCounterReady {
    param([object]$Status, [int]$ExpectedProcessId, [string]$DataDirectory)
    return ($Status.version -eq '2.0.0' -and $Status.running -and
        $Status.pid -eq $ExpectedProcessId -and $Status.autostart -eq $true -and
        $Status.data_directory -eq $DataDirectory)
}

function Register-KMCounterStartup {
    param([string]$Executable, [string]$Command)
    $userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $registry = @{
        hDefKey = [uint32]2147483651 # HKEY_USERS, scoped to the current user SID.
        sSubKeyName = $userSid + '\Software\Microsoft\Windows\CurrentVersion\Run'
    }
    if (-not $Command) { $Command = '"' + $Executable + '" --background' }
    $created = Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName CreateKey -Arguments $registry
    if ($created.ReturnValue -ne 0) { throw 'Windows could not open the current-user startup key.' }
    $valueArguments = $registry.Clone()
    $valueArguments.sValueName = 'KMCounter'
    $writeArguments = $valueArguments.Clone()
    $writeArguments.sValue = $Command
    $written = Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName SetStringValue -Arguments $writeArguments
    if ($written.ReturnValue -ne 0) { throw 'Windows could not register KMCounter startup.' }
    # Read through the system provider, not only the install process's registry view.
    $verified = Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName GetStringValue -Arguments $valueArguments
    if ($verified.ReturnValue -ne 0 -or $verified.sValue -ne $Command) {
        throw 'The Windows system registry cannot see the startup registration.'
    }
}

function Remove-KMCounterStartup {
    $userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $registry = @{
        hDefKey = [uint32]2147483651
        sSubKeyName = $userSid + '\Software\Microsoft\Windows\CurrentVersion\Run'
    }
    $listed = Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName EnumValues -Arguments $registry
    if ($listed.ReturnValue -eq 2) { return } # Run key is absent: already disabled.
    if ($listed.ReturnValue -ne 0) { throw 'Windows could not read the current-user startup key.' }
    if (@($listed.sNames) -notcontains 'KMCounter') { return }
    $arguments = $registry.Clone()
    $arguments.sValueName = 'KMCounter'
    $deleted = Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName DeleteValue -Arguments $arguments
    if ($deleted.ReturnValue -ne 0) { throw 'Windows could not remove KMCounter startup.' }
    $listed = Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName EnumValues -Arguments $registry
    if ($listed.ReturnValue -ne 0 -or @($listed.sNames) -contains 'KMCounter') {
        throw 'Windows still sees the startup registration after removal.'
    }
}

function Get-KMCounterStartupCommand {
    $userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $registry = @{
        hDefKey = [uint32]2147483651
        sSubKeyName = $userSid + '\Software\Microsoft\Windows\CurrentVersion\Run'
    }
    $listed = Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName EnumValues -Arguments $registry
    if ($listed.ReturnValue -eq 2) { return $null }
    if ($listed.ReturnValue -ne 0) { throw 'Windows could not read the current-user startup key.' }
    if (@($listed.sNames) -notcontains 'KMCounter') { return $null }
    $registry.sValueName = 'KMCounter'
    $value = Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName GetStringValue -Arguments $registry
    if ($value.ReturnValue -ne 0) { throw 'Windows could not read KMCounter startup.' }
    return $value.sValue
}

if ($StartupAction -eq 'Enable') {
    if (-not $env:KMC_STARTUP_COMMAND) { throw 'Missing startup command.' }
    Register-KMCounterStartup -Command $env:KMC_STARTUP_COMMAND
} elseif ($StartupAction -eq 'Disable') {
    Remove-KMCounterStartup
} elseif ($StartupAction -eq 'Check') {
    $command = Get-KMCounterStartupCommand
    if ($command -and $command -eq $env:KMC_STARTUP_COMMAND) {
        [Console]::Out.WriteLine('enabled')
    } else {
        [Console]::Out.WriteLine('disabled')
    }
}
