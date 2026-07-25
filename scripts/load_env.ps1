# Load .env into the current PowerShell session so dbt's env_var() calls resolve.
# Usage (from the repo root):   . .\scripts\load_env.ps1
Get-Content .env | Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } | ForEach-Object {
    $parts = $_.Split('=', 2)
    [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    Write-Host "set $($parts[0].Trim())"
}
