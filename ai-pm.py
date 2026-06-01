#!/usr/bin/env python3
"""
AI-PM 主入口
启动 FastAPI 后端 + 自动打开浏览器
"""

import os
import sys
import webbrowser
import time
import subprocess
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

sys.path.insert(0, str(BACKEND_DIR))

def check_dependencies():
    """检查依赖是否安装"""
    try:
        import fastapi
        import uvicorn
        print("✅ 依赖已安装")
        return True
    except ImportError:
        print("❌ 依赖未安装，请先运行：pip install -r requirements.txt")
        return False

def setup_directories():
    """创建必要的目录"""
    dirs = [
        PROJECT_ROOT / "backend",
        PROJECT_ROOT / "frontend",
        PROJECT_ROOT / "frontend" / "css",
        PROJECT_ROOT / "frontend" / "js",
        PROJECT_ROOT / "templates",
        PROJECT_ROOT / "assets" / "icons",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print("✅ 目录结构已创建")

def start_server():
    """启动 FastAPI 服务"""
    import uvicorn
    from backend.main import app
    
    host = "127.0.0.1"
    port = 8080
    
    print(f"\n🚀 启动 AI-PM 服务器...")
    print(f"   地址: http://{host}:{port}")
    print(f"   按 Ctrl+C 停止\n")
    
    # 自动打开浏览器
    time.sleep(1)
    webbrowser.open(f"http://{host}:{port}")
    
    uvicorn.run(app, host=host, port=port, log_level="info")

def main():
    print("=" * 50)
    print("🤖 AI-PM - 智能项目管理与研发工作流")
    print("=" * 50)
    
    if not check_dependencies():
        sys.exit(1)
    
    setup_directories()
    start_server()

if __name__ == "__main__":
    main()
