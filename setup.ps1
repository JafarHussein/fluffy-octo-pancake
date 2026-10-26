$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
Set-Location $Root

Write-Host "=== CareerForge Setup ===" -ForegroundColor Cyan

# Check required project files.
$requiredFiles = @(
    "requirements.txt",
    "docker-compose.yml",
    "database\schema.sql",
    "scripts\resume\strategy_engine.py",
    "config\resume-strategy.v1.json",
    "config\careerforge-style.v1.json",
    "config\ats-rule-catalog.v1.json",
    ".env.example"
)

foreach ($file in $requiredFiles) {
    if (!(Test-Path (Join-Path $Root $file))) {
        throw "Required file is missing: $file"
    }
}

# Check Python.
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Install Python and reopen PowerShell."
}

python --version
if ($LASTEXITCODE -ne 0) {
    throw "Python version check failed."
}

# Check Docker and Compose.
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found. Install Docker Desktop first."
}

docker compose version
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is unavailable."
}

# Create a local environment file without overwriting one.
if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example."
    Write-Host "Review .env and set a strong local database password before starting PostgreSQL."
} else {
    Write-Host "Existing .env preserved."
}

# Create a local Python virtual environment if needed.
if (!(Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Python virtual environment."
    }
} else {
    Write-Host "Existing Python virtual environment found."
}

# Install project dependencies in the virtual environment.
& ".\.venv\Scripts\python.exe" -m pip install -r ".\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed. See the pip output above."
}

# Check Python syntax without connecting to the database.
& ".\.venv\Scripts\python.exe" -m py_compile ".\scripts\resume\strategy_engine.py"
if ($LASTEXITCODE -ne 0) {
    throw "Strategy engine syntax validation failed."
}

Write-Host ""
Write-Host "Setup checks completed." -ForegroundColor Green
Write-Host "Next: review .env, then initialize the local database."
