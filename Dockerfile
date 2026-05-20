FROM python:3.11-slim

WORKDIR /app

# 系统依赖 (akshare 需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 源码
COPY . .

# Streamlit 端口
EXPOSE 8501

# 默认启动 Web 界面
CMD ["python", "-m", "streamlit", "run", "web.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
