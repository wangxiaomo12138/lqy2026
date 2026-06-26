"""
模型服务客户端 — 对接你们封装的模型 API。

支持两种风格：
  - openai：OpenAI 兼容 /v1/chat/completions
  - http_json：自定义 POST，字段名在 config.yaml 的 http_json 段配置
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class ModelClient:
    def __init__(self, model_cfg: dict[str, Any]):
        self.cfg = model_cfg
        self.style = model_cfg.get("style", "openai")
        self.timeout = float(model_cfg.get("timeout_sec", 120))
        self.temperature = float(model_cfg.get("temperature", 0.2))

    def chat(self, system: str, user: str) -> str:
        if self.style == "http_json":
            return self._chat_http_json(user)
        return self._chat_openai(system, user)

    def _chat_openai(self, system: str, user: str) -> str:
        base_url = self.cfg["base_url"].rstrip("/")
        api_key = self.cfg.get("api_key", "")
        model = self.cfg["model"]

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"无法解析模型响应: {data}") from e

    def _chat_http_json(self, user: str) -> str:
        hj = self.cfg.get("http_json", {})
        endpoint = hj["endpoint"]
        headers = {"Content-Type": "application/json", **hj.get("headers", {})}

        body = _render_body(hj.get("body_template", {"query": "{query}"}), user)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(endpoint, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        path = hj.get("response_text_path", "answer")
        return _get_by_path(data, path)


def _render_body(template: dict[str, Any], query: str) -> dict[str, Any]:
    def walk(obj: Any) -> Any:
        if isinstance(obj, str):
            return obj.replace("{query}", query)
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(x) for x in obj]
        return obj

    return walk(template)


def _get_by_path(data: Any, path: str) -> str:
    cur = data
    for key in path.split("."):
        if not isinstance(cur, dict):
            raise ValueError(f"响应路径无效: {path}, 当前节点不是 dict")
        cur = cur[key]
    return str(cur)
