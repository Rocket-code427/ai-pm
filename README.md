# AI-PM

AI-PM 是一个**本地智能项目管理软件**，结合 AI 能力辅助产品和技术团队管理研发全链路。它会学习、沉淀、推荐历史方案，成为项目管理的智能伙伴。

> 🌐 开源地址：https://github.com/luosilan/ai-pm（待创建）
> 💻 适用平台：macOS / Windows / Linux
> 🤖 AI 依赖：本地 Whisper + LLM API（Kimi/Qwen/OpenAI）

---

## 核心能力

### 1. 多项目并行管理
- 项目卡片总览，每个项目独立工作空间
- 项目内按阶段组织：需求 → PRD → UI → 测试 → 自动化
- 产物自动关联

### 2. 智能会议纪要（已完成）
**输入**：录音文件 → 本地 Whisper 转录 → LLM 结构化分析  
**输出**：
- 议题列表、决策记录、待办事项
- 技术特征提取（通信协议/架构模式/设备类型）
- 业务特征提取（品类/模块/功能）
- 自动转为需求文档

### 3. 需求 → PRD 工作流（已完成）
- 会议纪要自动归档为需求文档（草稿）
- 多需求合并生成 PRD 草案
- 产物自动关联（会议纪要 ↔ 需求 ↔ PRD）

### 4. 知识沉淀与推荐（规划中）
- 技术方案维度：通信协议、架构模式、性能挑战
- UI 方案维度：页面结构、组件模式、交互模式
- 业务方案维度：品类/模块、功能逻辑、实现方案、踩坑记录
- 跨项目推荐：新项目自动匹配历史方案

### 5. UI 设计稿 → HTML 原型（规划中）
- 设计稿图片 → AI 视觉分析 → HTML + Tailwind CSS

### 6. 变更影响分析（规划中）
- PRD 修改 → AI 分析影响链 → 标记下游产物待更新

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | Python + FastAPI | API 接口、文件操作、AI 调用 |
| 前端 | HTML + Tailwind CSS + 原生 JS | 无框架，轻量，易打包 |
| 数据库 | SQLite | 项目索引、配置 |
| AI 处理 | Whisper（本地）+ LLM API | 语音转录 + 文本分析 |
| 打包 | PyInstaller | 生成 .app/.exe |

---

## 快速开始

### 开发模式

```bash
git clone https://github.com/luosilan/ai-pm.git
cd ai-pm
pip install -r requirements.txt
python3 ai-pm.py
# 自动打开浏览器 http://localhost:8080
```

### 环境配置

```bash
# 配置 LLM API（三选一）
export KIMI_API_KEY=sk-xxxx       # 推荐，国内直接访问
export QWEN_API_KEY=sk-xxxx
export OPENAI_API_KEY=sk-xxxx
```

---

## 项目结构

```
ai-pm/
├── README.md
├── requirements.txt
├── ai-pm.py              # 主入口
├── build.py              # 打包脚本
├── backend/
│   ├── main.py            # FastAPI 主应用
│   ├── ai_engine.py       # Whisper + LLM 分析
│   └── __init__.py
├── frontend/
│   ├── index.html         # 项目面板
│   ├── project.html       # 项目工作台
│   └── js/
│       ├── app.js         # 项目面板逻辑
│       └── project.js     # 工作台逻辑
└── templates/              # 模板文件
    └── meeting-minutes.md
```

---

## 功能状态

| 功能 | 状态 | 说明 |
|------|------|------|
| 项目面板 | ✅ | 创建/查看/列表 |
| 会议纪要 | ✅ | 录音转录 + LLM 结构化 + 自动转需求 |
| 需求文档 | ✅ | 自动归档 + 查看编辑 |
| PRD 生成 | ✅ | 多需求合并生成 |
| UI 原型 | ⏳ | 设计稿 → HTML（规划中） |
| 测试用例 | ⏳ | 从 PRD 生成（规划中） |
| 变更影响分析 | ⏳ | PRD 修改影响链（规划中） |
| 知识沉淀推荐 | ⏳ | 历史方案推荐（规划中） |

---

## 开发日志

### 2026-06-01
- 项目骨架搭建（FastAPI + 原生 HTML/JS）
- Whisper 本地转录集成（tiny/small 模型）
- LLM 结构化分析（Kimi API）
- 会议纪要 → 需求 → PRD 工作流打通
- 产物自动关联（meetings/ requirements/ prd/）

---

## 许可证

MIT License
