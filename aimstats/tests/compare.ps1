# Compares two snapshots from snapshot.ps1 and lists every file that was added, removed or changed.
# Usage: powershell -ExecutionPolicy Bypass -File compare.ps1 -Before snap-1-before.csv -After snap-2-installed.csv
param(
    [Parameter(Mandatory = $true)][string]$Before,
    [Parameter(Mandatory = $true)][string]$After
)
$a = @{}; Import-Csv -LiteralPath $Before | ForEach-Object { $a[$_.Path] = $_ }
$b = @{}; Import-Csv -LiteralPath $After | ForEach-Object { $b[$_.Path] = $_ }
$diffs = @()
foreach ($p in $a.Keys) {
    if (-not $b.ContainsKey($p)) { $diffs += "REMOVED  $p" }
    elseif ($a[$p].SHA256 -ne $b[$p].SHA256) { $diffs += "CHANGED  $p" }
}
foreach ($p in $b.Keys) { if (-not $a.ContainsKey($p)) { $diffs += "ADDED    $p" } }
Write-Host ("Compared {0} files before and {1} after." -f $a.Count, $b.Count)
if ($diffs.Count -eq 0) { Write-Host "IDENTICAL: no file was added, removed or changed." }
else { $diffs | Sort-Object { $_.Substring(9) } | ForEach-Object { Write-Host $_ } }
