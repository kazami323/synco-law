param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$ComposeFile = "",
    [string]$PostgresContainer = "",
    [string]$MinioContainer = "",
    [string]$DbUser = "legal_user",
    [string]$DbName = "legal_workspace",
    [string]$DbPassword = "secure_password",
    [switch]$RestoreMinio
)

$ErrorActionPreference = "Stop"

if (-not $ComposeFile) {
    $ComposeFile = Join-Path $PSScriptRoot "..\..\docker-compose.yml"
}
if (-not $PostgresContainer) {
    $PostgresContainer = docker compose -f $ComposeFile ps -q postgres
}
if (-not $MinioContainer) {
    $MinioContainer = docker compose -f $ComposeFile ps -q minio
}
if (-not $PostgresContainer) {
    throw "Postgres container must be running before restore"
}
if ($RestoreMinio -and -not $MinioContainer) {
    throw "MinIO container must be running before restore"
}

$resolvedBackup = Resolve-Path -LiteralPath $BackupPath
$dbDump = Join-Path $resolvedBackup "postgres.dump"
$minioDir = Join-Path $resolvedBackup "minio-data"

if (-not (Test-Path -LiteralPath $dbDump)) {
    throw "Postgres dump not found: $dbDump"
}

Write-Host "Restoring Postgres from $dbDump"
$containerDump = "/tmp/synco-restore.dump"
docker cp $dbDump "${PostgresContainer}:$containerDump"
docker exec -e "PGPASSWORD=$DbPassword" $PostgresContainer `
    pg_restore -U $DbUser -d $DbName --clean --if-exists $containerDump

if ($RestoreMinio) {
    if (-not (Test-Path -LiteralPath $minioDir)) {
        throw "MinIO backup folder not found: $minioDir"
    }
    Write-Host "Restoring MinIO data from $minioDir"
    docker cp $minioDir "${MinioContainer}:/data"
}

Write-Host "Restore complete. Rebuild indexes:"
Write-Host "  python -m scripts.reindex_search"
Write-Host "  python -m scripts.reindex_laws"
