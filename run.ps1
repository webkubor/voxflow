# VoxFlow 启动器（Windows）。macOS / Linux 用同目录的 run.sh。
#
# 跟 run.sh 一样薄，原因也一样：前端产物检查、museav 提示、模型名默认值
# 都在 `voice web`（cli/app.py）里，三个平台共用一份，不在启动脚本里各写一遍。
#
# 用法：
#   .\run.ps1          启动 Web UI（http://localhost:8866）
#   .\run.ps1 dev      开发模式：后端 8866 + Vite 前端 5173
#   .\run.ps1 doctor   自检
#   .\run.ps1 <任意 voice 子命令>
#
# 首次使用先跑：python -m venv .venv; .\.venv\Scripts\pip install -e .

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$voice = ".\.venv\Scripts\voice.exe"
if (-not (Test-Path $voice)) {
    Write-Host "X 没找到 .venv\Scripts\voice.exe —— 先建虚拟环境并安装：" -ForegroundColor Red
    Write-Host "    python -m venv .venv"
    Write-Host "    .\.venv\Scripts\pip install -e ."
    exit 1
}

if ($args.Count -gt 0 -and $args[0] -eq "dev") {
    if (-not (Test-Path "web\ui\node_modules")) {
        Write-Host "  安装前端依赖…"
        Push-Location web\ui; npm install; Pop-Location
    }
    Write-Host "  后端 -> http://localhost:8866"
    Write-Host "  前端 -> http://localhost:5173  <- 开发时打开这个"
    Write-Host ""
    # 后端放后台，前端占前台（Ctrl-C 停前端后记得收掉后端进程）
    $backend = Start-Process -FilePath $voice -ArgumentList "web" -PassThru -NoNewWindow
    try {
        Push-Location web\ui
        npm run dev
    } finally {
        Pop-Location
        if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    }
    exit 0
}

if ($args.Count -eq 0) { & $voice web } else { & $voice @args }
