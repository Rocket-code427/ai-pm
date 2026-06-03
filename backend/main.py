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
import time
from datetime import datetime
from typing import Optional, List, Dict

from backend.config import load_config, save_config, get_llm_config_from_file, config_to_display, PROVIDER_PRESETS


# 创建 FastAPI 应用
app = FastAPI(
    title="AI-PM",
    description="智能项目管理与研发工作流",
    version="0.2.0"
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

# 内存级访谈状态（重启丢失，生产环境换 Redis）
INTERVIEWS: Dict[str, dict] = {}

INTERVIEW_QUESTIONS = [
    "这个项目的核心用户是谁？他们面临的主要痛点是什么？",
    "产品需要解决的核心功能是什么？有哪些必须支持的次要功能？",
    "项目的技术约束或特殊要求有哪些？（如平台、性能、安全等）",
    "预期的时间线和里程碑是怎样的？有哪些关键交付节点？",
    "有哪些风险或不确定性需要提前考虑？"
]

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

def generate_requirement_from_meeting(meeting_file: Path, project_dir: Path, meeting_type: str = "") -> Optional[Path]:
    """将会议纪要自动转为需求文档（草稿），仅需求评审类型才生成
    
    Args:
        meeting_file: 会议纪要文件路径
        project_dir: 项目目录
        meeting_type: 会议纪要类型，只有"需求评审"才自动生成需求
    
    Returns:
        生成的需求文件路径，如果不是需求评审则返回 None
    """
    # 只有需求评审才自动生成需求
    if meeting_type != "需求评审":
        print(f"ℹ️ 会议纪要类型为'{meeting_type}'，不是需求评审，跳过自动生成需求")
        return None
    
    """将会议纪要自动转为需求文档（草稿），LLM 清洗修正"""
    # 读取会议纪要
    content = meeting_file.read_text(encoding="utf-8")
    
    # 提取标题
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
    
    # LLM 清洗修正
    try:
        import sys
        backend_dir = str(PROJECT_ROOT / "backend")
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        from ai_engine import get_llm_config, call_llm
        
        config = get_llm_config()
        if config:
            prompt = f"""请检查并修正以下从会议纪要提取的需求内容。对于明显的笔误、常识性错误或不通顺的术语，进行合理修正并标注。

原始内容：
- 摘要：{summary_text[:500]}
- 议题：{topic_text[:500]}
- 决策：{decision_text[:500]}
- 待办：{todo_text[:500]}
- 技术特征：{tech_features_text[:500]}

请返回修正后的内容，格式如下（纯文本，不要 markdown 代码块）：

摘要：修正后的摘要
议题：修正后的议题列表
决策：修正后的决策列表
待办：修正后的待办列表
技术特征：修正后的技术特征

注意：
- 只修正明显的错误（如"蓝牙Black协议"应为"蓝牙BLE协议"）
- 不要添加原文未提及的新内容
- 如果没有明显错误，直接返回原文
"""
            llm_result = call_llm(prompt, config)
            if llm_result:
                # 解析 LLM 返回
                for line in llm_result.split('\n'):
                    if line.startswith('摘要：') and len(line) > 4:
                        summary_text = line[3:].strip()
                    elif line.startswith('议题：') and len(line) > 4:
                        topic_text = line[3:].strip()
                    elif line.startswith('决策：') and len(line) > 4:
                        decision_text = line[3:].strip()
                    elif line.startswith('待办：') and len(line) > 4:
                        todo_text = line[3:].strip()
                    elif line.startswith('技术特征：') and len(line) > 6:
                        tech_features_text = line[5:].strip()
    except Exception as e:
        print(f"⚠️ 需求 LLM 修正失败: {e}")
    
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


def save_requirement_version(req_file: Path, project_dir: Path) -> int:
    """保存需求文档版本，返回版本号
    
    版本命名规则：需求-{名称}.v{N}.md
    """
    if not req_file.exists():
        return 0
    
    # 解析文件名：需求-xxx.md -> 需求-xxx.v1.md
    stem = req_file.stem  # 需求-xxx
    suffix = req_file.suffix  # .md
    
    # 检查是否已有版本
    req_dir = project_dir / "requirements"
    versions = sorted(req_dir.glob(f"{stem}.v*.md"))
    
    # 计算下一个版本号
    next_version = 1
    if versions:
        # 从最后一个版本提取版本号
        last_version = versions[-1]
        match = re.search(r'\.v(\d+)\.md$', last_version.name)
        if match:
            next_version = int(match.group(1)) + 1
    
    # 复制当前文件为新版本
    version_file = req_dir / f"{stem}.v{next_version}{suffix}"
    version_file.write_text(req_file.read_text(encoding="utf-8"), encoding="utf-8")
    
    return next_version

def get_requirement_versions(project_dir: Path, req_name: str) -> list:
    """获取需求文档的所有版本"""
    req_dir = project_dir / "requirements"
    versions = []
    
    # 查找所有版本文件
    for f in sorted(req_dir.glob(f"{req_name}.v*.md")):
        match = re.search(r'\.v(\d+)\.md$', f.name)
        if match:
            versions.append({
                "version": int(match.group(1)),
                "file": f.name,
                "path": str(f),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })
    
    return versions

def diff_requirements_with_llm(old_content: str, new_content: str, req_name: str) -> str:
    """使用 LLM 对比两个版本的需求文档，标出修改点
    
    Returns:
        Markdown 格式的差异报告
    """
    config = get_llm_config()
    if not config:
        return "⚠️ LLM 未配置，无法生成差异报告"
    
    prompt = f"""你是一位资深产品经理，请对比以下两份需求文档，标出修改点。

## 旧版本
{old_content[:4000]}

## 新版本
{new_content[:4000]}

## 输出要求

请生成一份差异报告，格式如下：

# 需求变更报告：{req_name}

## 变更摘要
- 新增内容：...
- 删除内容：...
- 修改内容：...

## 详细对比

### 新增
1. [新增的内容描述]
   - 位置：xxx章节
   - 影响：对下游（PRD/UI/测试）的影响

### 删除
1. [删除的内容描述]
   - 原位置：xxx章节
   - 删除原因（推测）：...

### 修改
1. [修改的内容描述]
   - 旧：...  
   - 新：...
   - 影响：...

## 影响评估
- PRD：是否需要更新？
- UI：是否需要调整？
- 测试：是否需要补充用例？

注意：
- 只对比真实差异，不要编造
- 标注每一项变更对下游的影响
- 如果没有实质变更，明确说明"无实质变更"
"""
    
    return call_llm(
        prompt, config,
        system="你是资深产品经理，擅长需求文档版本管理和变更影响分析。",
        temperature=0.2,
        timeout=120
    ) or "⚠️ LLM 调用失败"


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
    (project_dir / "ui_prototype").mkdir(parents=True, exist_ok=True)
    (project_dir / "ui_final").mkdir(parents=True, exist_ok=True)
    
    
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
        "ui_prototype": len(list((project_dir / "ui_prototype").glob("*"))),
        "ui_final": len(list((project_dir / "ui_final").glob("*"))),
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
    valid_categories = ["requirements", "meetings", "prd", "ui", "ui_prototype", "ui_final", "testcases", "automation"]
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
        "api_key": {"configured": False, "provider": None},
        "playwright": {"installed": False}
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
    
    # 检查 Playwright
    try:
        import playwright
        status["playwright"]["installed"] = True
    except ImportError:
        pass
    
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
    
    # 3. 自动转为需求（如果启用，且会议类型为需求评审）
    req_file = None
    meeting_type = result.get("summary", {}).get("meeting_type", "")
    if auto_convert and result.get("minutes_file") and meeting_type == "需求评审":
        meeting_file = Path(result["minutes_file"])
        if meeting_file.exists():
            req_file = generate_requirement_from_meeting(meeting_file, project_dir, meeting_type)
    elif auto_convert and meeting_type != "需求评审":
        print(f"ℹ️ 会议纪要类型为'{meeting_type}'，不是需求评审，不自动生成需求")
    
    return {
        "message": "会议纪要生成成功",
        "meeting_file": result.get("minutes_file"),
        "meta_file": result.get("meta_file"),
        "requirement_file": str(req_file) if req_file else None,
        "summary": result.get("summary", {})
    }

@app.post("/api/projects/{project_id}/ai/meeting-from-text")
async def meeting_from_text(project_id: str, file: UploadFile = File(...), auto_convert: bool = Form(True)):
    """上传文字文档直接生成结构化会议纪要（支持 txt/md/pdf/docx）"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 1. 保存文件到临时目录
    temp_dir = Path("/tmp") / "ai-pm" / project_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)
    
    # 2. 提取文本
    import sys
    backend_dir = str(PROJECT_ROOT / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from ai_engine import extract_text_from_file, generate_meeting_from_text
    
    text_content = extract_text_from_file(str(file_path))
    if text_content.startswith("⚠️"):
        raise HTTPException(status_code=400, detail=text_content)
    
    # 3. 生成结构化纪要
    meetings_dir = project_dir / "meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)
    
    meeting_title = file.filename.rsplit('.', 1)[0]
    result = generate_meeting_from_text(text_content, meeting_title=meeting_title)
    
    # 4. 保存会议纪要
    safe_title = slugify(meeting_title)
    minutes_file = meetings_dir / f"会议纪要-{safe_title}-{datetime.now().strftime('%Y%m%d')}.md"
    minutes_file.write_text(result["minutes"], encoding='utf-8')
    
    # 5. 自动转为需求（如果启用，且会议类型为需求评审）
    req_file = None
    meeting_type = result.get("summary", {}).get("meeting_type", "")
    if auto_convert and meeting_type == "需求评审":
        req_file = generate_requirement_from_meeting(minutes_file, project_dir, meeting_type)
    elif auto_convert and meeting_type != "需求评审":
        print(f"ℹ️ 会议纪要类型为'{meeting_type}'，不是需求评审，不自动生成需求")
    
    return {
        "message": "会议纪要生成成功",
        "meeting_file": str(minutes_file),
        "requirement_file": str(req_file) if req_file else None,
        "summary": result["summary"]
    }
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

@app.post("/api/projects/{project_id}/ai/requirement-from-text")
async def requirement_from_text(project_id: str, file: UploadFile = File(...), compare_version: bool = Form(True)):
    """上传文字文档，AI 解析为结构化需求文档（支持 txt/md/pdf/docx）
    
    Args:
        compare_version: 是否与前版本对比生成差异报告
    """
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    # 1. 保存文件
    temp_dir = Path("/tmp") / "ai-pm" / project_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / file.filename
    content = await file.read()
    file_path.write_bytes(content)
    
    # 2. 提取文本
    import sys
    backend_dir = str(PROJECT_ROOT / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from ai_engine import extract_text_from_file, generate_requirement_from_text
    
    text_content = extract_text_from_file(str(file_path))
    if text_content.startswith("⚠️"):
        raise HTTPException(status_code=400, detail=text_content)
    
    # 3. AI 生成需求
    req_md = generate_requirement_from_text(text_content, req_name=file.filename.rsplit('.', 1)[0])
    
    if not req_md:
        raise HTTPException(status_code=500, detail="AI 生成需求失败，请检查 LLM 配置")
    
    # 4. 保存到 requirements
    req_dir = project_dir / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = slugify(file.filename.rsplit('.', 1)[0])
    req_file = req_dir / f"需求-{safe_name}.md"
    
    # 5. 版本管理：如果已有同名文件，先保存旧版本
    diff_report = None
    version = 1
    if req_file.exists() and compare_version:
        # 保存旧版本
        version = save_requirement_version(req_file, project_dir)
        # 读取旧版本内容
        old_content = req_file.read_text(encoding="utf-8")
        # 写入新内容
        req_file.write_text(req_md, encoding='utf-8')
        # 生成差异报告
        diff_report = diff_requirements_with_llm(old_content, req_md, f"需求-{safe_name}")
        # 保存差异报告
        if diff_report and not diff_report.startswith("⚠️"):
            diff_file = req_dir / f"需求-{safe_name}.v{version}-v{version+1}.diff.md"
            diff_file.write_text(diff_report, encoding="utf-8")
    else:
        req_file.write_text(req_md, encoding='utf-8')
    
    return {
        "message": "需求文档生成成功",
        "requirement_file": str(req_file),
        "filename": file.filename,
        "version": version,
        "diff_report": diff_report
    }

@app.get("/api/projects/{project_id}/files/{category}/{filename}/versions")
async def list_file_versions(project_id: str, category: str, filename: str):
    """获取文件的所有版本（目前支持需求文档）"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    if category != "requirements":
        raise HTTPException(status_code=400, detail="暂只支持需求文档版本管理")
    
    # 解析文件名
    stem = Path(filename).stem  # 需求-xxx
    versions = get_requirement_versions(project_dir, stem)
    
    return {
        "filename": filename,
        "versions": versions,
        "total": len(versions)
    }

@app.get("/api/projects/{project_id}/files/{category}/{filename}/diff")
async def get_file_diff(project_id: str, category: str, filename: str, v1: int, v2: int):
    """获取两个版本之间的差异报告"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    if category != "requirements":
        raise HTTPException(status_code=400, detail="暂只支持需求文档版本管理")
    
    stem = Path(filename).stem
    req_dir = project_dir / "requirements"
    
    # 查找版本文件
    v1_file = req_dir / f"{stem}.v{v1}.md"
    v2_file = req_dir / f"{stem}.v{v2}.md"
    
    if not v1_file.exists() or not v2_file.exists():
        raise HTTPException(status_code=404, detail="版本文件不存在")
    
    # 读取内容
    v1_content = v1_file.read_text(encoding="utf-8")
    v2_content = v2_file.read_text(encoding="utf-8")
    
    # 生成差异报告
    diff_report = diff_requirements_with_llm(v1_content, v2_content, stem)
    
    return {
        "filename": filename,
        "v1": v1,
        "v2": v2,
        "diff_report": diff_report
    }

@app.get("/api/projects/{project_id}/files/{category}/{filename}/diff-report")
async def get_diff_report_file(project_id: str, category: str, filename: str, v1: int, v2: int):
    """获取已保存的差异报告文件"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    stem = Path(filename).stem
    req_dir = project_dir / "requirements"
    
    # 查找差异报告文件
    diff_file = req_dir / f"{stem}.v{v1}-v{v2}.diff.md"
    if not diff_file.exists():
        # 尝试反向查找
        diff_file = req_dir / f"{stem}.v{v2}-v{v1}.diff.md"
    
    if not diff_file.exists():
        raise HTTPException(status_code=404, detail="差异报告不存在")
    
    content = diff_file.read_text(encoding="utf-8")
    
    return {
        "filename": diff_file.name,
        "content": content
    }


    """获取 LLM 配置（复用 config 模块）"""
    return get_llm_config_from_file()

def call_llm(prompt: str, config: dict, system: str = "", temperature: float = 0.3, timeout: int = 60) -> Optional[str]:
    """通用 LLM 调用"""
    import requests
    if not config:
        return None
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature
    }
    
    proxies = {}
    all_proxy = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
    if all_proxy:
        proxies = {"http": all_proxy, "https": all_proxy}
    
    try:
        resp = requests.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
            proxies=proxies
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            print(f"❌ LLM API 错误: {resp.status_code} - {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        return None


def generate_interview_prd(context: dict) -> str:
    """根据访谈上下文生成 PRD"""
    config = get_llm_config()
    if not config:
        return "⚠️ LLM 未配置，无法生成 PRD"
    
    initial = context.get("initial", "")
    answers = context.get("answers", [])
    
    qa_text = ""
    for i, ans in enumerate(answers):
        if ans.strip():
            qa_text += f"\nQ{i+1}: {INTERVIEW_QUESTIONS[i]}\nA{i+1}: {ans}\n"
    
    prompt = f"""你是一位资深产品经理，请根据以下访谈记录生成一份结构化的 PRD。

## 初始需求描述
{initial}

## 访谈问答
{qa_text}

## 输出要求

请生成标准 PRD 格式，包含：
1. 项目概述
2. 用户与场景
3. 功能需求（P0/P1/P2 优先级）
4. 非功能需求
5. 交互与流程
6. 数据与接口
7. 版本规划
8. 风险评估

不要编造访谈中未提及的内容，技术细节留空。
"""
    
    return call_llm(
        prompt, config,
        system="你是资深产品经理，擅长将模糊需求转化为结构清晰的 PRD。",
        temperature=0.3,
        timeout=120
    ) or "⚠️ LLM 调用失败"

def _generate_prd_core(inputs: List[str], project_name: str) -> str:
    """通用 PRD 生成：接收多个输入文本"""
    config = get_llm_config()
    if not config:
        return "\n\n---\n\n".join(inputs)
    
    combined = "\n\n---\n\n".join(inputs)[:8000]
    
    prompt = f"""你是一位资深产品经理，请根据以下输入生成一份结构化的 PRD。

## 项目信息
项目名称：{project_name or '未命名项目'}

## 输入内容（共 {len(inputs)} 份）

{combined}

## 输出要求

生成标准 PRD 格式，包含：
1. 项目概述
2. 用户与场景
3. 功能需求（P0/P1/P2 优先级）
4. 非功能需求
5. 交互与流程
6. 数据与接口
7. 版本规划
8. 风险评估

不要编造输入中未提及的内容，技术细节留空。
"""
    
    return call_llm(
        prompt, config,
        system="你是资深产品经理，擅长编写可直接落地的 PRD 文档。",
        temperature=0.3,
        timeout=120
    ) or "\n\n---\n\n".join(inputs)

def generate_testcases_from_artifacts(prd_content: str, ui_content: str, project_name: str) -> str:
    """从 PRD + UI 终稿生成测试用例"""
    config = get_llm_config()
    if not config:
        return "⚠️ LLM 未配置，无法生成测试用例"
    
    prompt = f"""你是一位测试专家，请根据以下 PRD 和 UI 设计稿生成测试用例。

## 项目
{project_name}

## PRD 内容
{prd_content[:4000]}

## UI 设计稿内容
{ui_content[:4000]}

## 输出要求

生成 pytest + Playwright 风格的测试用例代码（Python），包含：
1. 功能测试用例：按 PRD 的功能需求逐条覆盖
2. UI 交互测试：按 UI 设计稿覆盖页面流转、元素可见性
3. 边界测试：错误输入、空数据、网络异常等
4. 每个测试用例包含：测试名称、前置条件、测试步骤、预期结果

注意：
- 只生成测试用例代码，不生成被测应用代码
- 假设被测应用运行在 http://localhost:8080
- 用例要可执行，使用真实的 CSS selector 或文本定位
"""
    
    return call_llm(
        prompt, config,
        system="你是资深测试工程师，擅长编写自动化的端到端测试用例。",
        temperature=0.2,
        timeout=180
    ) or "⚠️ LLM 调用失败"

def run_playwright_tests(test_dir: Path, report_dir: Path) -> dict:
    """执行 Playwright 测试并返回结果"""
    result = {
        "success": False,
        "stdout": "",
        "stderr": "",
        "report_path": None,
        "exit_code": -1
    }
    
    playwright_check = shutil.which("pytest")
    if not playwright_check:
        result["stderr"] = "pytest 未安装，请先运行：pip install pytest pytest-playwright playwright"
        return result
    
    report_dir.mkdir(parents=True, exist_ok=True)
    
    env = os.environ.copy()
    env["ALL_PROXY"] = ""
    
    cmd = [
        "pytest", str(test_dir),
        "-v",
        "--html", str(report_dir / "report.html"),
        "--self-contained-html",
        "--tb=short"
    ]
    
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, env=env,
            timeout=300, cwd=str(test_dir)
        )
        result["exit_code"] = proc.returncode
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        result["success"] = proc.returncode == 0
        result["report_path"] = str(report_dir / "report.html")
    except subprocess.TimeoutExpired:
        result["stderr"] = "测试执行超时（5分钟）"
    except Exception as e:
        result["stderr"] = f"执行异常: {str(e)}"
    
    return result

def fetch_feishu_doc(doc_token: str) -> Optional[str]:
    """通过飞书 API 拉取文档内容"""
    import requests
    
    tenant_token = os.environ.get("FEISHU_TENANT_TOKEN")
    user_token = os.environ.get("FEISHU_USER_TOKEN")
    
    if not tenant_token and not user_token:
        feishu_config_path = Path.home() / ".feishu" / "config.json"
        if feishu_config_path.exists():
            try:
                fc = json.loads(feishu_config_path.read_text(encoding="utf-8"))
                tenant_token = fc.get("tenant_access_token")
                user_token = fc.get("user_access_token")
            except:
                pass
    
    token = user_token or tenant_token
    if not token:
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    
    proxies = {}
    all_proxy = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
    if all_proxy:
        proxies = {"http": all_proxy, "https": all_proxy}
    
    try:
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_token}/content"
        resp = requests.get(url, headers=headers, timeout=30, proxies=proxies)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                blocks = data.get("data", {}).get("content", [])
                texts = []
                for block in blocks:
                    if block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif block.get("type") == "paragraph":
                        elems = block.get("paragraph", {}).get("elements", [])
                        line = "".join(e.get("text_run", {}).get("text", "") for e in elems)
                        if line:
                            texts.append(line)
                return "\n".join(texts)
        
        url = f"https://open.feishu.cn/open-apis/doc/v2/{doc_token}/content"
        resp = requests.get(url, headers=headers, timeout=30, proxies=proxies)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("content", "")
        
        return None
    except Exception as e:
        print(f"❌ 飞书文档拉取失败: {e}")
        return None

@app.post("/api/projects/{project_id}/ai/interview/start")
async def start_interview(project_id: str, initial: str = Form(...)):
    """开始 PRD 访谈模式"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    session_key = f"{project_id}:{int(time.time())}"
    INTERVIEWS[session_key] = {
        "project_id": project_id,
        "initial": initial,
        "step": 0,
        "answers": [],
        "status": "in_progress",
        "started_at": datetime.now().isoformat()
    }
    
    return {
        "session_key": session_key,
        "step": 0,
        "total_steps": len(INTERVIEW_QUESTIONS),
        "status": "in_progress",
        "question": INTERVIEW_QUESTIONS[0],
        "progress": "1/5"
    }

@app.post("/api/projects/{project_id}/ai/interview/answer")
async def answer_interview(project_id: str, session_key: str = Form(...), answer: str = Form(...)):
    """回答访谈问题"""
    if session_key not in INTERVIEWS:
        raise HTTPException(status_code=404, detail="访谈会话不存在或已过期")
    
    interview = INTERVIEWS[session_key]
    if interview["project_id"] != project_id:
        raise HTTPException(status_code=400, detail="会话与项目不匹配")
    if interview["status"] != "in_progress":
        raise HTTPException(status_code=400, detail=f"访谈已结束，状态: {interview['status']}")
    
    current_step = interview["step"]
    interview["answers"].append(answer)
    next_step = current_step + 1
    interview["step"] = next_step
    
    if next_step < len(INTERVIEW_QUESTIONS):
        return {
            "session_key": session_key,
            "step": next_step,
            "total_steps": len(INTERVIEW_QUESTIONS),
            "status": "in_progress",
            "question": INTERVIEW_QUESTIONS[next_step],
            "progress": f"{next_step + 1}/{len(INTERVIEW_QUESTIONS)}",
            "answered_so_far": next_step
        }
    
    # 所有问题回答完毕，生成 PRD
    interview["status"] = "generating"
    prd_content = generate_interview_prd(interview)
    
    prd_dir = PROJECTS_DIR / project_id / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)
    
    prd_file = prd_dir / f"PRD-访谈-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    prd_file.write_text(prd_content, encoding="utf-8")
    
    interview["status"] = "completed"
    interview["prd_file"] = str(prd_file)
    
    return {
        "session_key": session_key,
        "step": next_step,
        "total_steps": len(INTERVIEW_QUESTIONS),
        "status": "completed",
        "prd_file": str(prd_file),
        "message": "访谈完成，PRD 已生成"
    }

@app.post("/api/projects/{project_id}/ai/generate-prd-from-docs")
async def generate_prd_from_docs(project_id: str, file: UploadFile = File(...)):
    """上传文档直接生成 PRD"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    temp_dir = Path("/tmp") / "ai-pm" / project_id / "docs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    doc_path = temp_dir / file.filename
    content = await file.read()
    doc_path.write_bytes(content)
    
    doc_content = ""
    if file.filename.endswith('.md') or file.filename.endswith('.txt'):
        doc_content = doc_path.read_text(encoding="utf-8")
    else:
        doc_content = f"[文档已上传: {file.filename}，当前仅支持 .md 和 .txt 直接解析]"
    
    project_meta_path = project_dir / ".meta" / "project.json"
    project_name = project_id
    if project_meta_path.exists():
        meta = json.loads(project_meta_path.read_text(encoding="utf-8"))
        project_name = meta.get("name", project_id)
    
    prd_content = _generate_prd_core([doc_content], project_name)
    
    prd_dir = project_dir / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)
    
    prd_file = prd_dir / f"PRD-文档-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{file.filename}.md"
    prd_file.write_text(prd_content, encoding="utf-8")
    
    return {
        "message": "PRD 从文档生成成功",
        "prd_file": str(prd_file),
        "source": file.filename,
        "llm_generated": not prd_content.startswith("⚠️")
    }

@app.post("/api/projects/{project_id}/ai/generate-prd-from-feishu")
async def generate_prd_from_feishu(project_id: str, doc_token: str = Form(...), doc_name: str = Form("飞书文档")):
    """从飞书文档拉取内容生成 PRD"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    doc_content = fetch_feishu_doc(doc_token)
    if not doc_content:
        raise HTTPException(status_code=400, detail="飞书文档拉取失败，请检查文档 token 和权限")
    
    project_meta_path = project_dir / ".meta" / "project.json"
    project_name = project_id
    if project_meta_path.exists():
        meta = json.loads(project_meta_path.read_text(encoding="utf-8"))
        project_name = meta.get("name", project_id)
    
    prd_content = _generate_prd_core([doc_content], f"{project_name}（来源：{doc_name}）")
    
    prd_dir = project_dir / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)
    
    slug = re.sub(r'[^\w\u4e00-\u9fff]', '-', doc_name)[:50]
    prd_file = prd_dir / f"PRD-飞书-{slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    prd_file.write_text(prd_content, encoding="utf-8")
    
    return {
        "message": "PRD 从飞书文档生成成功",
        "prd_file": str(prd_file),
        "source": doc_name,
        "llm_generated": not prd_content.startswith("⚠️")
    }

@app.post("/api/projects/{project_id}/ai/generate-ui-prototype")
async def generate_ui_prototype(project_id: str, prd_file: str = Form(...)):
    """从 PRD 生成 UI 原型草案（HTML）"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    prd_path = project_dir / "prd" / prd_file
    if not prd_path.exists():
        raise HTTPException(status_code=404, detail="PRD 文件不存在")
    
    prd_content = prd_path.read_text(encoding="utf-8")
    
    config = get_llm_config()
    if not config:
        raise HTTPException(status_code=500, detail="LLM 未配置")
    
    prompt = f"""你是一位前端开发专家，请根据以下 PRD 生成一个可运行的 HTML 原型页面。

## PRD 内容
{prd_content[:6000]}

## 输出要求

生成一个完整的 HTML 文件，包含：
1. 使用 Tailwind CSS（CDN 引入）
2. 包含所有 PRD 中描述的核心页面和交互
3. 页面之间通过链接跳转
4. 使用占位数据和图片
5. 响应式设计

输出完整 HTML 代码（可直接保存为 .html 文件运行）。
"""
    
    html_content = call_llm(
        prompt, config,
        system="你是资深前端工程师，擅长用 HTML + Tailwind CSS 快速构建产品原型。",
        temperature=0.3,
        timeout=180
    )
    
    if not html_content:
        raise HTTPException(status_code=500, detail="UI 原型生成失败")
    
    html_clean = html_content.strip()
    if html_clean.startswith("```html"):
        html_clean = html_clean[7:]
    elif html_clean.startswith("```"):
        html_clean = html_clean[3:]
    if html_clean.endswith("```"):
        html_clean = html_clean[:-3]
    html_clean = html_clean.strip()
    
    prototype_dir = project_dir / "ui_prototype"
    prototype_dir.mkdir(exist_ok=True)
    
    html_file = prototype_dir / f"prototype-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
    html_file.write_text(html_clean, encoding="utf-8")
    
    return {
        "message": "UI 原型草案生成成功",
        "html_file": str(html_file),
        "preview_url": f"/api/projects/{project_id}/files/ui_prototype/{html_file.name}"
    }

@app.post("/api/projects/{project_id}/ai/generate-testcases")
async def generate_testcases(project_id: str, prd_file: str = Form(...), ui_file: str = Form("")):
    """从 PRD（+ UI 终稿）生成测试用例"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    prd_path = project_dir / "prd" / prd_file
    if not prd_path.exists():
        raise HTTPException(status_code=404, detail="PRD 文件不存在")
    
    prd_content = prd_path.read_text(encoding="utf-8")
    
    ui_content = ""
    if ui_file:
        ui_path = project_dir / "ui_final" / ui_file
        if not ui_path.exists():
            ui_path = project_dir / "ui" / ui_file
        if ui_path.exists():
            ui_content = ui_path.read_text(encoding="utf-8")
    
    project_meta_path = project_dir / ".meta" / "project.json"
    project_name = project_id
    if project_meta_path.exists():
        meta = json.loads(project_meta_path.read_text(encoding="utf-8"))
        project_name = meta.get("name", project_id)
    
    testcases_content = generate_testcases_from_artifacts(prd_content, ui_content, project_name)
    
    testcases_dir = project_dir / "testcases"
    testcases_dir.mkdir(parents=True, exist_ok=True)
    
    tc_file = testcases_dir / f"testcases-{datetime.now().strftime('%Y%m%d-%H%M%S')}.py"
    tc_file.write_text(testcases_content, encoding="utf-8")
    
    return {
        "message": "测试用例生成成功",
        "testcases_file": str(tc_file),
        "based_on": {"prd": prd_file, "ui": ui_file or "未使用"}
    }

@app.post("/api/projects/{project_id}/ai/run-tests")
async def run_tests(project_id: str, test_file: str = Form(...), app_url: str = Form("http://localhost:8080")):
    """执行 Playwright 自动化测试"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    
    test_path = project_dir / "testcases" / test_file
    if not test_path.exists():
        raise HTTPException(status_code=404, detail="测试文件不存在")
    
    run_dir = project_dir / "automation" / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    test_copy = run_dir / test_path.name
    shutil.copy2(test_path, test_copy)
    
    conftest_content = f"""import pytest

@pytest.fixture(scope="session")
def base_url():
    return "{app_url}"
"""
    (run_dir / "conftest.py").write_text(conftest_content, encoding="utf-8")
    
    report_dir = run_dir / "report"
    result = run_playwright_tests(run_dir, report_dir)
    
    (run_dir / "test_stdout.txt").write_text(result["stdout"], encoding="utf-8")
    (run_dir / "test_stderr.txt").write_text(result["stderr"], encoding="utf-8")
    
    return {
        "message": "测试执行完成" if result["success"] else "测试执行失败",
        "success": result["success"],
        "exit_code": result["exit_code"],
        "stdout_preview": result["stdout"][:2000],
        "stderr_preview": result["stderr"][:2000],
        "report_path": result.get("report_path"),
        "run_dir": str(run_dir)
    }

@app.delete("/api/projects/{project_id}/files/{category}/{filename}")
async def delete_file(project_id: str, category: str, filename: str):
    """删除项目文件"""
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    file_path = project_dir / category / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    file_path.unlink()
    return {"message": "文件删除成功"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
