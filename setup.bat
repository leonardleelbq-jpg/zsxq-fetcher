@echo off
chcp 65001 >nul
echo ========================================
echo   ZSXQ Fetcher — 一键安装
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo   下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [✓] Python 已就绪

:: 安装依赖
echo [*] 安装 Python 依赖...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)
echo [✓] 依赖安装完成

:: 安装 Chromium
echo [*] 安装 Playwright Chromium（约 300MB，首次较慢）...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [错误] Chromium 安装失败
    pause
    exit /b 1
)
echo [✓] Chromium 安装完成

:: 配置文件
if not exist "scripts\config.json" (
    echo [*] 创建配置文件...
    copy scripts\config.example.json scripts\config.json >nul
    echo [✓] 已创建 scripts\config.json，请编辑填入你的 zsxq_access_token
) else (
    echo [✓] config.json 已存在
)

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo   下一步:
echo   1. 用记事本打开 scripts\config.json 填入你的 token
echo      （获取 token: 浏览器登录 wx.zsxq.com → F12 → Cookies）
echo   2. 运行: python scripts\zsxq_fetcher.py --list
echo.
echo   交流群: https://qm.qq.com/q/your_group
echo.
pause