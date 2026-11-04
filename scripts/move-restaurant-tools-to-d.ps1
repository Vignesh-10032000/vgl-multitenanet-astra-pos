$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path.TrimEnd('\')
if ($projectRoot -ne 'D:\vgl-restaurant-pos') { throw "Unexpected project root: $projectRoot" }
$toolRoot = Join-Path $projectRoot '.tools'
if ((Get-Item -LiteralPath $toolRoot).LinkType) { throw 'Tools root must be a real directory on D:.' }

# These are the only C: directories this migration may replace. Compatibility
# junctions preserve existing SDK/browser references in other local tools.
$moves = @(
    @{ Source = 'C:\Users\L E N O V O\AppData\Local\ms-playwright'; Name = 'playwright' },
    @{ Source = 'C:\Users\L E N O V O\AppData\Local\Android\Sdk'; Name = 'android-sdk' },
    @{ Source = 'C:\Users\L E N O V O\.android'; Name = 'android-user' }
)
$diskBefore = (Get-PSDrive C).Free
$moved = @()
foreach ($move in $moves) {
    $source = [IO.Path]::GetFullPath($move.Source).TrimEnd('\')
    $destination = [IO.Path]::GetFullPath((Join-Path $toolRoot $move.Name)).TrimEnd('\')
    if ($source -ne $move.Source -or -not $destination.StartsWith($toolRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Migration path validation failed.'
    }
    if (-not (Test-Path -LiteralPath $source)) { continue }
    $sourceItem = Get-Item -LiteralPath $source -Force
    if ($sourceItem.LinkType) {
        if ($sourceItem.Target -eq $destination) {
            $existingFiles = @(Get-ChildItem -LiteralPath $destination -Recurse -File -Force)
            $moved += [pscustomobject]@{ source = $source; destination = $destination; files = $existingFiles.Count; bytes = ($existingFiles | Measure-Object Length -Sum).Sum; already_moved = $true }
            continue
        }
        throw "Source already links elsewhere: $source"
    }
    if ((Test-Path -LiteralPath $destination) -and (Get-Item -LiteralPath $destination).LinkType) { throw "Destination must be a real D: directory: $destination" }
    if ($move.Name -eq 'android-sdk') {
        & (Join-Path $source 'platform-tools/adb.exe') kill-server
        if ($LASTEXITCODE -ne 0) { throw 'ADB could not stop before SDK relocation.' }
    }
    $active = Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase)
    }
    if ($active) { throw "A process still uses $source; close that tool before migration." }
    Write-Output "Copying $source to $destination"
    & robocopy $source $destination /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XJ /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) { throw "Copy failed; source retained: $source" }
    $verificationOutput = & python (Join-Path $PSScriptRoot 'verify-tool-copy.py') $source $destination
    if ($LASTEXITCODE -ne 0) { throw "Copy verification failed; source retained: $source" }
    $verification = $verificationOutput | ConvertFrom-Json
    [long]$bytes = $verification.bytes
    # Exact source and destination were validated above; every copied file has
    # matched SHA-256. Delete only this verified source, never a parent folder.
    Remove-Item -LiteralPath $source -Recurse -Force
    New-Item -ItemType Junction -Path $source -Target $destination | Out-Null
    $moved += [pscustomobject]@{ source = $source; destination = $destination; files = $verification.files; bytes = $bytes }
    Write-Output "Verified and relocated $($verification.files) files ($bytes bytes)."
}
$record = [pscustomobject]@{
    date = (Get-Date).ToString('o')
    moved = $moved
    c_free_before = $diskBefore
    c_free_after = (Get-PSDrive C).Free
    d_free_after = (Get-PSDrive D).Free
}
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $projectRoot 'docs/restaurant/storage-migration.json') -Encoding UTF8
$record | ConvertTo-Json -Depth 5
