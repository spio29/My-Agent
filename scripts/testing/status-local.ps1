param(
  [int]$Tail = 20
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$LogDir = Join-Path $Root "runtime-logs"

function Get-ServiceState {
  param([string]$Name)

  $pidFile = Join-Path $LogDir "$Name.pid"
  if (-not (Test-Path $pidFile)) {
    return [PSCustomObject]@{
      Name = $Name
      Pid = "-"
      Running = "Tidak"
    }
  }

  $pidText = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $pidText) {
    return [PSCustomObject]@{
      Name = $Name
      Pid = "-"
      Running = "Tidak"
    }
  }

  $pidValue = 0
  $ok = [int]::TryParse($pidText, [ref]$pidValue)
  if (-not $ok) {
    return [PSCustomObject]@{
      Name = $Name
      Pid = $pidText
      Running = "Tidak"
    }
  }

  $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
  return [PSCustomObject]@{
    Name = $Name
    Pid = $pidValue
    Running = if ($proc) { "Ya" } else { "Tidak" }
  }
}

function Test-UrlStatus {
  param([string]$Url)
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
    return "$($resp.StatusCode)"
  } catch {
    return "Gagal"
  }
}

if (-not (Test-Path $LogDir)) {
  Write-Host "[SPIO] Belum ada runtime-logs. Jalankan start-local.ps1 dulu."
  exit 0
}

$rows = @(
  Get-ServiceState "api"
  Get-ServiceState "worker"
  Get-ServiceState "scheduler"
  Get-ServiceState "connector"
  Get-ServiceState "ui"
)

Write-Host "[SPIO] Status proses"
$rows | Format-Table -AutoSize

$apiStatus = Test-UrlStatus "http://127.0.0.1:8000/healthz"
$uiStatus = Test-UrlStatus "http://127.0.0.1:3000"

Write-Host "[SPIO] Cek endpoint API /healthz : $apiStatus"
Write-Host "[SPIO] Cek endpoint UI /         : $uiStatus"

$errFiles = @(
  "api.err.log",
  "worker.err.log",
  "scheduler.err.log",
  "connector.err.log",
  "ui.err.log"
)

Write-Host ""
Write-Host "[SPIO] Ringkasan error log (tail $Tail baris)"
foreach ($file in $errFiles) {
  $path = Join-Path $LogDir $file
  if (Test-Path $path) {
    Write-Host "--- $file ---"
    Get-Content -Tail $Tail $path
  }
}
