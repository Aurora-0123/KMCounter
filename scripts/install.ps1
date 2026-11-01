param(
    [string]$LegacyData = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'installer-functions.ps1')
$source = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $source 'KMCounter.exe'))) {
    $source = Join-Path (Split-Path $PSScriptRoot -Parent) 'dist\KMCounter'
}
if (-not (Test-Path -LiteralPath (Join-Path $source 'KMCounter.exe'))) {
    throw 'Build or extract KMCounter first.'
}
$localData = [Environment]::GetFolderPath('LocalApplicationData')
$destination = Join-Path $localData 'Programs\KMCounter'
$dataDirectory = Join-Path $localData 'KMCounter\data'
$executable = Join-Path $destination 'KMCounter.exe'

# Update only after the running installed version has saved and exited.
$allInstances = @(Get-CimInstance Win32_Process -Filter "Name = 'KMCounter.exe'")
$running = @($allInstances | Where-Object { $_.ExecutablePath -eq $executable })
if (@($allInstances | Where-Object { $_.ExecutablePath -ne $executable }).Count -gt 0) {
    throw 'Another copy of KMCounter is running. Exit it from its tray or webpage before installing.'
}
if ($running.Count -gt 0) {
    $page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5000/'
    $match = [regex]::Match($page.Content, 'name="control-token" content="([A-Za-z0-9_-]+)"')
    if (-not $match.Success) { throw 'Exit KMCounter from the tray before updating.' }
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:5000/control/stop' -Headers @{
        Origin = 'http://127.0.0.1:5000'
        'X-KMCounter-Token' = $match.Groups[1].Value
    } | Out-Null
    foreach ($process in $running) {
        Wait-Process -Id $process.ProcessId -Timeout 15 -ErrorAction SilentlyContinue
        if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
            throw 'The running program could not finish saving. Installation was stopped.'
        }
    }
}

# Source archives and existing statistics are retained, including during updates.
New-Item -ItemType Directory -Path $destination -Force | Out-Null
if ([IO.Path]::GetFullPath($source).TrimEnd('\') -ne [IO.Path]::GetFullPath($destination).TrimEnd('\')) {
    Get-ChildItem -LiteralPath $source -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
if ($LegacyData -and -not (Test-Path -LiteralPath $LegacyData -PathType Container)) {
    throw 'Legacy data directory does not exist.'
}
if ($LegacyData) {
    $backup = Join-Path (Split-Path $dataDirectory -Parent) ('legacy-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Item -LiteralPath $LegacyData -Destination $backup -Recurse
}
$arguments = @('--background', '--enable-autostart')
if ($LegacyData) {
    $arguments += @('--import-data', ('"' + [IO.Path]::GetFullPath($LegacyData) + '"'))
}
Register-KMCounterStartup $executable
$launched = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $destination -WindowStyle Hidden -PassThru
$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $status = Invoke-RestMethod -Uri 'http://127.0.0.1:5000/status' -TimeoutSec 1
        if (Test-KMCounterReady $status $launched.Id $dataDirectory) {
            $ready = $true
            break
        }
    } catch { }
}
if (-not $ready) { throw 'Installed, but startup failed. Check the program message and kmcounter.log.' }
Write-Output "Installed and running: $executable"
Write-Output "Statistics: $dataDirectory"
if ($status.errors.Count -gt 0) { Write-Warning ($status.errors -join '; ') }
