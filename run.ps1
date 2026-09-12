# Запуск сервера Spendtrack на порту из config/settings.toml
param(
  [switch]$NoReuse
)
$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")

if (-not $NoReuse) {
  $listener = Test-NetConnection -ComputerName 127.0.0.1 -Port 8766 -WarningAction SilentlyContinue
  if ($listener.TcpTestSucceeded) {
    Write-Host "Spendtrack уже запущен на http://127.0.0.1:8766"
    Start-Process "http://127.0.0.1:8766"
    exit 0
  }
}

uv run uvicorn spendtrack.main:app --host 127.0.0.1 --port 8766