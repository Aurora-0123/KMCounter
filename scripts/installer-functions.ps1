function Test-KMCounterReady {
    param([object]$Status, [int]$ExpectedProcessId, [string]$DataDirectory)
    return ($Status.version -eq '2.0.0' -and $Status.running -and
        $Status.pid -eq $ExpectedProcessId -and $Status.autostart -eq $true -and
        $Status.data_directory -eq $DataDirectory)
}
