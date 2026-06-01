"""
FastAPI 主应用
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import json
import re
import subprocess
from datetime import datetime
from typing import Optional, List

# 创建 FastAPI 应用
app = FastAPI(
    title="AI-PM",
    description="智能项目管理与研发工作流",
    version="0.1.0"
)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PROJECTS_DIR = Path.home() / "Documents" / "Projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
if (FRONTEND_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
if (FRONTEND_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
if (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

# ============ 工具函数 ============

def slugify(name: str) -> str:
    """将中文/英文名称转为文件名可用的 slug"""
    import unicodedata
    # 保留中文和英文，其他字符替换为 -
    slug = re.sub(r'[^\w\u4e00-\u9fff]', '-', name)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:50]  # 限制长度

def run_ai_engine(audio_path: str, output_dir: str, model: str = "small") -> dict:
    """调用 ai_engine.py 处理会议纪要"""
    python = "/Library/Developer/CommandLineTools/usr/bin/python3"
    engine = str(PROJECT_ROOT / "backend" / "ai_engine.py")
    
    env = os.environ.copy()
    env["ALL_PROXY"] = ""  # 禁用代理，确保 Kimi 直接访问
    
    cmd = [
        python, engine, audio_path,
        "-o", output_dir,
        "--model", model
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)
    
    if result.returncode != 0:
        raise Exception(f"AI 引擎失败: {result.stderr}")
    
    # 解析最后一行 JSON 输出
    lines = result.stdout.strip().split('\n')
    for line in reversed(lines):
        try:
            return json.loads(line)
        except:
            continue
    return {}

def generate_requirement_from_meeting(meeting_file: Path, project_dir: Path) -> Path:
    """将会议纪要自动转为需求文档（草稿）"""
    # 读取会议纪要
    content = meeting_file.read_text(encoding="utf-8")
    
    # 提取标题和核心内容
    title_match = re.search(r'# 会议纪要：(.+)', content)
    date = title_match.group(1) if title_match else datetime.now().strftime("%Y-%m-%d")
    
    # 提取议题
    topics = re.findall(r'## 议题\n+(.+?)\n##', content, re.DOTALL)
    topic_text = topics[0] if topics else ""
    
    # 提取决策
    decisions = re.findall(r'## 决策\n+(.+?)\n##', content, re.DOTALL)
    decision_text = decisions[0] if decisions else ""
    
    # 提取待办
    todos = re.findall(r'## 待办\n+(.+?)\n##', content, re.DOTALL)
    todo_text = todos[0] if todos else ""
    
    # 提取技术特征
    tech_features = re.findall(r'## 技术特征\n+(.+?)\n##', content, re.DOTALL)
    tech_features_text = tech_features[0] if tech_features else ''
    
    # 提取摘要
    summary = re.findall(r'## 摘要\n+(.+?)\n##', content, re.DOTALL)
    summary_text = summary[0].strip() if summary else ""
    
    # 从议题中提取需求名称
    req_name = ""
    if topic_text:
        lines = [l.strip() for l in topic_text.split('\n') if l.strip() and not l.startswith('_')]
        if lines:
            req_name = lines[0].strip().lstrip('0123456789.').strip()
    
    if not req_name:
        req_name = f"需求-{date}"
    
    # 生成需求文档
    req_slug = slugify(req_name)
    req_file = project_dir / "requirements" / f"{req_slug}.md"
    
    req_content = f"""# {req_name}

> **来源**: 会议纪要 [{meeting_file.name}]({meeting_file.name})
> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
> **状态**: 草稿（待确认）

---

## 需求概述

{summary_text}

---

## 背景

{topic_text}

---

## 决策与约束

{decision_text}

---

## 待办事项

{todo_text}

---

## 技术特征

{tech_features_text}

---

> 📝 本需求由 AI 从会议纪要自动提取，请人工确认并补充细节。
"""
    
    req_file.write_text(req_content, encoding="utf-8")
    return req_file

# ============ 路由 ============

@app.get("/", response_class=HTMLResponse)
async def root():
    """项目面板首页"""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(content="<h1>AI-PM</h1><p>前端文件未生成</p>")

@app.get("/project/{project_id}", response_class=HTMLResponse)
async def project_page(project_id: str):
    """项目工作台"""
    project_file = FRONTEND_DIR / "project.html"
    if project_file.exists():
        return FileResponse(project_file)
    return HTMLResponse(content=f"<h1>项目: {project_id}</h1><p>前端文件未生成</p>")

# ============ API 路由 ============

@app.get("/api/projects")
async def list_projects():
    """列出所有项目"""
    projects = []
    if PROJECTS_DIR.exists():
        for item in PROJECTS_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                meta_file = item / ".meta" / "project.json"
                meta = {}
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                projects.append({
                    "id": item.name,
                    "name": meta.get("name", item.name),
                    "description": meta.get("description", ""),
                    "created_at": meta.get("created_at", ""),
                    "status": meta.get("status", "active")
                })
    return {"projects": projects}

@app.post("/api/projects")
async def create_project(name: str = Form(...), description: str = Form("")):
    """创建新项目"""
    import re
    
    # 生成项目 ID
    project_id = re.sub(r'[^\w\-]', '-', name.lower())
    project_dir = PROJECTS_DIR / project_id
    
    if project_dir.exists():
        raise HTTPException(status_code=400, detail="项目已存在")
    
    # 创建目录结构
    (project_dir / ".meta").mkdir(parents=True, exist_ok=True)
    (project_dir / "requirements").mkdir(parents=True, exist_ok=True)
    (project_dir / "meetings").mkdir(parents=True, exist_ok=True)
    (project_dir / "prd").mkdir(parents=True, exist_ok=True)
    (project_dir / "ui").mkdir(parents=True, exist_ok=True)
    (project_dir / "testcases").mkdir(parents=True, exist_ok=True)
    (project_dir / "automation").mkdir(parents=True, exist_ok=True)
    
    # 创建元数据
    meta = {
        "id": project_id,
        "name": name,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "tech_features": {},
        "ui_features": {},
        "business_features": {}
    }
    (project_dir / ".meta" / "project.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    return {"id": project_id, "name": name, "message": "项目创建成功"}

@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """获取项目详情"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    meta_file = project_dir / ".meta" / "project.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    
    # 统计产物
    artifacts = {
        "requirements": len(list((project_dir / "requirements").glob("*.md"))),
        "meetings": len(list((project_dir / "meetings").glob("*.md"))),
        "prd": len(list((project_dir / "prd").glob("*.md"))),
        "ui": len(list((project_dir / "ui").glob("*.html"))),
        "testcases": len(list((project_dir / "testcases").glob("*.md"))),
        "automation": len(list((project_dir / "automation").glob("*"))),
    }
    
    return {
        "id": project_id,
        "meta": meta,
        "artifacts": artifacts
    }

@app.post("/api/projects/{project_id}/upload")
async def upload_file(project_id: str, file: UploadFile = File(...), category: str = Form(...)):
    """上传文件到项目"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 验证分类
    valid_categories = ["requirements", "meetings", "prd", "ui", "testcases", "automation"]
    if category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"无效分类: {category}")
    
    target_dir = project_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    file_path = target_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)
    
    return {
        "message": "文件上传成功",
        "filename": file.filename,
        "category": category,
        "path": str(file_path)
    }

@app.get("/api/projects/{project_id}/files/{category}")
async def list_files(project_id: str, category: str):
    """列出项目某分类下的文件"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    target_dir = project_dir / category
    if not target_dir.exists():
        return {"files": []}
    
    files = []
    for f in target_dir.iterdir():
        if f.is_file():
            stat = f.stat()
            files.append({
                "name": f.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    
    return {"files": files}

@app.get("/api/projects/{project_id}/files/{category}/{filename}")
async def read_file(project_id: str, category: str, filename: str):
    """读取项目文件内容"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    file_path = project_dir / category / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    content = file_path.read_text(encoding="utf-8")
    return {"filename": filename, "content": content}

@app.post("/api/projects/{project_id}/files/{category}/{filename}")
async def update_file(project_id: str, category: str, filename: str, content: str = Form(...)):
    """更新项目文件内容"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    file_path = project_dir / category / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_path.write_text(content, encoding="utf-8")
    return {"message": "文件更新成功"}

# ============ AI 相关 API ============

@app.get("/api/ai/status")
async def ai_status():
    """检查 AI 配置状态"""
    status = {
        "whisper": {"installed": False, "model": None},
        "ollama": {"available": False, "models": []},
        "api_key": {"configured": False, "provider": None}
    }
    
    # 检查 Whisper
    try:
        import whisper
        status["whisper"]["installed"] = True
        cache_dir = Path.home() / ".cache" / "whisper"
        models = [f.name for f in cache_dir.glob("*.pt")] if cache_dir.exists() else []
        status["whisper"]["model"] = models[0] if models else None
    except ImportError:
        pass
    
    # 检查 Ollama
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            status["ollama"]["available"] = True
            status["ollama"]["models"] = [m["name"] for m in resp.json().get("models", [])]
    except:
        pass
    
    # 检查 Kimi API Key（环境变量或硬编码）
    if os.environ.get("KIMI_API_KEY") or True:  # 硬编码了 key
        status["api_key"]["configured"] = True
        status["api_key"]["provider"] = "Kimi"
    
    return status

@app.post("/api/projects/{project_id}/ai/transcribe")
async def transcribe_meeting(project_id: str, file: UploadFile = File(...), auto_convert: bool = Form(True)):
    """上传音频并生成会议纪要 + 自动转为需求（可选）"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 1. 保存音频到临时目录
    temp_dir = Path("/tmp") / "ai-pm" / project_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    audio_path = temp_dir / file.filename
    content = await file.read()
    audio_path.write_bytes(content)
    
    # 2. 调用 AI 引擎转录
    meetings_dir = project_dir / "meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        result = run_ai_engine(str(audio_path), str(meetings_dir))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"转录失败: {str(e)}")
    
    # 3. 自动转为需求（如果启用）
    req_file = None
    if auto_convert and result.get("minutes_file"):
        meeting_file = Path(result["minutes_file"])
        if meeting_file.exists():
            req_file = generate_requirement_from_meeting(meeting_file, project_dir)
    
    return {
        "message": "会议纪要生成成功",
        "meeting_file": result.get("minutes_file"),
        "meta_file": result.get("meta_file"),
        "requirement_file": str(req_file) if req_file else None,
        "summary": result.get("summary", {})
    }

@app.post("/api/projects/{project_id}/ai/generate-prd")
async def generate_prd(project_id: str, requirement_files: str = Form(...)):
    """选中多个需求文件，生成 PRD 草案"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 解析需求文件列表（逗号分隔）
    req_names = [f.strip() for f in requirement_files.split(",") if f.strip()]
    
    # 读取需求内容
    req_contents = []
    for req_name in req_names:
        req_path = project_dir / "requirements" / req_name
        print(f"检查需求文件: {req_path}")
        if req_path.exists():
            req_contents.append(req_path.read_text(encoding="utf-8"))
            print(f"✅ 找到: {req_path}")
        else:
            print(f"❌ 未找到: {req_path}")
            req_dir = project_dir / "requirements"
            if req_dir.exists():
                print(f"目录内容: {list(req_dir.iterdir())}")
    
    if not req_contents:
        raise HTTPException(status_code=400, detail="未找到需求文件")
    
    # 调用 LLM 生成结构化 PRD
    try:
        import sys
        backend_dir = str(PROJECT_ROOT / "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from ai_engine import generate_prd_from_requirements
        project_meta_path = project_dir / ".meta" / "project.json"
        project_name = project_id
        if project_meta_path.exists():
            meta = json.loads(project_meta_path.read_text(encoding="utf-8"))
            project_name = meta.get("name", project_id)
        prd_content = generate_prd_from_requirements(req_contents, project_name)
    except Exception as e:
        print(f"⚠️ LLM PRD 生成失败: {e}")
        import traceback
        traceback.print_exc()
        prd_content = "\n\n---\n\n".join(req_contents)
    
    prd_dir = project_dir / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)
    
    prd_file = prd_dir / f"PRD-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    prd_file.write_text(prd_content, encoding="utf-8")
    
    return {
        "message": "PRD 草案生成成功",
        "prd_file": str(prd_file),
        "based_on": req_names,
        "llm_generated": not prd_content.startswith("⚠️")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
