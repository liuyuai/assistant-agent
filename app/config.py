# -*- coding: utf-8 -*-
"""全局配置：从 .env 读取，统一入口。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> dict:
    env = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


class Settings:
    def __init__(self) -> None:
        env = _load_env()
        self.llm_api_key: str = env.get("LLM_API_KEY", "")
        self.llm_base_url: str = env.get("LLM_BASE_URL", "https://api.deepseek.com")
        self.llm_model: str = env.get("LLM_MODEL", "deepseek-chat")
        self.temperature: float = float(env.get("TEMPERATURE", "0.3"))
        self.max_steps: int = int(env.get("MAX_STEPS", "8"))
        # 演示模式：不调真实模型，用规则模拟（供无 key 时展示）
        self.demo_mode: bool = env.get("DEMO_MODE", "false").lower() == "true"


settings = Settings()
