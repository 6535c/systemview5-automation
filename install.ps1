param([string]$Destination = (Join-Path $env:LOCALAPPDATA 'Programs\SystemView5Automation'))
$ErrorActionPreference = 'Stop'
$sourceRoot = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $sourceRoot 'release-files.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$targetRoot = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $targetRoot) { throw 'Destination already exists. Choose a new directory; nothing was overwritten.' }
foreach ($entry in $manifest.files.PSObject.Properties) {
    $relative = $entry.Name
    if ([IO.Path]::IsPathRooted($relative) -or (($relative -split '[\\/]') -contains '..')) { throw 'Invalid release path.' }
    $source = Join-Path $sourceRoot $relative
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw "Checksum mismatch: $relative" }
}
New-Item -ItemType Directory -Path $targetRoot | Out-Null
foreach ($entry in $manifest.files.PSObject.Properties) {
    $target = Join-Path $targetRoot $entry.Name
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($target)) | Out-Null
    Copy-Item -LiteralPath (Join-Path $sourceRoot $entry.Name) -Destination $target
}
Copy-Item -LiteralPath (Join-Path $sourceRoot 'release-files.json') -Destination $targetRoot
Write-Output "Installed: $targetRoot"
Write-Output 'Next: run sv.cmd config --exe with your SystemView path, then sv.cmd doctor.'
