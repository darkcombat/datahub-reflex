param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://github\.com/[^/]+/[^/]+(?:\.git)?$')]
    [string]$RemoteUrl
)

$ErrorActionPreference = "Stop"

if ((git status --porcelain) -ne "") {
    throw "Working tree is not clean. Commit or review changes before publishing."
}

$branch = git branch --show-current
if ($branch -ne "main") {
    throw "Expected branch 'main', found '$branch'."
}

$existing = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0 -and $existing -ne $RemoteUrl) {
    throw "Remote 'origin' already points to '$existing'. Refusing to replace it."
}

if ($LASTEXITCODE -ne 0) {
    git remote add origin $RemoteUrl
}

Write-Host "Publishing branch 'main' to $RemoteUrl"
git push --set-upstream origin main
