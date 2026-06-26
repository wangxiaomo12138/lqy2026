"""加载 config.yaml"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if not cfg_path.exists():
        example = ROOT / "config.yaml.example"
        raise FileNotFoundError(
            f"未找到配置文件 {cfg_path}，请复制 {example.name} 为 config.yaml 并填写模型地址"
        )
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
