from __future__ import annotations

import os
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv

from ingest import get_collection
from settings import load_settings


load_dotenv()

DEFAULT_MODEL = "deepseek-chat"


def check_llm_connection() -> tuple[bool, str]:
    if not os.getenv("OPENAI_API_KEY"):
        return False, "未配置 OPENAI_API_KEY。"
    try:
        client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            messages=[{"role": "user", "content": "只回复 OK"}],
            temperature=0,
            max_tokens=5,
        )
        content = response.choices[0].message.content or ""
        return True, f"连接正常：{content.strip()}"
    except Exception as exc:
        return False, f"连接失败：{exc}"


def search(question: str, top_k: int = 5) -> list[dict[str, Any]]:
    settings = load_settings()
    collection = get_collection(reset=False, db_dir=settings["db_dir"])
    result = collection.query(query_texts=[question], n_results=top_k)
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    hits = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        hits.append({"text": document, "metadata": metadata or {}, "distance": distance})
    return hits


def answer_question(question: str, top_k: int = 5) -> tuple[str, list[dict[str, Any]]]:
    hits = search(question, top_k=top_k)
    if not hits:
        return "未在资料中找到。", []

    if not os.getenv("OPENAI_API_KEY"):
        first = hits[0]["text"].strip()
        answer = first[:500] + ("..." if len(first) > 500 else "")
        return f"未配置 OPENAI_API_KEY，先返回最相关原文摘录：\n\n{answer}", hits

    context = "\n\n".join(
        f"[来源 {index}]\n{format_source(hit['metadata'])}\n{hit['text']}"
        for index, hit in enumerate(hits, start=1)
    )
    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        messages=[
            {
                "role": "system",
                "content": "你只能根据提供的资料回答。资料不足时回答“未在资料中找到”。回答要简洁，并列出引用的来源编号。",
            },
            {"role": "user", "content": f"问题：{question}\n\n资料：\n{context}"},
        ],
        temperature=0.1,
    )
    return response.choices[0].message.content or "未在资料中找到。", hits


def extract_value(field_name: str, hits: list[dict[str, Any]]) -> tuple[str, str]:
    if not hits:
        return "", "未找到"

    if not os.getenv("OPENAI_API_KEY"):
        return hits[0]["text"].splitlines()[0][:180], "需要确认"

    context = "\n\n".join(hit["text"] for hit in hits[:3])
    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        messages=[
            {"role": "system", "content": "从资料中抽取字段值。只输出字段值；找不到就输出 未找到。"},
            {"role": "user", "content": f"字段：{field_name}\n\n资料：\n{context}"},
        ],
        temperature=0,
    )
    value = (response.choices[0].message.content or "").strip()
    if not value or value == "未找到":
        return "", "未找到"
    return value, "已填写"


def format_source(metadata: dict[str, Any]) -> str:
    location = []
    if metadata.get("page"):
        location.append(f"第 {metadata['page']} 页")
    if metadata.get("sheet"):
        location.append(f"Sheet: {metadata['sheet']}")
    if metadata.get("row_start"):
        location.append(f"行 {metadata['row_start']}-{metadata.get('row_end', metadata['row_start'])}")
    suffix = "，".join(location)
    return f"{metadata.get('file', '未知文件')}" + (f"（{suffix}）" if suffix else "")
