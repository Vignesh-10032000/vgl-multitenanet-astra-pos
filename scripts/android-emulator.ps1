param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('start', 'stop', 'install', 'logs')][string]$Action,
    [string]$ApkPath,
    [string]$Package = 'in.vgl.restaurant',
    [switch]$Dump,
    [int]$TimeoutSeconds = 600
)
$ErrorActionPreference = 'Stop'
$sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { 'D:\Android\Sdk' }
$avdHome = if ($env:ANDROID_AVD_HOME) { $env:ANDROID_AVD_HOME } else { 'D:\Android\avd' }
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:ANDROID_AVD_HOME = $avdHome
$env:ANDROID_USER_HOME = 'D:\Android\home'
$env:ANDROID_EMULATOR_HOME = $env:ANDROID_USER_HOME
$env:TEMP = 'D:\Android\tmp'
$env:TMP = $env:TEMP
$adb = Join-Path $sdk 'platform-tools\adb.exe'
$emulator = Join-Path $sdk 'emulator\emulator.exe'
$serial = 'emulator-5554'
$avdName = 'tvs_pos'
$logRoot = 'D:\Android\logs'
$pidFile = Join-Path $logRoot 'tvs_pos.pid'
$dataImage = Join-Path $avdHome 'tvs_pos.avd\userdata-pos-2g.img'
foreach ($path in @($adb, $emulator)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing Android tool: $path" }
}
New-Item -ItemType Directory -Path $logRoot, $env:TEMP -Force | Out-Null

function Get-DeviceState {
    $listing = & $adb devices
    if ($LASTEXITCODE -ne 0) { throw 'adb devices failed' }
    foreach ($line in $listing) {
        if ($line -match '^emulator-5554\s+(\S+)') { return $Matches[1] }
    }
    return ''
}
function Assert-TvsAvd {
    if ((Get-DeviceState) -ne 'device') { throw 'tvs_pos is not connected; run start_emulator.sh first' }
    $name = & $adb -s $serial emu avd name
    if ($LASTEXITCODE -ne 0 -or $name[0].Trim() -ne $avdName) {
        throw 'Port 5554 belongs to another AVD; refusing to operate on it'
    }
}
function Wait-ForBoot {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0
    while ((Get-Date) -lt $deadline) {
        if ((Get-DeviceState) -eq 'device') {
            $boot = (& $adb -s $serial shell getprop sys.boot_completed 2>$null | Out-String).Trim()
            if ($boot -eq '1') {
                Assert-TvsAvd
                Write-Output "BOOT_COMPLETED=1 SERIAL=$serial AVD=$avdName"
                & $adb -s $serial shell getprop ro.build.version.release
                return
            }
        }
        $attempt++
        if ($attempt % 6 -eq 0) { Write-Output "Waiting for $avdName to finish booting..." }
        if (Test-Path -LiteralPath $pidFile) {
            $emulatorPid = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
            if (-not (Get-Process -Id $emulatorPid -ErrorAction SilentlyContinue)) {
                Get-Content -LiteralPath (Join-Path $logRoot 'tvs_pos-stderr.log') -Tail 20
                throw 'Emulator process exited before boot completed'
            }
        }
        Start-Sleep -Seconds 5
    }
    throw "Emulator boot timed out after $TimeoutSeconds seconds. Inspect D:\Android\logs"
}

switch ($Action) {
    'start' {
        $state = Get-DeviceState
        if ($state -eq 'device') { Assert-TvsAvd; Wait-ForBoot; exit 0 }
        $alreadyStarting = $false
        if (Test-Path -LiteralPath $pidFile) {
            $emulatorPid = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$emulatorPid"
            if ($process -and $process.CommandLine -match 'tvs_pos') { $alreadyStarting = $true }
        }
        if (-not $alreadyStarting) {
            if ($state) { throw "Port 5554 is occupied ($state); inspect the running emulator" }
            if (-not (Test-Path -LiteralPath $dataImage)) { throw "Prepared 2GB test disk missing: $dataImage" }
            $driveName = ([IO.Path]::GetPathRoot($avdHome)).TrimEnd('\').TrimEnd(':')
            if ((Get-PSDrive -Name $driveName).Free -lt 5GB) {
                throw 'Android Emulator requires at least 5 GiB of host free space. Free space on the AVD drive before starting.'
            }
            $arguments = @('-avd', $avdName, '-no-window', '-no-audio', '-no-snapshot',
                '-gpu', 'swiftshader_indirect', '-port', '5554', '-no-metrics',
                '-feature', '-QuickbootFileBacked', '-partition-size', '2047', '-data', $dataImage)
            $process = Start-Process -FilePath $emulator -ArgumentList $arguments -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $logRoot 'tvs_pos-stdout.log') `
                -RedirectStandardError (Join-Path $logRoot 'tvs_pos-stderr.log') -PassThru
            $process.Id | Set-Content -LiteralPath $pidFile
            Write-Output "STARTED_PID=$($process.Id)"
        }
        Wait-ForBoot
    }
    'stop' {
        if (-not (Get-DeviceState)) { Write-Output 'Emulator already stopped'; exit 0 }
        Assert-TvsAvd
        & $adb -s $serial emu kill
        if ($LASTEXITCODE -ne 0) { throw 'Graceful emulator shutdown failed' }
        $deadline = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $deadline) {
            $alive = $false
            if (Test-Path -LiteralPath $pidFile) {
                $emulatorPid = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
                $alive = $null -ne (Get-Process -Id $emulatorPid -ErrorAction SilentlyContinue)
            }
            if (-not (Get-DeviceState) -and -not $alive) {
                Write-Output "STOPPED=$avdName"
                exit 0
            }
            Start-Sleep -Seconds 2
        }
        throw 'Emulator shutdown did not finish within 60 seconds'
    }
    'install' {
        Assert-TvsAvd
        if (-not $ApkPath -or -not (Test-Path -LiteralPath $ApkPath -PathType Leaf)) {
            throw 'Supply an existing APK: install_apk.sh <apk>'
        }
        $resolved = (Resolve-Path -LiteralPath $ApkPath).Path
        if ([IO.Path]::GetExtension($resolved) -ne '.apk') { throw 'Expected an .apk file' }
        & $adb -s $serial install -r --no-streaming $resolved
        if ($LASTEXITCODE -ne 0) { throw 'APK installation failed' }
        & $adb -s $serial shell pm path $Package
        if ($LASTEXITCODE -ne 0) { throw "Package not found after installation: $Package" }
        Write-Output "INSTALLED_PACKAGE=$Package"
    }
    'logs' {
        Assert-TvsAvd
        if ($Package -notmatch '^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$') { throw 'Invalid package identifier' }
        $appPid = (& $adb -s $serial shell pidof -s $Package | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $appPid -notmatch '^\d+$') {
            throw "Package $Package is not running. Launch it before collecting PID-filtered logs."
        }
        Write-Output "LOG_PACKAGE=$Package PID=$appPid SERIAL=$serial"
        $arguments = @('-s', $serial, 'logcat', "--pid=$appPid", '-v', 'threadtime')
        if ($Dump) { $arguments += @('-d', '-t', '200') }
        & $adb @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Filtered logcat failed' }
    }
}
