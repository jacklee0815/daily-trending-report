"""LLM 调用模块 (OpenAI 兼容接口).

为 top 商品生成一句中文卖点, 增强邮件可读性.
- 默认走 OpenAI (https://api.openai.com/v1)
- 通过 LLM_BASE_URL 切换到其他兼容服务: DeepSeek, 智谱 GLM, Moonshot, Ollama 等
- 失败容错: 网络/限流/Key 错误都不会让主流程崩, 静默回退到空字符串

环境变量:
  LLM_API_KEY    必填
  LLM_BASE_URL   默认 https://api.openai.com/v1
  LLM_MODEL      默认 gpt-4o-mini
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable

logger = logging.getLogger(__name__)

# 简单的进程内缓存, 避免一天内对同一商品重复调用
_cache: dict[str, str] = {}


def _get_client():
    """延迟初始化, 避免没装 openai 包也能跑(可选依赖)."""
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        # openai 1.x 风格
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed, LLM disabled")
        return None
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").strip()
    return OpenAI(api_key=api_key, base_url=base_url)


def _build_prompt(title: str, source: str, price: float) -> str:
    return (
        "你是一个跨境电商选品助手, 请根据商品标题给出一句简洁的中文卖点.\n"
        "要求: 12-25 字, 一句话点出商品的核心吸引力 (材质/功能/使用场景/独特卖点),\n"
        "不要包含价格信息, 不要用 '这款' '它' 等泛指词, 不要带句末标点.\n\n"
        f"商品: {title}\n"
        f"来源: {source} | 参考价格: ${price:.2f}\n\n"
        "请直接输出卖点一句话, 不要前缀说明."
    )


def generate_selling_point(title: str, source: str = "amazon", price: float = 0.0) -> str:
    """为单个商品生成一句中文卖点. 失败返回空串."""
    if not title:
        return ""
    cache_key = f"{source}::{title[:50]}"
    if cache_key in _cache:
        return _cache[cache_key]

    client = _get_client()
    if client is None:
        return ""

    model = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip()
    prompt = _build_prompt(title, source, price)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是跨境电商选品助手, 给出 12-25 字的中文卖点."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=80,
            temperature=0.7,
            timeout=20,
        )
        text = (resp.choices[0].message.content or "").strip().strip('"').strip('"').strip("'")
        # 去掉可能的换行/多余空白
        text = " ".join(text.split())
        # 截断
        if len(text) > 60:
            text = text[:60]
        _cache[cache_key] = text
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM call failed for '%s': %s", title[:30], exc)
        return ""


def batch_generate(items: Iterable[dict]) -> dict[str, str]:
    """批量生成. items: [{title, source, price}, ...]
    返回 {title_or_key: selling_point}."""
    out: dict[str, str] = {}
    for it in items:
        title = it.get("title", "")
        if not title:
            continue
        point = generate_selling_point(
            title=title,
            source=it.get("source", "amazon"),
            price=it.get("price", 0.0),
        )
        out[title] = point
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(generate_selling_point("Cute Cat Earphone Case for AirPods Pro 2", "amazon", 8.99))
