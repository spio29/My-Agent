param(
  [switch]$SkipUiBuild
)

$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$UiRoot = Join-Path $Root "ui"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "runtime-logs"

function Write-Info {
  param([string]$Message)
  Write-Host "[SPIO] $Message"
}

function Write-WarnMsg {
  param([string]$Message)
  Write-Host "[SPIO] $Message" -ForegroundColor Yellow
}

function Stop-ByPidFile {
  param([string]$Name)

  $pidFile = Join-Path $LogDir "$Name.pid"
  if (-not (Test-Path $pidFile)) {
    return
  }

  $pidText = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($pidText) {
    $pidValue = 0
    if ([int]::TryParse($pidText, [ref]$pidValue)) {
      $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
      if ($proc) {
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
      }
    }
  }

  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

function Start-ServiceProcess {
  param(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory
  )

  $outLog = Join-Path $LogDir "$Name.out.log"
  $errLog = Join-Path $LogDir "$Name.err.log"
  $pidFile = Join-Path $LogDir "$Name.pid"

  if (Test-Path $outLog) { Remove-Item $outLog -Force -ErrorAction SilentlyContinue }
  if (Test-Path $errLog) { Remove-Item $errLog -Force -ErrorAction SilentlyContinue }

  $proc = Start-Process `
    -FilePath $FilePath `
    -ArgumentList $ArgumentList `
    -WorkingDirectory $WorkingDirectory `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

  $proc.Id | Set-Content $pidFile
  return $proc
}

function Test-Url {
  param(
    [string]$Url,
    [int]$TimeoutSeconds = 30
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
      if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
        return $true
      }
    } catch {
    }
    Start-Sleep -Milliseconds 1000
  }

  return $false
}

if (-not (Test-Path $VenvPython)) {
  throw "Python venv tidak ditemukan di '$VenvPython'. Jalankan: python -m venv .venv lalu .\.venv\Scripts\python.exe -m pip install -e ."
}

if (-not (Test-Path $UiRoot)) {
  throw "Folder UI tidak ditemukan di '$UiRoot'."
}

if (-not (Test-Path $LogDir)) {
  New-Item -ItemType Directory -Path $LogDir | Out-Null
}

Write-Info "Membersihkan proses lama..."
Stop-ByPidFile "api"
Stop-ByPidFile "worker"
Stop-ByPidFile "scheduler"
Stop-ByPidFile "connector"
Stop-ByPidFile "ui"

if (-not (Test-Path (Join-Path $UiRoot "node_modules"))) {
  Write-Info "node_modules belum ada, menjalankan npm install..."
  Push-Location $UiRoot
  try {
    & npm install
  } finally {
    Pop-Location
  }
}

if (-not $SkipUiBuild) {
  Write-Info "Menjalankan build UI..."
  Push-Location $UiRoot
  try {
    & npm run build
  } finally {
    Pop-Location
  }
}

Write-Info "Menjalankan API..."
$api = Start-ServiceProcess -Name "api" -FilePath $VenvPython -ArgumentList @("-m", "uvicorn", "app.services.api.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $Root

Write-Info "Menjalankan worker..."
$worker = Start-ServiceProcess -Name "worker" -FilePath $VenvPython -ArgumentList @("-m", "app.services.worker.main") -WorkingDirectory $Root

Write-Info "Menjalankan scheduler..."
$scheduler = Start-ServiceProcess -Name "scheduler" -FilePath $VenvPython -ArgumentList @("-m", "app.services.scheduler.main") -WorkingDirectory $Root

Write-Info "Menjalankan connector..."
$connector = Start-ServiceProcess -Name "connector" -FilePath $VenvPython -ArgumentList @("-m", "app.services.connector.main") -WorkingDirectory $Root

Write-Info "Menjalankan UI..."
$ui = Start-ServiceProcess -Name "ui" -FilePath "cmd.exe" -ArgumentList @("/c", "npm run serve") -WorkingDirectory $UiRoot

$apiOk = Test-Url -Url "http://127.0.0.1:8000/healthz" -TimeoutSeconds 25
$uiOk = Test-Url -Url "http://127.0.0.1:3000" -TimeoutSeconds 35

Write-Host ""
if ($apiOk -and $uiOk) {
  Write-Host "[SPIO] Semua service berhasil jalan." -ForegroundColor Green
  Write-Host "[SPIO] API: http://127.0.0.1:8000/healthz"
  Write-Host "[SPIO] UI : http://127.0.0.1:3000"
} else {
  Write-WarnMsg "Ada service yang belum sehat. Cek log di: $LogDir"
  if (-not $apiOk) {
    Write-WarnMsg "API belum merespons /healthz"
  }
  if (-not $uiOk) {
    Write-WarnMsg "UI belum merespons port 3000"
  }
}

Write-Host ""
Write-Host "[SPIO] PID API      : $($api.Id)"
Write-Host "[SPIO] PID Worker   : $($worker.Id)"
Write-Host "[SPIO] PID Scheduler: $($scheduler.Id)"
Write-Host "[SPIO] PID Connector: $($connector.Id)"
Write-Host "[SPIO] PID UI       : $($ui.Id)"
Write-Host "[SPIO] Log folder   : $LogDir"
