param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "test", "audit-example", "lint", "help")]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"

function Invoke-Setup {
    python -m pip install -e ".[dev]"
}

function Invoke-Test {
    python -m pytest
}

function Invoke-AuditExample {
    python -m kolauda.cli.main audit --template .\examples\template.json --samples .\examples\samples
}

function Invoke-Lint {
    python -m ruff check src tests
}

function Show-Usage {
    Write-Host "EndpointKolauda task runner"
    Write-Host ""
    Write-Host "Usage: .\scripts\tasks.ps1 <task>"
    Write-Host ""
    Write-Host "Tasks:"
    Write-Host "  setup          Install project and development dependencies"
    Write-Host "  test           Run pytest"
    Write-Host "  audit-example  Run the CLI audit against ./examples"
    Write-Host "  lint           Run Ruff checks over src/ and tests/"
    Write-Host "  help           Show this message"
}

switch ($Task) {
    "setup" { Invoke-Setup }
    "test" { Invoke-Test }
    "audit-example" { Invoke-AuditExample }
    "lint" { Invoke-Lint }
    default { Show-Usage }
}

