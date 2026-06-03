#!/usr/bin/env python3
"""
AI-PM 用户配置管理
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict

CONFIG_DIR = Path.home() / ".ai-pm"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "version": "0.2.0",
    "llm": {
        "provider": "",
        "api_key": "",
        "base_url": "",
        "model": ""
    }
}

PROVIDER_PRESETS = {
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k"
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/api/v1",
        "model": "qwen-plus"
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-3.5-turbo"
    }
}


def _ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """加载用户配置"""
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    """保存用户配置"""
    _ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_llm_config_from_file() -> Optional[dict]:
    """
    从配置文件获取 LLM 配置。
    被 ai_engine.py（独立进程）和 main.py 共用。
    """
    config = load_config()
    llm = config.get("llm", {})
    provider = llm.get("provider", "").lower()
    api_key = llm.get("api_key", "").strip()

    if not provider or not api_key:
        return None

    preset = PROVIDER_PRESETS.get(provider, {})
    base_url = llm.get("base_url", "") or preset.get("base_url", "")
    model = llm.get("model", "") or preset.get("model", "")

    if not base_url:
        return None

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model
    }


def mask_key(key: str) -> str:
    """脱敏显示 API key"""
    if len(key) <= 12:
        return "****" if key else ""
    return key[:4] + "****" + key[-4:]


def config_to_display(config: dict) -> dict:
    """返回前端可安全展示的配置（脱敏）"""
    c = dict(config)
    llm = c.get("llm", {})
    if llm.get("api_key"):
        llm = dict(llm)
        llm["api_key"] = mask_key(llm["api_key"])
        c["llm"] = llm
    return c
