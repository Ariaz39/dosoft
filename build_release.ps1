[CmdletBinding()]
param(
    [string]$PythonExe = "",
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [switch]$KeepBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

function Remove-ProjectDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    $RootFull = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    $TargetFull = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Path)).TrimEnd('\')
    if (-not $TargetFull.StartsWith("$RootFull\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Nettoyage refusé hors du projet : $TargetFull"
    }
    if ($TargetFull -eq $RootFull) {
        throw "Nettoyage refusé à la racine du projet"
    }
    if (Test-Path -LiteralPath $TargetFull) {
        Remove-Item -LiteralPath $TargetFull -Recurse -Force
    }
}

# Certains environnements Windows isolés exposent un dossier TEMP lisible mais
# non inscriptible. Les tests et PyInstaller utilisent donc un espace contrôlé.
$ReleaseTemp = Join-Path $ProjectRoot ".release_tmp"
Remove-ProjectDirectory -Path ".release_tmp"
New-Item -ItemType Directory -Path $ReleaseTemp | Out-Null
$env:TEMP = $ReleaseTemp
$env:TMP = $ReleaseTemp

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    if (-not [string]::IsNullOrWhiteSpace($env:DOSOFT_PYTHON)) {
        $PythonExe = $env:DOSOFT_PYTHON
    } else {
        $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source
    }
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python introuvable : $PythonExe"
}

$VersionData = Get-Content -LiteralPath "version.json" -Raw | ConvertFrom-Json
$Version = [string]$VersionData.version
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Version invalide dans version.json : $Version"
}

Write-Host "[1/6] Validation des sources DOSOFT $Version"
& $PythonExe "tools\validate_release.py" --root $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Validation des sources échouée" }

if (-not $SkipTests) {
    Write-Host "[2/6] Tests automatiques"
    & $PythonExe -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw "Tests automatiques échoués" }
} else {
    Write-Host "[2/6] Tests ignorés à la demande"
}

if (-not $KeepBuild) {
    Write-Host "[3/6] Nettoyage des sorties temporaires"
    foreach ($Directory in ("build", "dist")) {
        Remove-ProjectDirectory -Path $Directory
    }
} else {
    Write-Host "[3/6] Conservation des sorties temporaires"
}

Write-Host "[4/6] Compilation PyInstaller reproductible"
$PyInstallerArguments = @("-m", "PyInstaller", "--noconfirm")
if (-not $KeepBuild) {
    $PyInstallerArguments += "--clean"
}
$PyInstallerArguments += "Dosoft_BETA.spec"
& $PythonExe @PyInstallerArguments
if ($LASTEXITCODE -ne 0) { throw "Compilation PyInstaller échouée" }
$Executable = Join-Path $ProjectRoot "dist\Dosoft_BETA.exe"
& $PythonExe "tools\validate_release.py" --root $ProjectRoot --executable $Executable
if ($LASTEXITCODE -ne 0) { throw "Validation de l'exécutable échouée" }

$ReleaseDirectory = Join-Path $ProjectRoot "release_output\v$Version"
if (Test-Path -LiteralPath $ReleaseDirectory) {
    Remove-ProjectDirectory -Path ("release_output\v{0}" -f $Version)
}
New-Item -ItemType Directory -Path $ReleaseDirectory | Out-Null
Copy-Item -LiteralPath $Executable -Destination $ReleaseDirectory
Copy-Item -LiteralPath "version.json", "LICENSE", "THIRD_PARTY_NOTICES.md" -Destination $ReleaseDirectory
Copy-Item -LiteralPath "obs-plugin\dofus-scene-guard.dll" -Destination $ReleaseDirectory
$ReleaseNotes = Join-Path $ProjectRoot ("docs\releases\{0}-beta.md" -f $Version)
if (Test-Path -LiteralPath $ReleaseNotes -PathType Leaf) {
    Copy-Item -LiteralPath $ReleaseNotes -Destination (Join-Path $ReleaseDirectory "RELEASE_NOTES.md")
}
$DiscordNotes = Join-Path $ProjectRoot ("docs\releases\{0}-beta-discord.md" -f $Version)
if (Test-Path -LiteralPath $DiscordNotes -PathType Leaf) {
    Copy-Item -LiteralPath $DiscordNotes -Destination (Join-Path $ReleaseDirectory "DISCORD_PATCH_NOTES.md")
}

if (-not $SkipInstaller) {
    Write-Host "[5/6] Compilation de l'installeur Inno Setup"
    $IsccCandidates = @(
        (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path $env:USERPROFILE "AppData\Local\Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    $Iscc = $IsccCandidates | Select-Object -First 1
    if (-not $Iscc) {
        throw "Inno Setup 6 introuvable. Utilisez -SkipInstaller pour valider uniquement l'exécutable."
    }
    & $Iscc "/DAppVersion=$Version" "setup.iss"
    if ($LASTEXITCODE -ne 0) { throw "Compilation Inno Setup échouée" }
    $Installer = Join-Path $ProjectRoot "installer_output\Dosoft_BETA_Setup_v$Version.exe"
    if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
        throw "L'installeur attendu n'a pas été généré : $Installer"
    }
    Copy-Item -LiteralPath $Installer -Destination $ReleaseDirectory
} else {
    Write-Host "[5/6] Installeur ignoré à la demande"
}

Write-Host "[6/6] Empreintes SHA-256"
$Artifacts = Get-ChildItem -LiteralPath $ReleaseDirectory -File | Sort-Object Name
$ChecksumLines = foreach ($Artifact in $Artifacts) {
    $Hash = (Get-FileHash -LiteralPath $Artifact.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  $($Artifact.Name)"
}
$ChecksumLines | Set-Content -LiteralPath (Join-Path $ReleaseDirectory "SHA256SUMS.txt") -Encoding utf8
Remove-ProjectDirectory -Path ".release_tmp"
Write-Host "[OK] Release préparée dans $ReleaseDirectory"
