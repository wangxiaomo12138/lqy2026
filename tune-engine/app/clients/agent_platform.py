"""
Agent 平台客户端

★ 上线时你只需要改这个文件 ★

现在用 MockAgentClient 模拟合同解析：
- v1~v2 准确率故意低
- 每次 patch 后版本升高，准确率提升
这样你不接真实平台也能看到调优循环效果。
"""

import re
import time
import uuid
from typing import Any

import httpx

from app.config import AGENT_PLATFORM_URL, USE_MOCK_AGENT


class MockAgentClient:
    """
    模拟你们 Agent 平台的行为。
    entry_ref 格式: wf_contract_parse@vN
    版本号越高，模拟输出越接近标准答案。
    """

    # 内存里存每个版本的 skill 补丁（模拟配置版本库）
    _version_configs: dict[str, dict] = {}

    def run(self, entry_ref: str, input_data: dict, ground_truth: dict | None = None) -> dict:
        time.sleep(0.05)  # 模拟网络延迟

        version_no = self._parse_version(entry_ref)
        config = self._version_configs.get(entry_ref, {"rules": []})

        # 模拟：版本低时故意出错，版本高时输出正确答案
        output = self._simulate_parse(version_no, input_data, ground_truth or {}, config)

        return {
            "run_id": f"run_{uuid.uuid4().hex[:8]}",
            "status": "success",
            "output": output,
            "plan_trace": [
                {"step": 1, "intent": "选择合同解析 Skill", "status": "ok"},
                {"step": 2, "intent": "执行字段抽取", "status": "ok"},
                {"step": 3, "intent": "输出 JSON", "status": "ok"},
            ],
            "summary": f"合同解析完成，版本 {entry_ref}",
            "latency_ms": 120,
            "cost_tokens": 800,
        }

    def apply_patch(self, entry_ref: str, patch: dict) -> str:
        """模拟打补丁：生成新版本 entry_ref"""
        version_no = self._parse_version(entry_ref)
        new_ref = re.sub(r"@v\d+", f"@v{version_no + 1}", entry_ref)

        old_config = self._version_configs.get(entry_ref, {"rules": []})
        new_rules = list(old_config.get("rules", []))
        if patch.get("type") == "skill" and patch.get("content"):
            new_rules.append(patch["content"])

        self._version_configs[new_ref] = {"rules": new_rules}
        return new_ref

    def _parse_version(self, entry_ref: str) -> int:
        m = re.search(r"@v(\d+)", entry_ref)
        return int(m.group(1)) if m else 1

    def _simulate_parse(
        self, version_no: int, input_data: dict, ground_truth: dict, config: dict
    ) -> dict:
        """
        模拟逻辑：版本号 + 补丁规则数 越高，输出越接近标准答案。
        v1~v2 故意错很多，v3~v4 逐步变好，v5+ 基本全对。
        """
        if not ground_truth:
            return {"party_a": "未知", "party_b": "未知"}

        rules_bonus = len(config.get("rules", []))
        effective = version_no + rules_bonus  # 每打一次补丁，等效版本 +1

        output = {}
        total_fields = len(ground_truth)
        for i, (field, truth) in enumerate(ground_truth.items()):
            # effective>=5 全对；否则按字段序号逐步变对
            correct_count = min(total_fields, max(0, effective - 1))
            if effective >= 5 or i < correct_count:
                output[field] = truth
            else:
                output[field] = f"错误_{field}"

        return output


class RealAgentPlatformClient:
  """对接你们真实 Agent 平台 —— 上线时启用这个"""

  def __init__(self, base_url: str = AGENT_PLATFORM_URL):
      self.base_url = base_url.rstrip("/")

  def run(self, entry_ref: str, input_data: dict, ground_truth: dict | None = None) -> dict:
      with httpx.Client(timeout=120.0) as client:
          resp = client.post(
              f"{self.base_url}/internal/agent/run",
              json={
                  "entry_ref": entry_ref,
                  "input": input_data,
                  "trace_enabled": True,
              },
          )
          resp.raise_for_status()
          return resp.json()

  def apply_patch(self, entry_ref: str, patch: dict) -> str:
      with httpx.Client(timeout=30.0) as client:
          resp = client.post(
              f"{self.base_url}/internal/config/patch",
              json={"entry_ref": entry_ref, "patch": patch},
          )
          resp.raise_for_status()
          return resp.json()["new_entry_ref"]


def get_agent_client():
    if USE_MOCK_AGENT:
        return MockAgentClient()
    return RealAgentPlatformClient()
