$ErrorActionPreference = 'Stop'

$backend = 'C:\Users\Dell\Trabot\backend'
$dataDir = Join-Path $backend 'data'
$envPath = Join-Path $backend '.env'
$stamp = '20261118-100544'

$equityReport = Join-Path $dataDir "nifty500_upstox_equity_keys-$stamp.csv"
$optionsReport = Join-Path $dataDir "nifty500_stocks_with_options-$stamp.csv"

if (-not (Test-Path -LiteralPath $envPath)) { throw "Missing .env: $envPath" }
if (-not (Test-Path -LiteralPath $equityReport)) { throw "Missing report: $equityReport" }
if (-not (Test-Path -LiteralPath $optionsReport)) { throw "Missing report: $optionsReport" }

$backup = "$envPath.repair-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item -LiteralPath $envPath -Destination $backup

$envLines = [System.Collections.Generic.List[string]]::new()
[System.IO.File]::ReadAllLines($envPath) | ForEach-Object { $envLines.Add($_) }

function Get-EnvValue([string]$Name) {
  $pattern = '^\s*' + [regex]::Escape($Name) + '\s*=\s*(.*)$'
  foreach ($line in $envLines) {
    if ($line -match $pattern) {
      return $Matches[1].Trim().Trim('"').Trim("'")
    }
  }
  return ''
}

function Set-EnvValue([string]$Name, [string]$Value) {
  $pattern = '^\s*' + [regex]::Escape($Name) + '\s*='
  $indexes = @(
    for ($i = 0; $i -lt $envLines.Count; $i++) {
      if ($envLines[$i] -match $pattern) { $i }
    }
  )

  if ($indexes.Count -eq 0) {
    $envLines.Add("$Name=$Value")
  }
  else {
    $envLines[$indexes[0]] = "$Name=$Value"
    for ($i = $indexes.Count - 1; $i -ge 1; $i--) {
      $envLines.RemoveAt($indexes[$i])
    }
  }
}

# Reuse the configured watchlist path; otherwise use the default data file.
$watchlistSetting = Get-EnvValue 'UPSTOX_INSTRUMENT_KEYS_FILE'
$watchlistPath = Join-Path $dataDir 'nifty500_instrument_keys.txt'

if ($watchlistSetting) {
  if ([System.IO.Path]::IsPathRooted($watchlistSetting)) {
    $watchlistPath = $watchlistSetting
  }
  else {
    $watchlistPath = Join-Path $backend $watchlistSetting
  }
}

$watchlistParent = Split-Path -Parent $watchlistPath
New-Item -ItemType Directory -Force -Path $watchlistParent | Out-Null

$existingText = ''
if (Test-Path -LiteralPath $watchlistPath) {
  $existingText = [System.IO.File]::ReadAllText($watchlistPath)
}

$keySet = [System.Collections.Generic.HashSet[string]]::new(
  [System.StringComparer]::OrdinalIgnoreCase
)
foreach ($key in ($existingText -split '[,\r\n]+')) {
  if ($key.Trim()) { [void]$keySet.Add($key.Trim()) }
}

$equityRows = Import-Csv -LiteralPath $equityReport
$symbolMapPath = Join-Path $dataDir 'upstox_instrument_symbols.json'
$symbolMap = [System.Collections.Generic.Dictionary[string,string]]::new(
  [System.StringComparer]::OrdinalIgnoreCase
)
if (Test-Path -LiteralPath $symbolMapPath) {
  try {
    $savedMap = Get-Content -LiteralPath $symbolMapPath -Raw | ConvertFrom-Json
    foreach ($property in $savedMap.PSObject.Properties) {
      if ($property.Name -and $property.Value) { $symbolMap[$property.Name] = [string]$property.Value }
    }
  } catch { throw "Could not parse existing instrument symbol map: $symbolMapPath" }
}
foreach ($row in $equityRows) {
  if ($row.InstrumentKey -and $row.Symbol) { $symbolMap[$row.InstrumentKey.Trim()] = $row.Symbol.Trim() }
}
[System.IO.File]::WriteAllText(
  $symbolMapPath,
  ($symbolMap | ConvertTo-Json -Depth 4),
  [System.Text.UTF8Encoding]::new($false)
)
$symbolMapSetting = Get-EnvValue 'UPSTOX_SYMBOL_MAP_FILE'
if (-not $symbolMapSetting) { Set-EnvValue 'UPSTOX_SYMBOL_MAP_FILE' 'data/upstox_instrument_symbols.json' }
$newKeys = @(
  foreach ($row in $equityRows) {
    $key = $row.InstrumentKey.Trim()
    if ($key -and $keySet.Add($key)) { $key }
  }
)

if ($newKeys.Count -gt 0) {
  $appendText = ''
  if ($existingText.Length -gt 0 -and
      -not $existingText.EndsWith("`n") -and
      -not $existingText.EndsWith("`r")) {
    $appendText = [Environment]::NewLine
  }
  $appendText += ($newKeys -join [Environment]::NewLine) + [Environment]::NewLine
  [System.IO.File]::AppendAllText(
    $watchlistPath,
    $appendText,
    [System.Text.UTF8Encoding]::new($false)
  )
}

Set-EnvValue 'UPSTOX_INSTRUMENT_KEYS_FILE' ('"' + $watchlistPath + '"')

$existingOptions = @(
  (Get-EnvValue 'UPSTOX_OPTION_UNDERLYING_KEYS' -split ',' |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ } |
    Select-Object -Unique)
)
if ($existingOptions.Count -eq 0) {
  $existingOptions = @('NSE_INDEX|Nifty 50', 'NSE_INDEX|Nifty Bank')
}

$optionSet = [System.Collections.Generic.HashSet[string]]::new(
  [System.StringComparer]::OrdinalIgnoreCase
)
foreach ($key in $existingOptions) { [void]$optionSet.Add($key) }

$slots = [Math]::Max(0, 10 - $existingOptions.Count)
$optionRows = Import-Csv -LiteralPath $optionsReport
$addedOptions = @(
  $optionRows |
    Where-Object { $_.InstrumentKey -and -not $optionSet.Contains($_.InstrumentKey) } |
    Select-Object -First $slots |
    ForEach-Object {
      [void]$optionSet.Add($_.InstrumentKey)
      $_.InstrumentKey
    }
)

$allOptions = @($existingOptions + $addedOptions | Select-Object -Unique)
Set-EnvValue 'UPSTOX_OPTION_UNDERLYING_KEYS' ('"' + ($allOptions -join ',') + '"')

[System.IO.File]::WriteAllLines(
  $envPath,
  $envLines,
  [System.Text.UTF8Encoding]::new($false)
)

"Equity keys appended: $($newKeys.Count)"
"Option underlyings added: $($addedOptions.Count)"
"Watchlist file: $watchlistPath"
"Instrument symbol map: $symbolMapPath"
".env backup: $backup"
"Full equity report: $equityReport"
"Full options report: $optionsReport"
