param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$ComposeFile = "",
    [string]$DbUser = "legal_user",
    [string]$DbPassword = "secure_password"
)

$ErrorActionPreference = "Stop"
if (-not $ComposeFile) {
    $ComposeFile = Join-Path $PSScriptRoot "..\..\docker-compose.yml"
}
$resolvedBackup = Resolve-Path -LiteralPath $BackupPath
$dbDump = Join-Path $resolvedBackup "postgres.dump"
if (-not (Test-Path -LiteralPath $dbDump)) {
    throw "Postgres dump not found: $dbDump"
}

$testDb = "restore_check_$(Get-Date -Format 'yyyyMMddHHmmss')"
$containerDump = "/tmp/$testDb.dump"
try {
    docker compose -f $ComposeFile exec -T postgres `
        psql -U $DbUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $testDb"

    $postgresContainer = docker compose -f $ComposeFile ps -q postgres
    if (-not $postgresContainer) {
        throw "Postgres container is not running"
    }
    docker cp $dbDump "${postgresContainer}:$containerDump"
    docker compose -f $ComposeFile exec -T -e "PGPASSWORD=$DbPassword" postgres `
        pg_restore -U $DbUser -d $testDb --exit-on-error $containerDump

    docker compose -f $ComposeFile exec -T postgres `
        psql -U $DbUser -d $testDb -v ON_ERROR_STOP=1 `
        -c "SELECT count(*) AS users FROM users; SELECT count(*) AS legal_articles FROM legal_articles;"
    Write-Host "Restore verification passed: $testDb"
}
finally {
    docker compose -f $ComposeFile exec -T postgres `
        psql -U $DbUser -d postgres -c "DROP DATABASE IF EXISTS $testDb WITH (FORCE)"
}
