#!/usr/bin/env python3
"""
AI-PM 打包脚本
使用 PyInstaller 生成可执行文件

用法：
    python3 build.py

输出：
    dist/ai-pm.app (Mac)
    dist/ai-pm.exe (Windows)
"""

import os
import sys
import shutil
from pathlib import Path

def build():
    """打包应用"""
    project_root = Path(__file__).parent.resolve()
    
    print("=" * 50)
    print("🚀 AI-PM 打包工具")
    print("=" * 50)
    
    # 检查 PyInstaller
    try:
        import PyInstaller
        print("✅ PyInstaller 已安装")
    except ImportError:
        print("❌ PyInstaller 未安装，正在安装...")
        os.system(f"{sys.executable} -m pip install pyinstaller")
    
    # 清理旧构建
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        print("🗑️ 清理旧构建目录")
    
    # 构建命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "ai-pm",
        "--onefile",  # 单文件
        "--windowed",  # 无控制台窗口（Mac）
        "--add-data", f"frontend{os.pathsep}frontend",
        "--add-data", f"templates{os.pathsep}templates",
        "--icon", "assets/icons/icon.icns" if sys.platform == "darwin" else "assets/icons/icon.ico",
        "ai-pm.py"
    ]
    
    print(f"\n📦 开始打包...")
    print(f"   命令: {' '.join(cmd)}")
    
    os.chdir(project_root)
    result = os.system(" ".join(cmd))
    
    if result == 0:
        print("\n✅ 打包成功！")
        print(f"   输出: {dist_dir}")
        
        if sys.platform == "darwin":
            app_path = dist_dir / "ai-pm.app"
            if app_path.exists():
                print(f"   Mac 应用: {app_path}")
        elif sys.platform == "win32":
            exe_path = dist_dir / "ai-pm.exe"
            if exe_path.exists():
                print(f"   Windows 应用: {exe_path}")
    else:
        print("\n❌ 打包失败")
        sys.exit(1)

if __name__ == "__main__":
    build()
