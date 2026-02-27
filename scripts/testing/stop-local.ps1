$ErrorActionPreference = "SilentlyContinue"

$Root = $PSScriptRoot
$LogDir = Join-Path $Root "runtime-logs"

function Stop-ByPidFile {
  param([string]$Name)

  $pidFile = Join-Path $LogDir "$Name.pid"
  if (-not (Test-Path $pidFile)) {
    return
  }

  $pidText = (Get-Content $pidFile | Select-Object -First 1)
  $pidValue = 0
  if ([int]::TryParse($pidText, [ref]$pidValue)) {
    $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($proc) {
      Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
      Write-Host "[SPIO] Stop $Name (PID $pidValue)"
    }
  }

  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $LogDir)) {
  Write-Host "[SPIO] Tidak ada proses yang tercatat."
  exit 0
}

Stop-ByPidFile "api"
Stop-ByPidFile "worker"
Stop-ByPidFile "scheduler"
Stop-ByPidFile "connector"
Stop-ByPidFile "ui"

Write-Host "[SPIO] Proses lokal sudah dihentikan."
