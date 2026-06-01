#!/bin/bash
# AI-PM 启动脚本 - 双击即可运行

cd "$(dirname "$0")"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装 Python"
    read -p "按回车键退出..."
    exit 1
fi

# 检查依赖
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "📦 首次启动，正在安装依赖..."
    pip3 install -r requirements.txt
fi

echo "🚀 启动 AI-PM..."
python3 ai-pm.py

# 防止窗口关闭
read -p "按回车键退出..."
