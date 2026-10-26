$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\")).Path
Set-Location $Root

if (-not (Test-Path ".env")) {
    throw ".env is missing. Run .\setup.ps1 first and review .env."
}

# Load local settings without printing their values.
$envValues = @{}

foreach ($line in Get-Content ".env") {
    $trimmed = $line.Trim()

    if (-not $trimmed -or $trimmed.StartsWith("#")) {
        continue
    }

    if ($trimmed -match '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $key = $Matches[1]
        $value = $Matches[2].Trim()

        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        $envValues[$key] = $value
    }
}

foreach ($required in @("POSTGRES_USER", "POSTGRES_DB")) {
    if (-not $envValues.ContainsKey($required) -or
        [string]::IsNullOrWhiteSpace($envValues[$required])) {
        throw "Missing $required in .env."
    }
}

$env:POSTGRES_USER = $envValues["POSTGRES_USER"]
$env:POSTGRES_DB = $envValues["POSTGRES_DB"]

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is not running. Start Docker Desktop and retry."
}

docker compose up -d postgres
if ($LASTEXITCODE -ne 0) {
    throw "Could not start PostgreSQL."
}

Write-Host "Waiting for PostgreSQL..."
$healthy = $false

for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T postgres pg_isready *> $null

    if ($LASTEXITCODE -eq 0) {
        $healthy = $true
        break
    }

    Start-Sleep -Seconds 2
}

if (-not $healthy) {
    throw "PostgreSQL did not become ready within 60 seconds."
}

$tables = docker compose exec -T postgres psql `
    -U $env:POSTGRES_USER `
    -d $env:POSTGRES_DB `
    -Atc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"

if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect database tables. Check .env and database logs."
}

if ([int]$tables.Trim() -gt 0) {
    throw "The database already contains public tables. Schema was not applied."
}

docker compose exec -T postgres psql `
    -v ON_ERROR_STOP=1 `
    -U $env:POSTGRES_USER `
    -d $env:POSTGRES_DB `
    -f /careerforge-database/schema.sql

if ($LASTEXITCODE -ne 0) {
    throw "Schema initialization failed. Inspect the database before retrying."
}

Write-Host "Database schema initialized successfully."
