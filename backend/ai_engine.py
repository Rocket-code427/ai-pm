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
    """获取 LLM 配置：优先配置文件，其次环境变量"""
    # 尝试从配置文件读取（被 main.py 和独立进程共用）
    try:
        import importlib.util
        config_path = Path(__file__).parent / "config.py"
        if config_path.exists():
            spec = importlib.util.spec_from_file_location("config", str(config_path))
            config_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_mod)
            cfg = config_mod.get_llm_config_from_file()
            if cfg:
                return cfg
    except Exception:
        pass
    
    # 降级：环境变量
    kim_key = os.environ.get("KIMI_API_KEY", "").strip()
    if kim_key:
        return {
            "provider": "kimi",
            "api_key": kim_key,
            "base_url": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-8k"
        }
    qwen_key = os.environ.get("QWEN_API_KEY", "").strip()
    if qwen_key:
        return {
            "provider": "qwen",
            "api_key": qwen_key,
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "model": "qwen-plus"
        }
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        return {
            "provider": "openai",
            "api_key": openai_key,
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
            {"role": "system", "content": "你是一个专业的会议纪要和需求分析助手。请分析文本，提取结构化信息。"},
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

def generate_minutes_with_llm(transcript_text, segments=None):
    """使用 LLM 生成结构化纪要（支持音频转录或纯文本输入）"""
    duration = segments[-1]["end"] if segments else 0
    
    config = get_llm_config()
    
    if config:
        print("🤖 调用 LLM 分析文本...")
        
        # 根据输入类型调整提示语
        is_text_input = segments is None
        source_type = "文字文档" if is_text_input else "转录文本"
        
        prompt = f"""请分析以下{source_type}，提取结构化信息。

{source_type}：
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
- **对于明显的笔误或常识性错误（如协议名拼写错误、明显不存在的术语、错别字），必须进行合理修正，不要保留错误原文**
- **示例**：转录文本说"蓝牙Black协议"，这是一个明显不存在的协议名，必须修正为"蓝牙"或"BLE"；说"卡片视列表"应为"卡片式列表"
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

def generate_minutes_fallback(transcript_text, segments=None):
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

def format_meeting_minutes(result, date="", title=""):
    """格式化会议纪要为 Markdown"""
    if not title:
        title = result.get("meeting_type", "会议")
    if not date:
        from datetime import datetime
        date = datetime.now().strftime("%Y-%m-%d")
    
    # 会议类型分类
    meeting_type = result.get("meeting_type", "其他")
    theme = result.get("theme", "")
    impact = result.get("impact", {})
    
    md = f"""# 会议纪要：{title}

> **日期**: {date}
> **时长**: {result.get('duration', 0):.0f} 秒
> **类型**: {meeting_type}
> **主题**: {theme}
> **影响范围**: {', '.join(impact.get('scope', [])) or '暂无'}
> **影响性质**: {impact.get('nature', '信息同步')}
> **影响摘要**: {impact.get('summary', '')}
> **LLM增强**: {'✅' if result.get('llm_enhanced') else '❌'}

---

## 摘要

{result.get('summary', '')}

---

## 议题

"""
    
    for topic in result.get('topics', []):
        md += f"- {topic}\\n"
    
    md += "\\n## 决策\\n\\n"
    for decision in result.get('decisions', []):
        md += f"- {decision}\\n"
    
    md += "\\n## 待办\\n\\n"
    for todo in result.get('todos', []):
        md += f"- [ ] {todo}\\n"
    
    md += "\\n## 技术特征\\n\\n"
    tech = result.get('tech_features', {})
    for category, items in tech.items():
        if items:
            md += f"**{category}**: {', '.join(items)}\\n"
    
    md += "\\n## 业务特征\\n\\n"
    business = result.get('business_features', {})
    for category, items in business.items():
        if items:
            md += f"**{category}**: {', '.join(items)}\\n"
    
    md += "\\n## 完整转录\\n\\n"
    md += f"```\\n{result.get('transcript', '')}\\n```\\n"
    
    return md

def extract_text_from_file(file_path):
    """从文件提取纯文本（支持 txt, md, pdf, docx）"""
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    
    # 纯文本文件
    if suffix in ['.txt', '.md', '.markdown', '.text']:
        return file_path.read_text(encoding='utf-8')
    
    # PDF
    if suffix == '.pdf':
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\\n"
            return text
        except ImportError:
            return f"⚠️ 需要安装 pypdf 才能解析 PDF: pip install pypdf"
        except Exception as e:
            return f"⚠️ PDF 解析失败: {e}"
    
    # Word
    if suffix in ['.docx', '.doc']:
        try:
            import docx
            doc = docx.Document(str(file_path))
            text = "\\n".join([para.text for para in doc.paragraphs if para.text.strip()])
            return text
        except ImportError:
            return f"⚠️ 需要安装 python-docx 才能解析 Word: pip install python-docx"
        except Exception as e:
            return f"⚠️ Word 解析失败: {e}"
    
    # 尝试作为文本读取
    try:
        return file_path.read_text(encoding='utf-8')
    except:
        return f"⚠️ 无法读取文件格式: {suffix}"

def generate_meeting_from_text(text_content, meeting_title=""):
    """从文字内容直接生成结构化会议纪要"""
    result = generate_minutes_with_llm(text_content, segments=None)
    
    if not meeting_title:
        meeting_title = result.get("meeting_type", "会议纪要")
    
    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d")
    md = format_meeting_minutes(result, date=date, title=meeting_title)
    
    return {
        "minutes": md,
        "summary": result,
        "title": meeting_title
    }

def generate_requirement_from_text(text_content, req_name=""):
    """从文字内容生成结构化需求文档"""
    config = get_llm_config()
    
    if not config:
        return None
    
    prompt = f"""你是一位资深产品经理，请分析以下文字内容，提取并整理为结构化的需求文档。

原始内容：
{text_content[:8000]}

请输出以下格式的需求文档（Markdown 格式，不要代码块）：

# [需求名称]

> **来源**: 文字文档提取
> **生成时间**: [当前日期]
> **状态**: 草稿（待确认）

---

## 需求概述

[一句话描述需求目标和价值]

## 用户与场景

[目标用户群体及使用场景]

## 功能需求

### P0 - 必须有
- [ ] 功能1
- [ ] 功能2

### P1 - 应该有
- [ ] 功能3

### P2 - 可以有
- [ ] 功能4

## 非功能需求

- 性能：...
- 安全：...
- 兼容性：...

## 技术约束

[从原文中提取的技术特征]

## 待办事项

- [ ] 待办1
- [ ] 待办2

## 备注

[原始内容中的其他有价值信息]

注意：
- 只整理原文中明确提到的内容，不要编造
- 如果原文信息不足，留空或标记为"待补充"
- 对于明显的笔误进行修正
"""
    
    llm_result = call_llm(prompt, config)
    
    if llm_result:
        return llm_result
    else:
        return None

def main():
    """命令行入口：转录音频文件"""
    import argparse
    parser = argparse.ArgumentParser(description="AI-PM 转录引擎")
    parser.add_argument("audio", help="音频文件路径")
    parser.add_argument("-o", "--output", default=".", help="输出目录")
    parser.add_argument("--model", default="small", help="Whisper 模型大小")
    args = parser.parse_args()
    
    # 转录
    result = transcribe_audio(args.audio, args.model)
    
    # 生成结构化纪要
    minutes = generate_minutes_with_llm(result["text"], result.get("segments", []))
    
    # 格式化
    date = os.path.basename(args.audio).split('.')[0]
    md = format_meeting_minutes(minutes, date=date)
    
    # 保存
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    minutes_file = output_dir / f"会议纪要-{date}.md"
    minutes_file.write_text(md, encoding='utf-8')
    
    # 保存元数据
    meta = {
        "audio": args.audio,
        "date": date,
        "duration": minutes["duration"],
        "topics_count": len(minutes["topics"]),
        "decisions_count": len(minutes["decisions"]),
        "todos_count": len(minutes["todos"]),
        "llm_enhanced": minutes["llm_enhanced"]
    }
    meta_file = output_dir / f"{date}.json"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    
    print(f"✅ 会议纪要已保存: {minutes_file}")
    print(json.dumps({
        "minutes_file": str(minutes_file),
        "meta_file": str(meta_file),
        "summary": {
            "topics": minutes["topics"],
            "decisions": minutes["decisions"],
            "todos": minutes["todos"],
            "summary": minutes["summary"]
        }
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
