# Writes a list of every file in the game's Binaries\Win64 folder (path, size, SHA-256) to a CSV. Reads only.
# Usage: powershell -ExecutionPolicy Bypass -File snapshot.ps1 -Out C:\AimStatsTest\snap-1-before.csv [-Game <Win64 folder>]
param(
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Game = "C:\Program Files (x86)\Steam\steamapps\common\Aimbeast\Aimbeast\Binaries\Win64"
)
$root = (Resolve-Path $Game).Path.TrimEnd('\')
Get-ChildItem -LiteralPath $root -Recurse -File -Force | ForEach-Object {
    [pscustomobject]@{
        Path   = $_.FullName.Substring($root.Length + 1)
        Size   = $_.Length
        SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
} | Sort-Object Path | Export-Csv -LiteralPath $Out -NoTypeInformation -Encoding UTF8
Write-Host ("{0} files listed in {1}" -f (Import-Csv -LiteralPath $Out).Count, $Out)
