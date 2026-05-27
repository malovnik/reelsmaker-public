#Requires -Version 5.1
<#
================================================================================
 Reelibra — Windows launcher (PowerShell)
================================================================================
 Запускается через reelibraWIN.cmd (powershell -ExecutionPolicy Bypass -File).

 Делает ровно то, что run.sh делает на macOS, но нативно на Windows и БЕЗ
 предустановленных инструментов — портативные раннеры скачиваются при первом
 запуске в локальный кэш .reelibra-runtime\ (НЕ требует админа/winget):

   1. Bootstrap портативных раннеров (python-build-standalone 3.12, Node 20,
      static ffmpeg, uv.exe) + VC++ Redist при отсутствии vcruntime140.dll.
   2. Диагностика каждый запуск: наличие/версии + идемпотентные uv sync /
      pnpm install.
   3. Чистка висяков прошлого запуска: процессы по портам 8000/3000 и по
      cmdline, освобождение портов, удаление .partial/.tmp/orphan-.lock.
   4. Запуск backend (uvicorn :8000) + frontend (Vite :3000), health-poll,
      открытие браузера.
   5. trap-очистка детей при выходе / Ctrl+C.

 Целевая ОС: Windows 10 x64 (1809+) / Windows 11 x64. Только x86-64.
 Honest: локального STT на Windows нет (MLX = Apple-only) → STT через Deepgram,
 нужен DEEPGRAM_API_KEY.
#>

# strict mode — ловим опечатки в переменных, но не валимся на не-zero кодах
# внешних утилит (их обрабатываем вручную через $LASTEXITCODE).
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# UTF-8 вывод (русский в консоли). На Win10+ консоль поддерживает.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

# ─── Пути ──────────────────────────────────────────────────────────────────
# Корень репо = на два уровня выше этого скрипта (launchers\windows\).
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir     = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$BackendDir  = Join-Path $RootDir 'apps\backend'
$FrontendDir = Join-Path $RootDir 'apps\frontend'
$DataDir     = Join-Path $RootDir 'data'
$RunDir      = Join-Path $DataDir '.run'
$LogsDir     = Join-Path $DataDir 'logs'
$RuntimeDir  = Join-Path $RootDir '.reelibra-runtime'
$AssetsDir   = Join-Path $RootDir 'assets'

# Кэш портативных раннеров
$PyDir       = Join-Path $RuntimeDir 'python-3.12'
$NodeDir     = Join-Path $RuntimeDir 'node-20'
$FfmpegDir   = Join-Path $RuntimeDir 'ffmpeg'
$UvExe       = Join-Path $RuntimeDir 'uv\uv.exe'
$DownloadDir = Join-Path $RuntimeDir 'downloads'

# Версии раннеров (заморожены для воспроизводимости)
$PyVersion     = '3.12.8'
$PyBuildTag    = '20241219'   # релиз python-build-standalone
$NodeVersion   = '20.18.1'
$UvVersion     = '0.5.11'
# ffmpeg: gyan.dev release build, закреплённая версия (постоянный GitHub-релиз,
# в отличие от ежедневно перезаливаемого BtbN latest → 404/невоспроизводимость).
$FfmpegVersion = '8.1.1'
# SHA256 артефакта ffmpeg-8.1.1-full_build.zip (вычислен с самого GitHub-релиза,
# на который пиннимся). Ловит обрыв/повреждение/подмену закачки.
$FfmpegSha256  = '49b28c5f16addd40239a66949973458769b7056fb7752c30ac0d53389d09a552'

# Backend host/port (дефолты как в .env.example; .env читаем ниже)
$AppHost = '127.0.0.1'
$AppPort = 8000
$FePort  = 3000
$HealthUrl = ''   # вычислим после чтения .env

# Глобальные хэндлы фоновых процессов (для cleanup)
$Script:BackendProc  = $null
$Script:FrontendProc = $null
$Script:LogFile      = $null

# ─── Цвета / прогресс UI ─────────────────────────────────────────────────────
# ANSI поддерживается на Win10+ (Windows Terminal / современный conhost).
$Script:Ansi = $false
try {
    if ($Host.UI.SupportsVirtualTerminal -or $env:WT_SESSION) { $Script:Ansi = $true }
} catch {}

function Write-Line {
    param([string]$Text, [string]$Color = 'Gray')
    Write-Host $Text -ForegroundColor $Color
}
function Write-Ok    { param([string]$m) Write-Host "   $m " -NoNewline; Write-Host 'ОК' -ForegroundColor Green }
function Write-OkMsg { param([string]$label,[string]$detail) Write-Host "   $label… " -NoNewline; Write-Host "ОК$detail" -ForegroundColor Green }
function Write-Warn  { param([string]$m) Write-Host "   $m" -ForegroundColor Yellow }
function Write-Err   { param([string]$m) Write-Host "   $m" -ForegroundColor Red }
function Write-Phase { param([string]$m) Write-Host ""; Write-Host $m -ForegroundColor Cyan }
function Write-Step  { param([string]$m) Write-Host "   $m… " -NoNewline -ForegroundColor Gray }

# Лог в файл (полные детали, без шума в консоль).
function Log {
    param([string]$Message)
    try {
        if ($Script:LogFile) {
            $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            Add-Content -LiteralPath $Script:LogFile -Value "[$ts] $Message" -Encoding UTF8
        }
    } catch {}
}

# Человеческая фатальная ошибка: сообщение + хвост лога, без сырого стектрейса.
function Fail {
    param([string]$UserMessage, [string]$LogTail = '')
    Write-Host ""
    Write-Host "  ✖ $UserMessage" -ForegroundColor Red
    if ($LogTail) {
        Write-Host "  Подробности:" -ForegroundColor DarkGray
        $LogTail -split "`n" | Select-Object -Last 5 | ForEach-Object {
            Write-Host "    $_" -ForegroundColor DarkGray
        }
    }
    if ($Script:LogFile) {
        Write-Host "  Полный лог: $($Script:LogFile)" -ForegroundColor DarkGray
    }
    Log "FATAL: $UserMessage`n$LogTail"
    Write-Host ""
    Write-Host "  Нажми любую клавишу, чтобы закрыть." -ForegroundColor DarkGray
    [void][System.Console]::ReadKey($true)
    exit 1
}

# ─── Сетевая загрузка с прогрессом и проверкой ───────────────────────────────
function Download-File {
    param([string]$Url, [string]$OutFile, [string]$Label)

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null
    $tmp = "$OutFile.partial"
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

    Write-Host "   $Label — скачиваю… " -NoNewline -ForegroundColor Gray
    Log "Download $Url -> $OutFile"

    # Системный прокси (корпоративные сети). Без него часто нет сети наружу.
    try {
        # Прогресс через WebClient + событие. Tls12 — некоторые хосты требуют.
        [System.Net.ServicePointManager]::SecurityProtocol = `
            [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls13
    } catch {
        try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12 } catch {}
    }

    try {
        $wc = New-Object System.Net.WebClient
        $wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy()
        $wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials
        $wc.Headers.Add('User-Agent', 'Reelibra-Launcher')

        # Прогресс печатаем на каждом «круглом» проценте (кратном 5). Дубли
        # визуально безвредны (та же строка перезаписывается через `r).
        $progressJob = Register-ObjectEvent -InputObject $wc -EventName DownloadProgressChanged -Action {
            $pct = $Event.SourceArgs.ProgressPercentage
            if ($pct % 5 -eq 0) {
                Write-Host "`r   $($Event.MessageData) — скачиваю… $pct%   " -NoNewline -ForegroundColor Gray
            }
        } -MessageData $Label

        $wc.DownloadFileAsync([Uri]$Url, $tmp)
        while ($wc.IsBusy) { Start-Sleep -Milliseconds 150 }
        Unregister-Event -SourceIdentifier $progressJob.Name -ErrorAction SilentlyContinue
        Remove-Job -Name $progressJob.Name -Force -ErrorAction SilentlyContinue
        $wc.Dispose()
    } catch {
        Log "WebClient failed: $($_.Exception.Message); fallback to Invoke-WebRequest"
        # Фолбэк: Invoke-WebRequest (без прогресс-бара, но надёжнее на части машин).
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing -ErrorAction Stop
        } catch {
            if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
            throw "Не удалось скачать $Label. Проверь интернет-соединение. ($($_.Exception.Message))"
        }
    }

    if (-not (Test-Path -LiteralPath $tmp) -or (Get-Item -LiteralPath $tmp).Length -eq 0) {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
        throw "Файл $Label скачался пустым. Проверь интернет."
    }
    Move-Item -LiteralPath $tmp -Destination $OutFile -Force
    Write-Host "`r   $Label — скачано           " -ForegroundColor Gray
}

# Распаковка zip (через .NET — без зависимости от внешних утилит).
function Expand-Zip {
    param([string]$ZipPath, [string]$Dest)
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
    # Используем Expand-Archive (PS 5.1+) — устойчивее к длинным путям с -Force.
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Dest -Force
}

# Распаковка .tar.gz / .tar.zst (python-build-standalone) — через bsdtar (tar.exe
# есть в Win10 1803+). Фолбэк-сообщение если tar отсутствует.
function Expand-Tar {
    param([string]$TarPath, [string]$Dest)
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    $tar = (Get-Command tar.exe -ErrorAction SilentlyContinue)
    if (-not $tar) {
        throw "Не найден tar.exe (нужен Windows 10 1803+). Обнови Windows."
    }
    & tar.exe -xf $TarPath -C $Dest
    if ($LASTEXITCODE -ne 0) { throw "Не удалось распаковать $TarPath" }
}

# ─── Bootstrap: VC++ Redist ──────────────────────────────────────────────────
function Ensure-VCRedist {
    # numpy/opencv/mediapipe/llama-cpp/onnxruntime требуют vcruntime140.dll.
    $sys32 = Join-Path $env:WINDIR 'System32\vcruntime140.dll'
    if (Test-Path -LiteralPath $sys32) {
        Write-OkMsg 'VC++ Runtime' ''
        return
    }
    Write-Warn 'VC++ Runtime не найден — нужен для научных библиотек'
    $vcExe = Join-Path $DownloadDir 'vc_redist.x64.exe'
    try {
        if (-not (Test-Path -LiteralPath $vcExe)) {
            Download-File -Url 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $vcExe -Label 'VC++ Redistributable'
        }
        Write-Host "   Устанавливаю VC++ Runtime (может запросить права)… " -NoNewline -ForegroundColor Gray
        # /quiet — без UI; /norestart — не перезагружать. Может всплыть UAC.
        $p = Start-Process -FilePath $vcExe -ArgumentList '/install','/quiet','/norestart' -Wait -PassThru -Verb RunAs
        # Коды: 0 = успех, 3010 = успех + нужен ребут, 1638 = уже стоит новее.
        if ($p.ExitCode -in 0,3010,1638) {
            Write-Host 'ОК' -ForegroundColor Green
        } else {
            Write-Host "код $($p.ExitCode)" -ForegroundColor Yellow
            Write-Warn 'VC++ установился с предупреждением — если приложение упадёт с DLL-ошибкой, поставь vc_redist.x64.exe вручную.'
        }
    } catch {
        Log "VCRedist install error: $($_.Exception.Message)"
        Write-Host ''
        Write-Warn 'Не удалось поставить VC++ Runtime автоматически.'
        Write-Warn 'Скачай и установи: https://aka.ms/vs/17/release/vc_redist.x64.exe'
    }
}

# ─── Bootstrap: Python 3.12 (python-build-standalone) ───────────────────────
function Ensure-Python {
    $exe = Join-Path $PyDir 'python\python.exe'
    if (Test-Path -LiteralPath $exe) {
        Write-OkMsg 'Python 3.12' " ($PyVersion)"
        return $exe
    }
    Write-Warn 'Python 3.12 не найден — ставлю портативный (без админа)'
    # python-build-standalone: install_only сборка содержит готовый python\.
    $asset = "cpython-$PyVersion+$PyBuildTag-x86_64-pc-windows-msvc-install_only.tar.gz"
    $url = "https://github.com/astral-sh/python-build-standalone/releases/download/$PyBuildTag/$asset"
    $dl  = Join-Path $DownloadDir $asset
    Download-File -Url $url -OutFile $dl -Label 'Python 3.12'
    if (Test-Path -LiteralPath $PyDir) { Remove-Item -LiteralPath $PyDir -Recurse -Force -ErrorAction SilentlyContinue }
    Expand-Tar -TarPath $dl -Dest $PyDir   # распакует в $PyDir\python\
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Python распаковался неверно (нет python.exe).' }
    Write-Ok 'Python 3.12 установлен'
    return $exe
}

# ─── Bootstrap: uv.exe ───────────────────────────────────────────────────────
function Ensure-Uv {
    if (Test-Path -LiteralPath $UvExe) {
        Write-OkMsg 'uv' ''
        return
    }
    Write-Warn 'uv не найден — ставлю портативный'
    $asset = 'uv-x86_64-pc-windows-msvc.zip'
    $url = "https://github.com/astral-sh/uv/releases/download/$UvVersion/$asset"
    $dl  = Join-Path $DownloadDir $asset
    Download-File -Url $url -OutFile $dl -Label 'uv'
    $uvParent = Split-Path -Parent $UvExe
    Expand-Zip -ZipPath $dl -Dest $uvParent
    if (-not (Test-Path -LiteralPath $UvExe)) { throw 'uv распаковался неверно.' }
    Write-Ok 'uv установлен'
}

# ─── Bootstrap: Node 20 (portable) ──────────────────────────────────────────
function Ensure-Node {
    $nodeExe = Join-Path $NodeDir 'node.exe'
    if (Test-Path -LiteralPath $nodeExe) {
        Write-OkMsg 'Node 20' " (v$NodeVersion)"
        return
    }
    Write-Warn 'Node 20 не найден — ставлю портативный'
    $folder = "node-v$NodeVersion-win-x64"
    $asset  = "$folder.zip"
    $url = "https://nodejs.org/dist/v$NodeVersion/$asset"
    $dl  = Join-Path $DownloadDir $asset
    Download-File -Url $url -OutFile $dl -Label 'Node 20'
    $extractTmp = Join-Path $RuntimeDir 'node-tmp'
    if (Test-Path -LiteralPath $extractTmp) { Remove-Item -LiteralPath $extractTmp -Recurse -Force -ErrorAction SilentlyContinue }
    Expand-Zip -ZipPath $dl -Dest $extractTmp
    if (Test-Path -LiteralPath $NodeDir) { Remove-Item -LiteralPath $NodeDir -Recurse -Force -ErrorAction SilentlyContinue }
    # Архив содержит node-vXX-win-x64\... — переносим содержимое в node-20\.
    Move-Item -LiteralPath (Join-Path $extractTmp $folder) -Destination $NodeDir -Force
    Remove-Item -LiteralPath $extractTmp -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $nodeExe)) { throw 'Node распаковался неверно.' }
    Write-Ok 'Node 20 установлен'
}

# ─── Bootstrap: ffmpeg + ffprobe (static gpl) ───────────────────────────────
function Ensure-Ffmpeg {
    $ffExe = Join-Path $FfmpegDir 'ffmpeg.exe'
    $fpExe = Join-Path $FfmpegDir 'ffprobe.exe'
    if ((Test-Path -LiteralPath $ffExe) -and (Test-Path -LiteralPath $fpExe)) {
        Write-OkMsg 'ffmpeg + ffprobe' ''
        return
    }
    Write-Warn 'ffmpeg не найден — ставлю static-сборку (gpl)'
    # gyan.dev release build — закреплённая версия с постоянным GitHub-релизом.
    # (BtbN latest перезаливается ежедневно → разные сборки у разных юзеров и 404
    #  в момент перезаливки. Здесь же тег версии не исчезает.)
    $asset = "ffmpeg-$FfmpegVersion-full_build.zip"
    $url = "https://github.com/GyanD/codexffmpeg/releases/download/$FfmpegVersion/$asset"
    $dl  = Join-Path $DownloadDir $asset
    Download-File -Url $url -OutFile $dl -Label 'ffmpeg'
    # Проверка целостности: SHA256 закреплённого артефакта.
    $actualSha = (Get-FileHash -LiteralPath $dl -Algorithm SHA256).Hash
    if ($actualSha -ne $FfmpegSha256.ToUpper()) {
        Remove-Item -LiteralPath $dl -Force -ErrorAction SilentlyContinue
        throw "Контрольная сумма ffmpeg не совпала (ожидалось $FfmpegSha256, получено $actualSha). Файл повреждён или подменён — скачивание прервано."
    }
    $extractTmp = Join-Path $RuntimeDir 'ffmpeg-tmp'
    if (Test-Path -LiteralPath $extractTmp) { Remove-Item -LiteralPath $extractTmp -Recurse -Force -ErrorAction SilentlyContinue }
    Expand-Zip -ZipPath $dl -Dest $extractTmp
    # Внутри: ffmpeg-master-latest-win64-gpl\bin\{ffmpeg,ffprobe}.exe
    $binDir = Get-ChildItem -LiteralPath $extractTmp -Recurse -Filter 'ffmpeg.exe' -ErrorAction SilentlyContinue |
              Select-Object -First 1 | ForEach-Object { $_.DirectoryName }
    if (-not $binDir) { throw 'Не нашёл ffmpeg.exe в архиве.' }
    New-Item -ItemType Directory -Force -Path $FfmpegDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $binDir 'ffmpeg.exe')  -Destination $ffExe -Force
    Copy-Item -LiteralPath (Join-Path $binDir 'ffprobe.exe') -Destination $fpExe -Force
    Remove-Item -LiteralPath $extractTmp -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $ffExe)) { throw 'ffmpeg распаковался неверно.' }
    Write-Ok 'ffmpeg + ffprobe установлены'
}

# ─── Сборка PATH сессии (раннеры впереди системных) ─────────────────────────
function Set-RuntimePath {
    param([string]$PyExe)
    $pyHome   = Split-Path -Parent $PyExe          # ...\python-3.12\python
    $pyScripts = Join-Path $pyHome 'Scripts'
    $uvHome   = Split-Path -Parent $UvExe
    # Node + глобальный npm-prefix (для pnpm) держим внутри runtime, не в системе.
    $npmPrefix = Join-Path $RuntimeDir 'npm-global'
    New-Item -ItemType Directory -Force -Path $npmPrefix | Out-Null
    $env:Path = @($FfmpegDir, $uvHome, $NodeDir, $npmPrefix, $pyHome, $pyScripts, $env:Path) -join ';'

    # uv: использовать ИМЕННО наш Python, не качать свой и не искать системный.
    $env:UV_PYTHON = $PyExe
    $env:UV_PYTHON_DOWNLOADS = 'never'
    # npm глобальные пакеты (pnpm) — в runtime, чтобы не пачкать систему/не требовать прав.
    $env:NPM_CONFIG_PREFIX = $npmPrefix
    # ffmpeg/ffprobe для backend (некоторый код читает env-пути).
    $env:FFMPEG_BINARY  = Join-Path $FfmpegDir 'ffmpeg.exe'
    $env:FFPROBE_BINARY = Join-Path $FfmpegDir 'ffprobe.exe'
}

# ─── pnpm через portable Node ───────────────────────────────────────────────
function Ensure-Pnpm {
    $npmPrefix = Join-Path $RuntimeDir 'npm-global'
    $pnpmCmd = Join-Path $npmPrefix 'pnpm.cmd'
    if (Test-Path -LiteralPath $pnpmCmd) {
        Write-OkMsg 'pnpm' ''
        return $pnpmCmd
    }
    Write-Warn 'pnpm не найден — ставлю в локальный кэш'
    $npmCmd = Join-Path $NodeDir 'npm.cmd'
    # Ставим pnpm в runtime\npm-global (NPM_CONFIG_PREFIX) — без прав администратора.
    & $npmCmd install -g pnpm --silent 2>&1 | ForEach-Object { Log "npm: $_" }
    if (-not (Test-Path -LiteralPath $pnpmCmd)) {
        throw 'Не удалось установить pnpm через portable Node.'
    }
    Write-Ok 'pnpm установлен'
    return $pnpmCmd
}

# ─── Чтение .env (host/port) ────────────────────────────────────────────────
function Read-DotEnv {
    $envPath = Join-Path $RootDir '.env'
    if (-not (Test-Path -LiteralPath $envPath)) { return }
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $k, $v = $line -split '=', 2
        $k = $k.Trim(); $v = $v.Trim()
        switch ($k) {
            'APP_HOST' { if ($v) { $Script:AppHost = $v } }
            'APP_PORT' { if ($v -match '^\d+$') { $Script:AppPort = [int]$v } }
        }
    }
}

# Получить значение ключа из .env (для проверки наличия API-ключей).
function Get-EnvValue {
    param([string]$Key)
    $envPath = Join-Path $RootDir '.env'
    if (-not (Test-Path -LiteralPath $envPath)) { return '' }
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") {
            return $Matches[1].Trim()
        }
    }
    return ''
}

# ─── Поиск PID, держащих порт ───────────────────────────────────────────────
function Get-PortPids {
    param([int]$Port)
    $pids = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        $pids += $conns | Select-Object -ExpandProperty OwningProcess
    } catch {
        # Фолбэк без модуля NetTCPIP: парсим netstat.
        $lines = netstat -ano | Select-String ":$Port\s" | Select-String 'LISTENING'
        foreach ($l in $lines) {
            $cols = ($l.ToString() -split '\s+') | Where-Object { $_ }
            if ($cols.Count -ge 5) { $pids += [int]$cols[-1] }
        }
    }
    return ($pids | Where-Object { $_ -and $_ -ne 0 } | Sort-Object -Unique)
}

# Принадлежит ли PID нашему стеку (python/uvicorn/node/vite/esbuild/pnpm/ffmpeg
# нашего репо). Защита от убийства чужого сервиса на 8000/3000.
function Test-OursPid {
    param([int]$ProcId)
    try {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcId" -ErrorAction Stop
    } catch { return $false }
    if (-not $p) { return $false }
    $cmd  = "$($p.CommandLine)"
    $name = "$($p.Name)"
    $rootEsc = [regex]::Escape($RootDir)
    # uvicorn videomaker.main — модуль уникален для этого ПО, путь не требуется.
    if ($cmd -match 'uvicorn videomaker\.main') { return $true }
    # Остальное (vite/esbuild/pnpm/ffmpeg) — ТОЛЬКО если из нашего каталога,
    # иначе прибьём чужой dev-сервер другого проекта на машине.
    if ($name -eq 'node.exe'  -and $cmd -match 'vite' -and $cmd -match $rootEsc) { return $true }
    if ($name -eq 'esbuild.exe' -and $cmd -match $rootEsc) { return $true }
    if ($cmd -match 'pnpm' -and $cmd -match 'dev' -and $cmd -match $rootEsc) { return $true }
    if ($name -eq 'ffmpeg.exe' -and $cmd -match 'data[\\/]artifacts' -and $cmd -match $rootEsc) { return $true }
    # Путь репо в cmdline/exe — наш процесс с неожиданной командой.
    if ($cmd -match $rootEsc) { return $true }
    if ($p.ExecutablePath -and ($p.ExecutablePath -match $rootEsc)) { return $true }
    return $false
}

# Найти наши процессы по cmdline (отвалившиеся от порта).
function Get-OurStrayPids {
    $rootEsc = [regex]::Escape($RootDir)
    $found = @()
    try {
        $procs = Get-CimInstance Win32_Process -ErrorAction Stop
    } catch { return @() }
    foreach ($p in $procs) {
        $cmd  = "$($p.CommandLine)"
        $name = "$($p.Name)"
        if (-not $cmd) { continue }
        $isOurs = $false
        if ($cmd -match 'uvicorn videomaker\.main') { $isOurs = $true }
        elseif ($cmd -match 'uv run uvicorn')        { $isOurs = $true }
        elseif ($name -eq 'node.exe'  -and $cmd -match 'vite' -and $cmd -match $rootEsc) { $isOurs = $true }
        elseif ($name -eq 'pnpm.cmd'  -and $cmd -match 'dev'  -and $cmd -match $rootEsc) { $isOurs = $true }
        elseif ($name -eq 'ffmpeg.exe' -and $cmd -match 'data[\\/]artifacts' -and $cmd -match $rootEsc) { $isOurs = $true }
        elseif (($name -eq 'python.exe' -or $name -eq 'node.exe') -and $cmd -match $rootEsc) { $isOurs = $true }
        if ($isOurs) { $found += [int]$p.ProcessId }
    }
    return ($found | Sort-Object -Unique)
}

# Остановка: мягко → жёстко с деревом (зеркало trap cleanup в run.sh).
function Stop-PidTree {
    param([int]$ProcId)
    try { Stop-Process -Id $ProcId -ErrorAction SilentlyContinue } catch {}
    Start-Sleep -Milliseconds 300
    if (Get-Process -Id $ProcId -ErrorAction SilentlyContinue) {
        # /T валит детей (reloader uvicorn, esbuild у Vite), /F = форс.
        & taskkill.exe /PID $ProcId /T /F 2>&1 | Out-Null
    }
}

# ─── ФАЗА 2: чистка висяков ──────────────────────────────────────────────────
function Invoke-Cleanup {
    Write-Phase '[2/4] Уборка после прошлого запуска'

    foreach ($port in @($AppPort, $FePort)) {
        Write-Host "   Порт $port… " -NoNewline -ForegroundColor Gray
        $pids = Get-PortPids -Port $port
        if (-not $pids -or $pids.Count -eq 0) {
            Write-Host 'свободен' -ForegroundColor Green
            continue
        }
        $ours    = @($pids | Where-Object { Test-OursPid $_ })
        $foreign = @($pids | Where-Object { -not (Test-OursPid $_) })
        if ($foreign.Count -gt 0) {
            $fp = $foreign[0]
            $fname = try { (Get-Process -Id $fp -ErrorAction SilentlyContinue).ProcessName } catch { 'неизвестно' }
            Write-Host 'занят чужой программой' -ForegroundColor Red
            Write-Err "Порт $port занят программой '$fname' (PID $fp) — это не Reelibra."
            if ($port -eq $FePort) {
                Fail "Порт $FePort обязан быть свободен (Vite strictPort). Закрой программу '$fname' (PID $fp) или поменяй её порт, затем перезапусти Reelibra."
            } else {
                Fail "Порт $port занят чужой программой '$fname' (PID $fp). Закрой её или поменяй APP_PORT в .env, затем перезапусти."
            }
        }
        # Все наши — гасим.
        foreach ($procId in $ours) { Stop-PidTree -ProcId $procId }
        Start-Sleep -Seconds 1
        $still = Get-PortPids -Port $port
        if ($still -and $still.Count -gt 0) {
            Write-Host 'не освободился' -ForegroundColor Red
            Fail "Не удалось освободить порт $port (PID $($still -join ',')). Закрой процесс вручную или перезапусти от администратора."
        }
        Write-Host "освобождён (был занят: $($ours -join ','))" -ForegroundColor Green
    }

    # Висяки по cmdline (отвалились от портов).
    Write-Host "   Зависшие процессы Reelibra… " -NoNewline -ForegroundColor Gray
    $stray = Get-OurStrayPids
    if ($stray -and $stray.Count -gt 0) {
        foreach ($procId in $stray) { Stop-PidTree -ProcId $procId }
        Write-Host "остановлено $($stray.Count)" -ForegroundColor Green
    } else {
        Write-Host 'не найдено' -ForegroundColor Green
    }

    # Орфаны .partial/.tmp/.lock — НЕ трогаем *.db/-wal/-shm и финальные медиа.
    Write-Host "   Временные файлы (.partial/.tmp/orphan .lock)… " -NoNewline -ForegroundColor Gray
    $removed = 0
    if (Test-Path -LiteralPath $DataDir) {
        try {
            $junk = Get-ChildItem -LiteralPath $DataDir -Recurse -File -Include '*.partial','*.tmp' -ErrorAction SilentlyContinue
            foreach ($f in $junk) { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue; $removed++ }
            # orphan .lock: старше lock_timeout (1800 c). Процессы уже убиты — но
            # для безопасности фильтруем по возрасту.
            $cutoff = (Get-Date).AddSeconds(-1800)
            $locks = Get-ChildItem -LiteralPath $DataDir -Recurse -File -Include '*.lock' -ErrorAction SilentlyContinue |
                     Where-Object { $_.LastWriteTime -lt $cutoff }
            foreach ($f in $locks) { Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue; $removed++ }
        } catch { Log "cleanup junk: $($_.Exception.Message)" }
    }
    Write-Host "удалено $removed" -ForegroundColor Green

    # PID-файлы прошлого сеанса (детект жёсткого закрытия).
    if (Test-Path -LiteralPath $RunDir) {
        Get-ChildItem -LiteralPath $RunDir -Filter '*.pid' -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }

    # __pycache__ — гарантия свежего bytecode (как в run.sh).
    $srcDir = Join-Path $BackendDir 'src'
    if (Test-Path -LiteralPath $srcDir) {
        Get-ChildItem -LiteralPath $srcDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host "   Прерванные задачи прошлого сеанса… " -NoNewline -ForegroundColor Gray
    Write-Host 'будут помечены бэкендом' -ForegroundColor DarkGray
}

# ─── ФАЗА 3: запуск серверов ─────────────────────────────────────────────────
function Start-Servers {
    param([string]$PnpmCmd)
    Write-Phase '[3/4] Запуск'

    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $beLog = Join-Path $LogsDir 'backend.out.log'
    $feLog = Join-Path $LogsDir 'frontend.out.log'

    # Backend: uv run uvicorn (БЕЗ --reload для конечного пользователя).
    Write-Step "Backend (порт $AppPort)"
    try {
        $Script:BackendProc = Start-Process -FilePath $UvExe `
            -ArgumentList @(
                'run','uvicorn','videomaker.main:app',
                '--host', $AppHost,
                '--port', "$AppPort",
                '--log-level','info'
            ) `
            -WorkingDirectory $BackendDir `
            -RedirectStandardOutput $beLog `
            -RedirectStandardError (Join-Path $LogsDir 'backend.err.log') `
            -WindowStyle Hidden -PassThru
        Set-Content -LiteralPath (Join-Path $RunDir 'backend.pid') -Value $Script:BackendProc.Id -Encoding ASCII
        Write-Host 'запущен' -ForegroundColor Green
    } catch {
        Fail "Не удалось запустить backend." (Get-Content -LiteralPath $beLog -Tail 5 -ErrorAction SilentlyContinue | Out-String)
    }

    # Frontend: pnpm dev (Vite :3000).
    Write-Step "Frontend (порт $FePort)"
    try {
        $Script:FrontendProc = Start-Process -FilePath $PnpmCmd `
            -ArgumentList @('dev') `
            -WorkingDirectory $FrontendDir `
            -RedirectStandardOutput $feLog `
            -RedirectStandardError (Join-Path $LogsDir 'frontend.err.log') `
            -WindowStyle Hidden -PassThru
        Set-Content -LiteralPath (Join-Path $RunDir 'frontend.pid') -Value $Script:FrontendProc.Id -Encoding ASCII
        Write-Host 'запущен' -ForegroundColor Green
    } catch {
        Fail "Не удалось запустить frontend." (Get-Content -LiteralPath $feLog -Tail 5 -ErrorAction SilentlyContinue | Out-String)
    }

    # Health-poll backend (до 60 с — холодный старт + DDL/seed на первом запуске).
    Write-Host "   Жду готовности backend ($HealthUrl)… " -NoNewline -ForegroundColor Gray
    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        # Если процесс backend умер — нет смысла ждать.
        if ($Script:BackendProc.HasExited) {
            Write-Host 'упал' -ForegroundColor Red
            $tail = (Get-Content -LiteralPath (Join-Path $LogsDir 'backend.err.log') -Tail 8 -ErrorAction SilentlyContinue | Out-String)
            Fail "Backend не запустился (процесс завершился)." $tail
        }
        try {
            $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 800
    }
    if (-not $ready) {
        Write-Host 'таймаут' -ForegroundColor Red
        $tail = (Get-Content -LiteralPath (Join-Path $LogsDir 'backend.err.log') -Tail 8 -ErrorAction SilentlyContinue | Out-String)
        Fail "Backend не ответил за 60 секунд." $tail
    }
    Write-Host 'ОК' -ForegroundColor Green
}

# ─── trap cleanup (выход / Ctrl+C) ──────────────────────────────────────────
function Stop-Servers {
    Write-Host ""
    Write-Host "Останавливаю Reelibra…" -ForegroundColor Cyan
    foreach ($proc in @($Script:FrontendProc, $Script:BackendProc)) {
        if ($proc -and -not $proc.HasExited) {
            Stop-PidTree -ProcId $proc.Id
        }
    }
    # Подчистить остатки по cmdline (дети, осиротевшие при крахе).
    foreach ($procId in (Get-OurStrayPids)) { Stop-PidTree -ProcId $procId }
    if (Test-Path -LiteralPath $RunDir) {
        Get-ChildItem -LiteralPath $RunDir -Filter '*.pid' -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Reelibra остановлен. Можно закрыть окно." -ForegroundColor Green
}

# ============================================================================
#  MAIN
# ============================================================================
try {
    # data-каталоги + лог-файл сразу (чтобы Log/Fail работали).
    New-Item -ItemType Directory -Force -Path $DataDir, $RunDir, $LogsDir,
        (Join-Path $DataDir 'uploads'), (Join-Path $DataDir 'artifacts') | Out-Null
    $Script:LogFile = Join-Path $LogsDir 'launcher.log'
    Log "=== Launcher start. Root=$RootDir ==="

    Clear-Host
    Write-Host ""
    Write-Host "  Reelibra — подготовка к запуску" -ForegroundColor White
    Write-Host "  Windows 10/11 x64 · нарезка видео в рилсы" -ForegroundColor DarkGray

    # Раннее предупреждение про кириллицу/пробелы в пути (классика поломки venv).
    if ($RootDir -match '[^\x00-\x7F]') {
        Write-Host ""
        Write-Warn "Путь содержит не-латинские символы:"
        Write-Warn "  $RootDir"
        Write-Warn "Это может ломать venv/uv. Если будут ошибки — перенеси папку в путь вида C:\reelibra."
    }

    # ── ФАЗА 1: bootstrap раннеров + диагностика ──
    Write-Phase '[1/4] Проверка окружения'
    Ensure-VCRedist
    $pyExe = Ensure-Python
    Ensure-Uv
    Ensure-Node
    Ensure-Ffmpeg
    Set-RuntimePath -PyExe $pyExe
    $pnpmCmd = Ensure-Pnpm

    # .env
    Write-Host "   Конфиг (.env)… " -NoNewline -ForegroundColor Gray
    $envPath = Join-Path $RootDir '.env'
    if (-not (Test-Path -LiteralPath $envPath)) {
        Copy-Item -LiteralPath (Join-Path $RootDir '.env.example') -Destination $envPath -Force
        Write-Host 'создан из шаблона' -ForegroundColor Yellow
    } else {
        Write-Host 'найден' -ForegroundColor Green
    }
    Read-DotEnv
    $HealthUrl = "http://$AppHost`:$AppPort/api/v1/health"

    # Проверка ключей (honesty: Gemini обязателен, Deepgram нужен для STT на Win).
    $gemini   = Get-EnvValue 'GEMINI_API_KEY'
    $deepgram = Get-EnvValue 'DEEPGRAM_API_KEY'
    if (-not $gemini) {
        Write-Warn 'GEMINI_API_KEY пуст — без него пайплайн не сгенерирует рилсы. Открой .env и добавь ключ.'
    }
    if (-not $deepgram) {
        Write-Warn 'DEEPGRAM_API_KEY пуст. На Windows распознавание речи работает ТОЛЬКО через Deepgram'
        Write-Warn '(локальный MLX-движок есть только на Mac). Без ключа транскрипция видео не заработает.'
    }

    # backend deps — uv sync --offline недоступен (wheelhouse не бандлим в репо),
    # поэтому обычный uv sync (ставит из PyPI; MLX-пакеты с маркером darwin
    # автоматически пропускаются на Windows).
    Write-Host "   Зависимости backend (uv sync)… " -NoNewline -ForegroundColor Gray
    $beSyncLog = & $UvExe sync --project $BackendDir 2>&1
    if ($LASTEXITCODE -ne 0) {
        Log "uv sync failed:`n$($beSyncLog | Out-String)"
        Write-Host 'ошибка, пересоздаю окружение…' -ForegroundColor Yellow
        $venv = Join-Path $BackendDir '.venv'
        if (Test-Path -LiteralPath $venv) { Remove-Item -LiteralPath $venv -Recurse -Force -ErrorAction SilentlyContinue }
        $beSyncLog = & $UvExe sync --project $BackendDir 2>&1
        if ($LASTEXITCODE -ne 0) {
            Fail "Не удалось собрать окружение backend." ($beSyncLog | Out-String)
        }
        Write-Host "   Зависимости backend… " -NoNewline -ForegroundColor Gray
    }
    Write-Host 'ОК' -ForegroundColor Green

    # frontend deps — pnpm install (идемпотентно).
    Write-Host "   Зависимости frontend (pnpm install)… " -NoNewline -ForegroundColor Gray
    Push-Location $FrontendDir
    try {
        $feLog2 = & $pnpmCmd install --silent 2>&1
        if ($LASTEXITCODE -ne 0) {
            Log "pnpm install failed:`n$($feLog2 | Out-String)"
            Write-Host 'ошибка, чищу и повторяю…' -ForegroundColor Yellow
            & $pnpmCmd store prune 2>&1 | Out-Null
            $nm = Join-Path $FrontendDir 'node_modules'
            if (Test-Path -LiteralPath $nm) { Remove-Item -LiteralPath $nm -Recurse -Force -ErrorAction SilentlyContinue }
            $feLog2 = & $pnpmCmd install 2>&1
            if ($LASTEXITCODE -ne 0) {
                Fail "Не удалось установить зависимости frontend." ($feLog2 | Out-String)
            }
            Write-Host "   Зависимости frontend… " -NoNewline -ForegroundColor Gray
        }
    } finally { Pop-Location }
    Write-Host 'ОК' -ForegroundColor Green

    # ── ФАЗА 2: чистка ──
    Invoke-Cleanup

    # ── ФАЗА 3: запуск ──
    Start-Servers -PnpmCmd $pnpmCmd

    # ── ФАЗА 4: готово ──
    Write-Phase '[4/4] Готово'
    $feUrl = "http://localhost:$FePort"
    Write-Host "   Открываю $feUrl" -ForegroundColor Green
    Start-Process $feUrl | Out-Null
    Write-Host ""
    Write-Host "  Reelibra работает." -ForegroundColor White
    Write-Host "  Нажми Ctrl+C или закрой это окно, чтобы остановить." -ForegroundColor DarkGray
    Write-Host ""

    # Держим окно открытым = «сервер». При выходе — Stop-Servers (см. finally).
    # Ctrl+C прервёт цикл → исключение → finally.
    while ($true) {
        Start-Sleep -Seconds 2
        # Если оба процесса умерли сами — выходим.
        $beDead = (-not $Script:BackendProc)  -or $Script:BackendProc.HasExited
        $feDead = (-not $Script:FrontendProc) -or $Script:FrontendProc.HasExited
        if ($beDead -and $feDead) {
            Write-Host "Серверы завершились." -ForegroundColor Yellow
            break
        }
    }
}
catch {
    Log "Unhandled: $($_.Exception.Message)`n$($_.ScriptStackTrace)"
    # Если это не наш Fail (он уже сам показал и вышел) — покажем кратко.
    if ($_.Exception.Message) {
        Write-Host ""
        Write-Host "  ✖ Ошибка: $($_.Exception.Message)" -ForegroundColor Red
        if ($Script:LogFile) { Write-Host "  Лог: $($Script:LogFile)" -ForegroundColor DarkGray }
        Write-Host "  Нажми любую клавишу, чтобы закрыть." -ForegroundColor DarkGray
        try { [void][System.Console]::ReadKey($true) } catch {}
    }
    exit 1
}
finally {
    Stop-Servers
}
