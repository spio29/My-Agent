param(
  [Parameter(Mandatory = $true)]
  [string]$Prompt,
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$Timezone = "Asia/Jakarta",
  [switch]$UseAi,
  [switch]$ForceRuleBased,
  [switch]$NoRun,
  [int]$WaitSeconds = 2
)

$ErrorActionPreference = "Stop"

$clampedWait = [Math]::Max(0, [Math]::Min(30, $WaitSeconds))
$runImmediately = -not $NoRun.IsPresent

$payload = @{
  prompt = $Prompt
  timezone = $Timezone
  use_ai = [bool]$UseAi.IsPresent
  force_rule_based = [bool]$ForceRuleBased.IsPresent
  run_immediately = $runImmediately
  wait_seconds = if ($runImmediately) { $clampedWait } else { 0 }
}

$bodyJson = $payload | ConvertTo-Json -Depth 12 -Compress
$result = Invoke-RestMethod -Method Post -Uri "$BaseUrl/planner/execute" -ContentType "application/json" -Body $bodyJson

$result | ConvertTo-Json -Depth 12
