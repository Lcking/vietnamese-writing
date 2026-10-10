#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
viet_writer - 越南语写作引擎
通用 LLM 适配层:支持任意 OpenAI 兼容端点(GPT / Gemini / Kimi / 本地 Qwen)
"""
import os, json, urllib.request, urllib.error, time
from pathlib import Path

DEFAULT_CONFIG = {
    "base_url": os.environ.get("VIET_LLM_BASE_URL", "https://api.openai.com/v1"),
    "api_key":  os.environ.get("VIET_LLM_API_KEY", ""),
    "model":    os.environ.get("VIET_LLM_MODEL", "gpt-4o"),
    "max_tokens": 4000,
    "temperature": 0.7,
}

class LLMClient:
    def __init__(self, config=None):
        self.cfg = dict(DEFAULT_CONFIG)
        if config:
            self.cfg.update(config)
        if not self.cfg["api_key"]:
            raise ValueError("缺少 API Key。请设置 VIET_LLM_API_KEY 环境变量或在 config 中提供。")

    def chat(self, system, user, **kw):
        payload = {
            "model": self.cfg["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": kw.get("max_tokens", self.cfg["max_tokens"]),
            "temperature": kw.get("temperature", self.cfg["temperature"]),
        }
        url = self.cfg["base_url"].rstrip("/") + "/chat/completions"
        # 可选:关闭思考链(本地 Qwen3 等深度思考型模型,可大幅提速)
        if kw.get("disable_thinking") or self.cfg.get("disable_thinking"):
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.cfg['api_key']}",
            }, method="POST")
        last_err = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=kw.get("timeout", 180)) as r:
                    d = json.loads(r.read())
                ch = d["choices"][0]["message"]
                # 兼容带 reasoning 的模型(如 Qwen3):优先 content
                return (ch.get("content") or "").strip()
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM 调用失败: {last_err}")
