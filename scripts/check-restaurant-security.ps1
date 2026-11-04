$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$scanTemp = Join-Path $projectRoot '.tools/tmp'
New-Item -ItemType Directory -Force -Path $scanTemp | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'test-results') | Out-Null
$env:TEMP = $scanTemp
$env:TMP = $scanTemp
$env:SEMGREP_SEND_METRICS = 'off'
$env:SEMGREP_ENABLE_VERSION_CHECK = '0'
& semgrep scan --error --metrics=off --disable-version-check --config semgrep.restaurant.yml --json --output test-results/restaurant-security.json restaurant src/vglpos/web/static/src/js/pos.js src/vglpos/web/static/src/js/dashboard.js src/vglpos/web/static/src/js/payment-view.js src/vglpos/web/static/src/js/payment-display.js src/vglpos/web/static/src/js/pos-icons.js src/vglpos/web/static/src/js/ui.js src/vglpos/web/static/src/js/i18n.js android/app/src/main/java/in/vgl/restaurant
if ($LASTEXITCODE -ne 0) { throw "Local security scan failed (exit $LASTEXITCODE). See test-results/restaurant-security.json." }
