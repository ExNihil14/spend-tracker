# Spendtrack — одна команда установки (Windows).
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# Источник можно переопределить (локальный путь/wheel/git):
#   .\install.ps1 -Source .\dist\spendtrack-0.1.0-py3-none-any.whl
param(
  [string]$Source = "git+https://github.com/ExNihil14/spend-tracker",
  [int]$Port = 0,          # 0 = порт из settings.toml (8766)
  [switch]$NoServe,        # только установить, без запуска
  [switch]$NoUvInstall     # не ставить uv автоматически
)
$ErrorActionPreference = "Stop"

function Test-Uv {
  return [bool](Get-Command uv -ErrorAction SilentlyContinue)
}

if (-not (Test-Uv)) {
  if ($NoUvInstall) {
    throw "uv не найден. Установите: https://docs.astral.sh/uv/ (или уберите -NoUvInstall)"
  }
  Write-Host "uv не найден — ставлю официальным установщиком astral.sh ..."
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
  if (-not (Test-Uv)) {
    throw "uv установлен, но не виден в PATH — откройте новый терминал и повторите"
  }
}

Write-Host "Устанавливаю spendtrack из $Source ..."
uv tool install --force $Source

$shimDir = Join-Path $env:USERPROFILE ".local\bin"
if (Test-Path (Join-Path $shimDir "spendtrack.exe")) { $env:Path = "$shimDir;$env:Path" }
$exe = (Get-Command spendtrack -ErrorAction Stop).Source

if ($NoServe) {
  Write-Host "Готово: $exe"
  Write-Host "Запуск: spendtrack serve --open"
  exit 0
}

$serveArgs = @("serve", "--open")
if ($Port -gt 0) { $serveArgs += @("--port", "$Port") }
& $exe @serveArgs
