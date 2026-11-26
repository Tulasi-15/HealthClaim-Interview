param(
    [string]$Psql = 'C:\Program Files\PostgreSQL\18\bin\psql.exe',
    [string]$Admin = 'postgres',
    [string]$DatabaseName = 'healthcare_claims',
    [switch]$SetAppPassword
)

$ErrorActionPreference = 'Stop'
if ($DatabaseName -notmatch '^[a-z][a-z0-9_]{0,62}$') {
    throw 'Choose a database name containing lowercase letters, digits or underscores.'
}
if (-not (Test-Path -LiteralPath $Psql -PathType Leaf)) {
    throw 'PostgreSQL is not installed at the specified psql path.'
}

$connection = @('-h', '127.0.0.1', '-U', $Admin, '-X', '-v', 'ON_ERROR_STOP=1')
$exists = & $Psql @connection -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$DatabaseName'"
if ($LASTEXITCODE -ne 0) { throw 'Could not connect to PostgreSQL.' }
if ($exists -ne '1') {
    & $Psql @connection -d postgres -c "CREATE DATABASE $DatabaseName"
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the claims database.' }
}

& $Psql @connection -d $DatabaseName -f (Join-Path $PSScriptRoot '001_initial.sql')
if ($LASTEXITCODE -ne 0) { throw 'Could not apply the initial schema.' }

if ($SetAppPassword) {
    & $Psql @connection -d $DatabaseName -c '\password claims_app'
    if ($LASTEXITCODE -ne 0) { throw 'Could not set the application role password.' }
}
