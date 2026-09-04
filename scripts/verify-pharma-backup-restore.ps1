[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Container })]
    [string]$EvidenceDirectory,

    [Parameter(Mandatory = $true)]
    [switch]$AcknowledgeIsolatedRestoreTarget
)

$ErrorActionPreference = 'Stop'

if (-not $env:SOURCE_DATABASE_URL -or -not $env:RESTORE_DATABASE_URL) {
    throw 'Set SOURCE_DATABASE_URL and RESTORE_DATABASE_URL through the approved secret channel.'
}
if ($env:SOURCE_DATABASE_URL -eq $env:RESTORE_DATABASE_URL) {
    throw 'The restore target must not be the source database.'
}
if (-not $AcknowledgeIsolatedRestoreTarget) {
    throw 'Explicit isolated-target acknowledgement is required.'
}

$resolvedEvidence = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$dumpPath = Join-Path $resolvedEvidence "pharma-agent-os-$stamp.dump"
$hashPath = "$dumpPath.sha256"
$countsPath = Join-Path $resolvedEvidence "pharma-agent-os-$stamp-counts.txt"

# Refuse a populated target, including source aliases that evade URL comparison.
$targetTables = & psql $env:RESTORE_DATABASE_URL --no-psqlrc --tuples-only --no-align --set=ON_ERROR_STOP=1 --command="SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
if ($LASTEXITCODE -ne 0 -or [int]$targetTables -ne 0) {
    throw 'Restore target must be a newly created empty database.'
}

& pg_dump $env:SOURCE_DATABASE_URL --format=custom --no-owner --no-acl --file=$dumpPath
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed.' }

$digest = (Get-FileHash -LiteralPath $dumpPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $hashPath -Value "$digest  $([IO.Path]::GetFileName($dumpPath))" -Encoding ascii

# Never drop or replace existing objects. Stop at the first restore error.
& pg_restore --dbname=$env:RESTORE_DATABASE_URL --exit-on-error --no-owner --no-acl $dumpPath
if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed.' }

$verificationSql = @'
SELECT 'agent_cases', count(*) FROM agent_cases
UNION ALL SELECT 'case_runs', count(*) FROM case_runs
UNION ALL SELECT 'approval_requests', count(*) FROM approval_requests
UNION ALL SELECT 'artifact_versions', count(*) FROM artifact_versions
UNION ALL SELECT 'run_events', count(*) FROM run_events
UNION ALL SELECT 'durable_activities', count(*) FROM durable_activities
UNION ALL SELECT 'platform_controls', count(*) FROM platform_controls
UNION ALL SELECT 'integration_outbox', count(*) FROM integration_outbox
UNION ALL SELECT 'a2a_exchanges', count(*) FROM a2a_exchanges
ORDER BY 1;
'@
$sourceCounts = $verificationSql | & psql $env:SOURCE_DATABASE_URL --no-psqlrc --tuples-only --no-align --set=ON_ERROR_STOP=1 --file=-
if ($LASTEXITCODE -ne 0) { throw 'Source verification query failed.' }
$restoredCounts = $verificationSql | & psql $env:RESTORE_DATABASE_URL --no-psqlrc --tuples-only --no-align --set=ON_ERROR_STOP=1 --file=-
if ($LASTEXITCODE -ne 0) { throw 'Restore verification query failed.' }
if (Compare-Object $sourceCounts $restoredCounts) {
    throw 'Source and restored counts differ; use a quiescent source for this drill.'
}
$restoredCounts | Set-Content -LiteralPath $countsPath -Encoding utf8

[pscustomobject]@{
    DumpPath = $dumpPath
    Sha256 = $digest
    VerificationEvidence = $countsPath
    CompletedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
}
