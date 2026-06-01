#!/usr/bin/env python3
"""
AI 转录引擎 + LLM 结构化分析
用 Python 3.9 运行（Whisper 安装在此环境）
"""

import sys
import os
sys.path.insert(0, '/Users/luosilan/Library/Python/3.9/lib/python/site-packages')

import whisper
import soundfile as sf
import numpy as np
from scipy import signal
from pathlib import Path
import json
import re
import requests

# 加载模型（全局，避免重复加载）
_model = None
def get_model(model_size="small"):
    global _model
    if _model is None:
        print(f"🎯 加载 Whisper 模型: {model_size}")
        _model = whisper.load_model(model_size)
    return _model

def get_llm_config():
    """获取 LLM 配置"""
    # 优先级：Kimi > Qwen > OpenAI
    kim_key = os.environ.get("KIMI_API_KEY") or "sk-bazgRPS4SyE4Eb4xviUJB3GkZMetgbGzOZGsGcSSrDvaAxJb"
    if kim_key:
        return {
            "provider": "kimi",
            "api_key": kim_key,
            "base_url": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-8k"
        }
    elif os.environ.get("QWEN_API_KEY"):
        return {
            "provider": "qwen",
            "api_key": os.environ["QWEN_API_KEY"],
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "model": "qwen-plus"
        }
    elif os.environ.get("OPENAI_API_KEY"):
        return {
            "provider": "openai",
            "api_key": os.environ["OPENAI_API_KEY"],
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-3.5-turbo"
        }
    return None

def call_llm(prompt, config):
    """调用 LLM API"""
    if not config:
        return None
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "你是一个专业的会议纪要和需求分析助手。请分析会议转录文本，提取结构化信息。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    # 配置代理
    proxies = {}
    all_proxy = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
    if all_proxy:
        proxies = {
            "http": all_proxy,
            "https": all_proxy
        }
    
    # 根据任务类型调整超时
    timeout = 60 if "PRD" in prompt else 30
    
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

def transcribe_audio(audio_path, model_size="small"):
    """转录音频文件"""
    model = get_model(model_size)
    
    print(f"📂 读取音频: {audio_path}")
    audio, sr = sf.read(audio_path)
    
    # 确保单声道
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)
    
    # 重采样到 16kHz
    if sr != 16000:
        audio = signal.resample(audio, int(len(audio) * 16000 / sr))
    
    audio = audio.astype(np.float32)
    
    print(f"🎙️ 转录中...")
    result = model.transcribe(audio, language="zh", fp16=False, verbose=False)
    
    return result

def generate_minutes_with_llm(transcript_text, segments):
    """使用 LLM 生成结构化纪要"""
    duration = segments[-1]["end"] if segments else 0
    
    config = get_llm_config()
    
    if config:
        print("🤖 调用 LLM 分析转录文本...")
        
        prompt = f"""请分析以下会议转录文本，提取结构化信息。

转录文本：
{transcript_text}

请按以下 JSON 格式返回（不要包含 markdown 代码块标记，只返回纯 JSON）：
{{
  "topics": ["议题1", "议题2"],
  "decisions": ["决策1", "决策2"],
  "todos": ["待办1", "待办2"],
  "meeting_type": "需求评审",
  "theme": "本次会议核心主题：解决了什么问题",
  "impact": {{
    "scope": ["需求", "PRD"],
    "nature": "推进",
    "summary": "一句话描述对项目的影响"
  }},
  "tech_features": {{
    "通信协议": ["BLE", "MQTT"],
    "架构模式": ["网关中转"],
    "设备类型": ["传感器", "控制器"],
    "性能挑战": ["低功耗"]
  }},
  "business_features": {{
    "品类/模块": ["空调插件页"],
    "功能": ["智能场景推荐"],
    "实现方案": "简要描述"
  }},
  "summary": "会议核心内容摘要（100字以内）"
}}

注意：
- 如果某类信息不存在，返回空数组或空字符串
- 技术特征从文本中推断，不要虚构。但对于明显的笔误或常识性错误（如协议名拼写错误、明显不存在的术语），可以进行合理修正并在括号中标注原文
- 待办事项应包含负责人和截止时间（如果有）
- 使用简体中文
- **meeting_type 从以下列表中选择最匹配的**：项目启动、需求评审、UI评审、技术方案评审、站会、复盘回顾、其他
- **theme 必须明确本次会议解决了什么问题**，而不是重复议题列表
- **impact.nature 从以下选择**：推进（有进展）、调整（修改已有方案）、纠偏（纠正错误方向）、补充（新增未覆盖的内容）、信息同步（无实质变更）
- **impact.scope 标记本次会议影响了哪些工作阶段**：需求、PRD、UI、技术方案、测试、项目整体
"""
        
        llm_result = call_llm(prompt, config)
        
        if llm_result:
            try:
                # 清理可能的 markdown 标记
                clean_json = llm_result.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.startswith("```"):
                    clean_json = clean_json[3:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                clean_json = clean_json.strip()
                
                parsed = json.loads(clean_json)
                
                return {
                    "duration": duration,
                    "topics": parsed.get("topics", []),
                    "decisions": parsed.get("decisions", []),
                    "todos": parsed.get("todos", []),
                    "transcript": transcript_text,
                    "tech_features": parsed.get("tech_features", {}),
                    "business_features": parsed.get("business_features", {}),
                    "summary": parsed.get("summary", ""),
                    "meeting_type": parsed.get("meeting_type", "其他"),
                    "theme": parsed.get("theme", ""),
                    "impact": parsed.get("impact", {"scope": [], "nature": "信息同步", "summary": ""}),
                    "llm_enhanced": True
                }
            except json.JSONDecodeError as e:
                print(f"⚠️ LLM 返回格式错误，使用备用方案: {e}")
                print(f"LLM 原始输出: {llm_result[:200]}")
    
    # 备用：简单规则提取
    print("⚠️ LLM 不可用，使用规则提取...")
    return generate_minutes_fallback(transcript_text, segments)

def generate_minutes_fallback(transcript_text, segments):
    """备用：简单规则提取"""
    duration = segments[-1]["end"] if segments else 0
    
    # 按常见分隔符分割
    sentences = re.split(r'[。！？\.\n]', transcript_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    decisions = []
    todos = []
    topics = []
    
    for sentence in sentences:
        if any(kw in sentence for kw in ["决定", "确定", "采用", "选用", "通过", "共识"]):
            decisions.append(sentence)
        elif any(kw in sentence for kw in ["负责", "跟进", "完成", "截止", "deadline", "TODO"]):
            todos.append(sentence)
        elif any(kw in sentence for kw in ["讨论", "关于", "方案", "问题", "第一", "第二", "第三"]):
            topics.append(sentence)
    
    tech_features = extract_tech_features(transcript_text)
    
    return {
        "duration": duration,
        "topics": list(dict.fromkeys(topics))[:5],
        "decisions": list(dict.fromkeys(decisions))[:5],
        "todos": list(dict.fromkeys(todos))[:5],
        "transcript": transcript_text,
        "tech_features": tech_features,
        "business_features": {},
        "summary": "",
        "meeting_type": "其他",
        "theme": "",
        "impact": {"scope": [], "nature": "信息同步", "summary": ""},
        "llm_enhanced": False
    }

def extract_tech_features(text):
    """提取技术特征标签"""
    features = {
        "通信协议": [],
        "架构模式": [],
        "设备类型": [],
        "性能挑战": []
    }
    
    # 简单关键词匹配
    protocol_keywords = {"BLE": "蓝牙", "蓝牙": "蓝牙", "WiFi": "WiFi", "MQTT": "MQTT", "HTTP": "HTTP", "Zigbee": "Zigbee"}
    for kw, label in protocol_keywords.items():
        if kw.lower() in text.lower() or kw in text:
            features["通信协议"].append(label)
    
    arch_keywords = {"网关": "网关中转", "直连": "直连", "边缘": "边缘计算", "云": "云端"}
    for kw, label in arch_keywords.items():
        if kw in text:
            features["架构模式"].append(label)
    
    device_keywords = {"传感器": "传感器", "控制器": "控制器", "门锁": "门锁", "血糖仪": "血糖仪", "空调": "空调", "血糖": "血糖仪"}
    for kw, label in device_keywords.items():
        if kw in text:
            features["设备类型"].append(label)
    
    challenge_keywords = {"低功耗": "低功耗", "并发": "多设备并发", "离线": "离线可用", "延迟": "低延迟"}
    for kw, label in challenge_keywords.items():
        if kw in text:
            features["性能挑战"].append(label)
    
    # 去重
    for key in features:
        features[key] = list(dict.fromkeys(features[key]))
    
    return features

def format_minutes(minutes_data, audio_filename):
    """格式化为 Markdown"""
    from datetime import datetime
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    date = datetime.now().strftime("%Y-%m-%d")
    
    llm_badge = "🤖 LLM增强" if minutes_data.get("llm_enhanced") else "⚠️ 规则提取"
    meeting_type = minutes_data.get("meeting_type", "其他")
    theme = minutes_data.get("theme", "")
    impact = minutes_data.get("impact", {})
    
    # 影响标签
    nature_colors = {
        "推进": "🟢",
        "调整": "🟡",
        "纠偏": "🔴",
        "补充": "🔵",
        "信息同步": "⚪"
    }
    nature = impact.get("nature", "信息同步")
    nature_icon = nature_colors.get(nature, "⚪")
    scope = ", ".join(impact.get("scope", [])) if impact.get("scope") else "暂无"
    impact_summary = impact.get("summary", "")
    
    md = f"""# 会议纪要：{date}

**音频来源**: `{audio_filename}`  
**生成时间**: {now}  
**会议时长**: {minutes_data['duration']:.1f} 分钟  
**转录模型**: Whisper (本地)  
**分析方式**: {llm_badge}  

---

## 📌 会议概览

| 维度 | 内容 |
|------|------|
| **会议类型** | {meeting_type} |
| **核心主题** | {theme or "_未提取_"} |
| **影响性质** | {nature_icon} {nature} |
| **影响范围** | {scope} |
| **影响摘要** | {impact_summary or "_未提取_"} |

---

## 摘要

{minutes_data.get('summary', '_未生成摘要_')}

---

## 议题

"""
    if minutes_data['topics']:
        for i, topic in enumerate(minutes_data['topics'], 1):
            md += f"{i}. {topic}\n"
    else:
        md += "_（未识别到明确议题）_\n"
    
    md += "\n## 决策\n\n"
    if minutes_data['decisions']:
        for decision in minutes_data['decisions']:
            md += f"- [x] {decision}\n"
    else:
        md += "_（未识别到明确决策）_\n"
    
    md += "\n## 待办\n\n"
    if minutes_data['todos']:
        for todo in minutes_data['todos']:
            md += f"- [ ] {todo}\n"
    else:
        md += "_（未识别到待办事项）_\n"
    
    # 技术特征
    tech = minutes_data.get('tech_features', {})
    if any(tech.values()):
        md += "\n## 技术特征\n\n"
        for key, values in tech.items():
            if values:
                md += f"- **{key}**: {', '.join(values)}\n"
    
    # 业务特征
    business = minutes_data.get('business_features', {})
    if business:
        md += "\n## 业务特征\n\n"
        if business.get("品类/模块"):
            md += f"- **品类/模块**: {', '.join(business['品类/模块'])}\n"
        if business.get("功能"):
            md += f"- **功能**: {', '.join(business['功能'])}\n"
        if business.get("实现方案"):
            md += f"- **实现方案**: {business['实现方案']}\n"
    
    md += f"""
---

## 原始转录

<details>
<summary>点击展开（{len(minutes_data['transcript'])} 字）</summary>

```
{minutes_data['transcript']}
```

</details>

---

> 📝 本纪要由 AI 辅助生成，关键信息请人工核对确认。
"""
    
    return md

def process_meeting(audio_path, output_dir, model_size="small"):
    """完整流程：转录 → LLM分析 → 保存"""
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 转录
    result = transcribe_audio(str(audio_path), model_size)
    transcript = result["text"]
    segments = result["segments"]
    
    print(f"✅ 转录完成: {len(transcript)} 字")
    
    # 2. LLM 结构化分析
    minutes_data = generate_minutes_with_llm(transcript, segments)
    
    # 3. 格式化
    md_content = format_minutes(minutes_data, audio_path.name)
    
    # 4. 保存
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = output_dir / f"meeting-{timestamp}.md"
    output_file.write_text(md_content, encoding="utf-8")
    
    # 5. 保存元数据（用于知识沉淀）
    meta = {
        "audio_file": str(audio_path.name),
        "duration": minutes_data["duration"],
        "tech_features": minutes_data.get("tech_features", {}),
        "business_features": minutes_data.get("business_features", {}),
        "topics": minutes_data["topics"],
        "decisions": minutes_data["decisions"],
        "todos": minutes_data["todos"],
        "summary": minutes_data.get("summary", ""),
        "llm_enhanced": minutes_data.get("llm_enhanced", False),
        "meeting_type": minutes_data.get("meeting_type", "其他"),
        "theme": minutes_data.get("theme", ""),
        "impact": minutes_data.get("impact", {"scope": [], "nature": "信息同步", "summary": ""})
    }
    meta_file = output_dir / f"meeting-{timestamp}.json"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"✅ 纪要已保存: {output_file}")
    print(f"📊 摘要: {len(minutes_data['topics'])} 议题, {len(minutes_data['decisions'])} 决策, {len(minutes_data['todos'])} 待办")
    if minutes_data.get("llm_enhanced"):
        print(f"🤖 LLM 分析已应用")
    
    return {
        "minutes_file": str(output_file),
        "meta_file": str(meta_file),
        "summary": {
            "topics": len(minutes_data['topics']),
            "decisions": len(minutes_data['decisions']),
            "todos": len(minutes_data['todos']),
            "llm_enhanced": minutes_data.get("llm_enhanced", False)
        }
    }

def generate_prd_from_requirements(req_contents, project_name=""):
    """
    调用 LLM 将多份需求合并为结构化 PRD
    """
    combined_req = "\n\n---\n\n".join(req_contents)
    
    config = get_llm_config()
    if not config:
        return _fallback_prd(combined_req, project_name)
    
    prompt = f"""你是一位资深产品经理，请根据以下需求文档，生成一份结构化的 PRD（产品需求文档）。

## 项目信息
项目名称：{project_name or '未命名项目'}

## 需求文档内容（共 {len(req_contents)} 份）

{combined_req[:5000]}

## 输出要求

请生成标准 PRD 格式，包含以下章节（使用 Markdown，层级清晰）：

```markdown
# PRD：项目名称

## 1. 项目概述
- 背景与问题
- 目标与价值
- 范围界定（包含/不包含）

## 2. 用户与场景
- 目标用户画像
- 核心使用场景
- 用户旅程地图（简要）

## 3. 功能需求
### 3.1 核心功能
- 功能名称、描述、验收标准
### 3.2 辅助功能
### 3.3 功能优先级（P0/P1/P2）

## 4. 非功能需求
- 性能指标
- 安全要求
- 兼容性要求
- 可维护性要求

## 5. 交互与流程
- 页面/模块结构
- 核心流程图（用文字描述）
- 关键界面说明

## 6. 数据与接口
- 数据模型（关键实体）
- 接口定义（简要）

## 7. 版本规划
- MVP 范围
- 后续迭代方向

## 8. 风险评估
- 技术风险
- 业务风险
- 缓解措施

---
> 本 PRD 由 AI 基于需求文档自动生成，请产品经理审核确认。
```

注意：
- 不要编造需求文档中未提及的内容（如全新功能、未讨论的技术方案）
- 但对于明显的笔误或常识性错误（如协议名、技术术语的明显拼写错误），可以进行合理修正并标注「原文修正」
- 对于模糊的需求，标注「待澄清」
- 技术实现细节留空，由研发补充
- 使用简体中文
"""

    print("🤖 调用 LLM 生成 PRD...")
    llm_result = call_llm(prompt, config)
    
    if llm_result:
        clean = llm_result.strip()
        if clean.startswith("```markdown"):
            clean = clean[10:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return clean.strip()
    
    return _fallback_prd(combined_req, project_name)


def _fallback_prd(combined_req, project_name):
    """PRD 生成失败时的备用模板"""
    return f"""# PRD：{project_name or '未命名项目'}

## 1. 项目概述

基于需求文档生成。

## 2. 功能需求（待结构化）

{combined_req[:3000]}

---
> ⚠️ LLM 不可用，此为需求原文拼接。请手动整理为 PRD 格式。
"""


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="音频文件路径")
    parser.add_argument("--output", "-o", default=".", help="输出目录")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium"])
    args = parser.parse_args()
    
    result = process_meeting(args.audio, args.output, args.model)
    print(json.dumps(result, ensure_ascii=False))
