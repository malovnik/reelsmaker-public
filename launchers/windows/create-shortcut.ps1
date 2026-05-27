#Requires -Version 5.1
<#
================================================================================
 Reelibra — создание ярлыка с фирменной иконкой
================================================================================
 Создаёт .lnk на рабочем столе и рядом с reelibraWIN.cmd. Ярлык указывает на
 reelibraWIN.cmd, иконка берётся из assets\reelibra.ico.

 Запуск: правый клик → «Выполнить с помощью PowerShell», либо
   powershell -ExecutionPolicy Bypass -File launchers\windows\create-shortcut.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$Target    = Join-Path $RootDir 'reelibraWIN.cmd'
$Icon      = Join-Path $RootDir 'assets\reelibra.ico'

if (-not (Test-Path -LiteralPath $Target)) {
    Write-Host "Не найден reelibraWIN.cmd в корне репозитория ($Target)." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $Icon)) {
    Write-Host "Не найдена иконка assets\reelibra.ico — ярлык будет без иконки." -ForegroundColor Yellow
    $Icon = $null
}

function New-Lnk {
    param([string]$Path)
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($Path)
    $sc.TargetPath       = $Target
    $sc.WorkingDirectory = $RootDir
    $sc.Description       = 'Reelibra — нарезка видео в рилсы'
    # Окно нормального размера (лаунчер показывает прогресс в консоли).
    $sc.WindowStyle      = 1
    if ($Icon) { $sc.IconLocation = "$Icon,0" }
    $sc.Save()
    Write-Host "Ярлык создан: $Path" -ForegroundColor Green
}

# Ярлык на рабочем столе.
$desktop = [Environment]::GetFolderPath('Desktop')
New-Lnk -Path (Join-Path $desktop 'Reelibra.lnk')

# Ярлык рядом с репозиторием (если папку открывают напрямую).
New-Lnk -Path (Join-Path $RootDir 'Reelibra.lnk')

Write-Host ""
Write-Host "Готово. Запускай Reelibra двойным кликом по ярлыку." -ForegroundColor White
