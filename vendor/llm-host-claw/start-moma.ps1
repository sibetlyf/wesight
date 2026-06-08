param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$defaultConfig = Join-Path $scriptDir "config.json"

if (-not (Test-Path -LiteralPath $defaultConfig)) {
    throw "Default config file not found: $defaultConfig"
}

$env:PYTHONPATH = "src"

$resolvedArgs = @()
if ($CliArgs.Count -eq 0) {
    $resolvedArgs = @("--config", $defaultConfig, "chat")
} else {
    $hasConfigArg = $false
    foreach ($arg in $CliArgs) {
        if ($arg -eq "--config") {
            $hasConfigArg = $true
            break
        }
    }

    if (-not $hasConfigArg) {
        $resolvedArgs += @("--config", $defaultConfig)
    }
    $resolvedArgs += $CliArgs
}

& "uv" "run" "python" "-u" "-m" "moma_cli" @resolvedArgs
$exitCode = $LASTEXITCODE
exit $exitCode
