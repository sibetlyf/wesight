param(
    [switch]$Dev,
    [switch]$WithBrowsers
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "src"

$args = @("run", "python", "-u", "-m", "moma_cli", "init")
if ($Dev) {
    $args += "--dev"
}
if ($WithBrowsers) {
    $args += "--with-browsers"
}

& "uv" @args
$exitCode = $LASTEXITCODE
exit $exitCode
