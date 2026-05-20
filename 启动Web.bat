@echo off
chcp 65001 >nul
echo 正在启动 A 股智能分析 Web 服务...
echo.
call E:\Anaconda\python.exe -m streamlit run web.py --server.port 8501
pause
