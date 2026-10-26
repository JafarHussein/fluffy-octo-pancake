
[CmdletBinding()]
param(
    [string]$JobDescriptionPath = ".\input\job_description.txt"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

Write-Host "=== CareerForge Resume Strategy ===" -ForegroundColor Cyan

# Define project paths.
$engine = Join-Path $Root "scripts\resume\strategy_engine.py"
$config = Join-Path $Root "config\resume-strategy.v1.json"
$envFile = Join-Path $Root ".env"
$python = Join-Path $Root ".venv\Scripts\python.exe"

# Validate required project files.
if (!(Test-Path -LiteralPath $engine -PathType Leaf)) {
    throw "Strategy engine not found: $engine"
}

if (!(Test-Path -LiteralPath $config -PathType Leaf)) {
    throw "Strategy configuration not found: $config"
}

if (!(Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Local .env not found. Run .\setup.ps1 first and configure your database credentials."
}

if (!(Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project Python environment not found. Run .\setup.ps1 first."
}

# Load KEY=value entries from .env into this process.
# Child processes, including Python, inherit these variables.
Get-Content -LiteralPath $envFile | ForEach-Object {
    $line = $_.Trim()

    if (!$line -or $line.StartsWith("#")) {
        return
    }

    $separator = $line.IndexOf("=")

    if ($separator -lt 1) {
        return
    }

    $name = $line.Substring(0, $separator).Trim()
    $value = $line.Substring($separator + 1).Trim()

    # Ignore invalid environment variable names.
    if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        return
    }

    # Remove matching surrounding quotes, if present.
    if (
        $value.Length -ge 2 -and
        (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        )
    ) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    [Environment]::SetEnvironmentVariable(
        $name,
        $value,
        [EnvironmentVariableTarget]::Process
    )
}

# Validate database settings without displaying credentials.
$requiredVariables = @(
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD"
)

foreach ($variable in $requiredVariables) {
    $value = [Environment]::GetEnvironmentVariable(
        $variable,
        [EnvironmentVariableTarget]::Process
    )

    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required environment variable '$variable' is missing or empty in .env."
    }
}

Write-Host "Environment configuration loaded." -ForegroundColor Green

# Resolve the job description relative to the project directory.
if (![System.IO.Path]::IsPathRooted($JobDescriptionPath)) {
    $JobDescriptionPath = Join-Path $Root $JobDescriptionPath
}

if (!(Test-Path -LiteralPath $JobDescriptionPath -PathType Leaf)) {
    throw "Job description not found: $JobDescriptionPath. Create this file with the target job description."
}

if ((Get-Item -LiteralPath $JobDescriptionPath).Length -eq 0) {
    throw "Job description file is empty."
}

Write-Host "Job description validated." -ForegroundColor Green

# Validate Python syntax before running the engine.
Write-Host "Checking strategy engine syntax..." -ForegroundColor Cyan

& $python -m py_compile $engine

if ($LASTEXITCODE -ne 0) {
    throw "Strategy engine syntax validation failed."
}

# Run the strategy engine.
Write-Host "Running resume strategy engine..." -ForegroundColor Cyan

& $python $engine

if ($LASTEXITCODE -ne 0) {
    throw "Strategy engine failed. Review the error output above."
}

Write-Host "Strategy engine completed." -ForegroundColor Green
Write-Host "Review the strategy report under output\strategy."
