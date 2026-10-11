#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 适配层:支持任意 OpenAI 兼容端点(GPT / Gemini / Kimi / 本地 Qwen)

关键行为(对应评审要求):
  - 尊重显式调用参数:调用方传的参数 > 配置文件 > 默认值。不再无条件强制覆盖。
  - 错误分类重试:鉴权/参数错误(4xx,除 429)不重试;限流(429)与网络错误才退避重试。
  - 记录 finish_reason 与输出是否被截断,便于排查"输出不完整"类问题。
  - 设总超时,避免单次调用无限等待。
"""
import os, json, urllib.request, urllib.error, time

DEFAULT_CONFIG = {
    "base_url": os.environ.get("VIET_LLM_BASE_URL", "https://api.openai.com/v1"),
    "api_key": os.environ.get("VIET_LLM_API_KEY", ""),
    "model": os.environ.get("VIET_LLM_MODEL", "gpt-4o"),
    # 默认值只在"调用方与配置都未指定"时使用
    "max_tokens": int(os.environ.get("VIET_LLM_MAX_TOKENS", "4000")),
    "temperature": float(os.environ.get("VIET_LLM_TEMPERATURE", "0.7")),
    "timeout": int(os.environ.get("VIET_LLM_TIMEOUT", "180")),
    "max_retries": int(os.environ.get("VIET_LLM_MAX_RETRIES", "3")),
    "disable_thinking": False,
}


class LLMError(RuntimeError):
    """携带可判别类别的 LLM 调用错误。"""
    def __init__(self, msg, kind="unknown", status=None):
        super().__init__(msg)
        self.kind = kind      # auth | param | rate_limit | network | server | parse | unknown
        self.status = status


def _autofix_payload(payload, error_detail):
    """根据服务端 400 报错,推断参数该怎么改。返回 {要改的键: 新键 或 None(删除)}。
    只处理已知可修正情形;无法判断时返回空 dict(交给上层抛错)。"""
    d = (error_detail or "").lower()
    fixes = {}
    if "max_tokens" in d and "max_completion_tokens" in d and "max_tokens" in payload:
        fixes["max_tokens"] = "max_completion_tokens"
    if "temperature" in d and ("unsupported" in d or "not supported" in d):
        fixes["temperature"] = None
    if "chat_template_kwargs" in d and ("unsupported" in d or "unknown" in d or "not supported" in d):
        fixes["chat_template_kwargs"] = None
    return fixes


class LLMResult:
    """保留文本内容的同时携带元数据(finish_reason / truncated / usage)。
    用 str 语义:str(result) 得到文本;result.text 等价。"""
    __slots__ = ("text", "finish_reason", "usage", "model", "truncated")

    def __init__(self, text, finish_reason=None, usage=None, model=None):
        self.text = text
        self.finish_reason = finish_reason
        self.usage = usage or {}
        self.model = model
        self.truncated = (finish_reason == "length")

    def __str__(self):
        return self.text

    def __repr__(self):
        return f"LLMResult(len={len(self.text)}, finish_reason={self.finish_reason!r})"


class LLMClient:
    def __init__(self, config=None):
        self.cfg = dict(DEFAULT_CONFIG)
        if config:
            self.cfg.update({k: v for k, v in config.items() if v is not None})
        if not self.cfg["api_key"]:
            raise ValueError("缺少 API Key。请设置 VIET_LLM_API_KEY 环境变量或在 config 中提供。")

    def _resolve(self, kw, key):
        """参数优先:显式 kw > 配置 > 默认(DEFAULT_CONFIG 里已是默认)。"""
        if key in kw and kw[key] is not None:
            return kw[key]
        return self.cfg.get(key)

    def chat(self, system, user, **kw):
        max_tokens = self._resolve(kw, "max_tokens")
        temperature = self._resolve(kw, "temperature")
        timeout = self._resolve(kw, "timeout")
        retries = self._resolve(kw, "max_retries")

        payload = {
            "model": kw.get("model") or self.cfg["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        model = payload["model"]

        # 推理模型(gpt-5/6、o 系列等)拒绝 max_tokens 与自定义 temperature,
        # 需改用 max_completion_tokens。可用 VIET_LLM_REASONING_HINT=1 显式声明。
        reasoning = bool(kw.get("reasoning") or self.cfg.get("reasoning"))
        if not reasoning:
            m = model.lower()
            reasoning = any(
                m.startswith(p) for p in ("gpt-5", "gpt-6", "o1", "o3", "o4")
            )
        if reasoning:
            if max_tokens is not None:
                payload["max_completion_tokens"] = max_tokens
            # 推理模型通常只接受默认 temperature=1,不主动传
        else:
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if temperature is not None:
                payload["temperature"] = temperature
        # 关闭思考链(可大幅提速)
        # 不同厂商参数不同:智谱 GLM 用 thinking={type:disabled};
        # 本地 Qwen3 等用 chat_template_kwargs.enable_thinking=False。
        if kw.get("disable_thinking") or self.cfg.get("disable_thinking"):
            m = model.lower()
            if m.startswith(("glm", "chatglm", "zhipu")):
                payload["thinking"] = {"type": "disabled"}
            else:
                payload["chat_template_kwargs"] = {"enable_thinking": False}

        url = self.cfg["base_url"].rstrip("/") + "/chat/completions"
        data = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg['api_key']}",
        }

        last_err = None
        attempts = max(1, int(retries or 1))
        learned = {}  # 记住服务端的参数怪癖,避免重复试错
        for attempt in range(attempts):
            if learned:
                for drop, replace in learned.items():
                    if replace is None:
                        payload.pop(drop, None)
                    else:
                        if drop in payload:
                            payload[replace] = payload.pop(drop)
                data = json.dumps(payload).encode()
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read()
                d = json.loads(body)
                choice = d["choices"][0]
                ch = choice.get("message") or {}
                text = (ch.get("content") or "").strip()
                finish = choice.get("finish_reason")
                return LLMResult(text, finish_reason=finish,
                                 usage=d.get("usage"), model=d.get("model"))
            except urllib.error.HTTPError as e:
                status = e.code
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")[:400]
                except Exception:
                    pass
                if status in (401, 403):
                    raise LLMError(f"鉴权失败({status}):{detail}", kind="auth", status=status)
                if status == 429:
                    last_err = LLMError(f"限流(429):{detail}", kind="rate_limit", status=status)
                    # 限流:退避重试
                elif 400 <= status < 500:
                    # 参数类错误:尝试自动修正一次(推理模型/服务端怪癖)
                    fixed = _autofix_payload(payload, detail)
                    if fixed and fixed not in learned.values() and attempt + 1 < attempts:
                        learned.update(fixed)
                        last_err = LLMError(f"参数错误({status}),已自动修正重试:{detail}",
                                            kind="param", status=status)
                        continue
                    raise LLMError(f"请求参数错误({status}):{detail}", kind="param", status=status)
                else:
                    last_err = LLMError(f"服务端错误({status}):{detail}", kind="server", status=status)
            except urllib.error.URLError as e:
                last_err = LLMError(f"网络错误:{e.reason}", kind="network")
            except json.JSONDecodeError as e:
                # 解析失败一般不因重试而好转,但偶发截断可重试一次
                last_err = LLMError(f"响应解析失败:{e}", kind="parse")
            except KeyError as e:
                raise LLMError(f"响应结构异常(缺少字段 {e})", kind="parse")

            if attempt < attempts - 1:
                time.sleep(min(2 ** attempt, 8))  # 指数退避,封顶 8s

        raise last_err or LLMError("LLM 调用失败(未知原因)")
