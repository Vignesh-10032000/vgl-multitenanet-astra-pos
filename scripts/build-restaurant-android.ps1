param([switch]$SkipWebBuild, [switch]$Lint, [switch]$UnitTests)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not $env:JAVA_HOME) {
    $projectJdk = Get-ChildItem -LiteralPath (Join-Path $projectRoot '.tools/jdk') -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($projectJdk) { $env:JAVA_HOME = $projectJdk.FullName }
}
if (-not $env:JAVA_HOME -or -not (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin/java.exe'))) { throw 'Set JAVA_HOME to a JDK 21 installation.' }
$projectSdk = Join-Path $projectRoot '.tools/android-sdk'
if (Test-Path -LiteralPath $projectSdk) { $env:ANDROID_HOME = $projectSdk }
elseif (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android/Sdk' }
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$projectAndroidUser = Join-Path $projectRoot '.tools/android-user'
if (Test-Path -LiteralPath $projectAndroidUser) { $env:ANDROID_USER_HOME = $projectAndroidUser }
$env:PATH = (Join-Path $env:JAVA_HOME 'bin') + ';' + $env:PATH
# Windows JVM selectors need a native, short temporary socket path.
$projectTemp = Join-Path $projectRoot '.tools/tmp'
New-Item -ItemType Directory -Force -Path $projectTemp | Out-Null
$env:TEMP = $projectTemp
$env:TMP = $projectTemp
$env:JAVA_TOOL_OPTIONS = ($env:JAVA_TOOL_OPTIONS + " -Djdk.net.unixdomain.tmpdir=$projectTemp").Trim()
# Keep build caches inside this independent project.
$env:GRADLE_USER_HOME = Join-Path $projectRoot '.tools/gradle'
$env:npm_config_cache = Join-Path $projectRoot '.tools/npm-cache'
if (-not $SkipWebBuild) { & npm.cmd run build:restaurant; if ($LASTEXITCODE -ne 0) { throw 'Restaurant web build failed' } }
& npx.cmd cap sync android
if ($LASTEXITCODE -ne 0) { throw 'Capacitor sync failed' }
Set-Location -LiteralPath (Join-Path $projectRoot 'android')
try {
    $buildTasks = @(':app:assembleDebug')
    if ($Lint) { $buildTasks += ':app:lintDebug' }
    if ($UnitTests) { $buildTasks += ':app:testDebugUnitTest' }
    & .\gradlew.bat --no-daemon @buildTasks
    if ($LASTEXITCODE -ne 0) { throw 'Android build failed' }
} finally { Set-Location -LiteralPath $projectRoot }
