@echo off
chcp 65001 >nul
echo ============================================
echo   A 股智能分析 - 公网访问模式
echo ============================================
echo.
echo [1/2] 启动 Streamlit 服务...
start "Stock-Web" E:\Anaconda\python.exe -m streamlit run web.py --server.port 8501 --server.headless true

echo [2/2] 启动公网隧道...
echo.
echo 公网地址将在下方显示，浏览器打开即可远程访问：
echo.

npx localtunnel --port 8501

pause
