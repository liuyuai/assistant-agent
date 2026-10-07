# -*- coding: utf-8 -*-
"""模型封装：ChatOpenAI 指向 DeepSeek（OpenAI 兼容协议）。"""
from langchain_openai import ChatOpenAI

from .config import settings


def build_llm(**overrides) -> ChatOpenAI:
    """构建聊天模型。支持 bind_tools 做 Function Calling。"""
    params = dict(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.temperature,
        timeout=60,
    )
    params.update(overrides)
    return ChatOpenAI(**params)
