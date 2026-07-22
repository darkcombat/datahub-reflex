param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://github\.com/[^/]+/[^/]+(?:\.git)?$')]
    [string]$RemoteUrl
)

$ErrorActionPreference = "Stop"

$status = git status --porcelain
if ($null -ne $status -and $status.Count -gt 0) {
    throw "Working tree is not clean. Commit or review changes before publishing."
}

$branch = git branch --show-current
if ($branch -ne "main") {
    throw "Expected branch 'main', found '$branch'."
}

$remotes = @(git remote)
if ($remotes -contains "origin") {
    $existing = git remote get-url origin
    if ($existing -ne $RemoteUrl) {
        throw "Remote 'origin' already points to '$existing'. Refusing to replace it."
    }
} else {
    git remote add origin $RemoteUrl
}

Write-Host "Publishing branch 'main' to $RemoteUrl"
git push --set-upstream origin main
