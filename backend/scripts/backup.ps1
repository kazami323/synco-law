param(
    [string]$BackupRoot = ".\backups",
    [string]$ComposeFile = "",
    [string]$PostgresContainer = "",
    [string]$MinioContainer = "",
    [string]$DbUser = "legal_user",
    [string]$DbName = "legal_workspace",
    [string]$DbPassword = "secure_password"
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
if (-not $PostgresContainer -or -not $MinioContainer) {
    throw "Postgres and MinIO containers must be running before backup"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force -Path $target | Out-Null

$dbDump = Join-Path $target "postgres.dump"
$minioDir = Join-Path $target "minio-data"
$containerDump = "/tmp/synco-$stamp.dump"

Write-Host "Backing up Postgres to $dbDump"
docker exec -e "PGPASSWORD=$DbPassword" $PostgresContainer `
    pg_dump -U $DbUser -d $DbName -Fc -f $containerDump
docker cp "${PostgresContainer}:$containerDump" $dbDump

Write-Host "Copying MinIO data to $minioDir"
docker cp "${MinioContainer}:/data" $minioDir

@{
    created_at = (Get-Date).ToString("o")
    db_name = $DbName
    postgres_container = $PostgresContainer
    minio_container = $MinioContainer
    notes = "Elasticsearch indexes are rebuilt from Postgres with scripts/reindex_search.py and scripts/reindex_laws.py."
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $target "manifest.json")

Write-Host "Backup complete: $target"
