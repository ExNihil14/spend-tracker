# Устанавливает gitleaks (пин v8.30.1) в D:\dev\tools\gitleaks — для pre-commit-хука (Habr-ресёрч 04.10).
# Без Go/Docker: официальный релизный zip + сверка sha256 (из GitHub Releases).
# Использование:  powershell -ExecutionPolicy Bypass -File scripts\install-gitleaks.ps1 [-AddToPath]
param(
    [string]$Version = "v8.30.1",
    [string]$Sha256 = "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
    [string]$Dest = "D:\dev\tools\gitleaks",
    [switch]$AddToPath
)
$ErrorActionPreference = "Stop"
$verNum = $Version.TrimStart("v")
$zip = Join-Path $env:TEMP "gitleaks_${verNum}_windows_x64.zip"
$url = "https://github.com/gitleaks/gitleaks/releases/download/$Version/gitleaks_${verNum}_windows_x64.zip"
Write-Host "скачиваю $url"
Invoke-WebRequest -Uri $url -OutFile $zip
$actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $Sha256.ToLower()) {
    throw "sha256 не совпал (ожидался $Sha256, получен $actual) — файл не распаковываю"
}
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Expand-Archive -Path $zip -DestinationPath $Dest -Force
Remove-Item $zip
$exe = Join-Path $Dest "gitleaks.exe"
if (-not (Test-Path $exe)) { throw "gitleaks.exe не найден после распаковки" }
Write-Host "установлено: $exe"
& $exe version
if ($AddToPath) {
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -notlike "*$Dest*") {
        [Environment]::SetEnvironmentVariable("PATH", "$userPath;$Dest", "User")
        Write-Host "PATH (User) дополнен: $Dest (активируется в новых процессах)"
    } else {
        Write-Host "PATH уже содержит $Dest"
    }
}
