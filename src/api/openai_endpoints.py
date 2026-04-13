"""OpenAI 兼容的 API 端点 - 简化版本"""
from fastapi import APIRouter, HTTPException, Request, Header, Depends
from fastapi.responses import JSONResponse, StreamingResponse
import uuid
import time
import json
import re
from typing import Optional, List, Dict, Any

from src.core.config import config
from src.core.logging import logger
from src.core.client import OpenAIClient
from src.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatChoice,
    ChatMessage,
    UsageInfo,
)

router = APIRouter()

minimax_client = OpenAIClient(
    config.openai_api_key,
    config.openai_base_url,
    config.request_timeout,
    api_version=config.azure_api_version,
)


def parse_xml(content: str) -> tuple:
    """Parse MiniMax XML tool calls."""
    if not content or "<minimax:tool_call>" not in content:
        return content, []
    tool_calls = []
    pattern = re.compile(r'<minimax:tool_call>\s*<invoke name="([^"]+)">(.*?)</invoke>\s*</minimax:tool_call>', re.DOTALL)
    for m in pattern.finditer(content):
        tool_calls.append({"id": f"call_{uuid.uuid4().hex[:8]}", "type": "function", "function": {"name": m.group(1), "arguments": "{}"}})
    clean = pattern.sub("", content).strip()
    return clean if clean else None, tool_calls


def parse_response(response: dict) -> dict:
    """Parse MiniMax XML in response."""
    for choice in response.get("choices", []):
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""
        if "<minimax:tool_call>" in content:
            clean, tools = parse_xml(content)
            msg["content"] = clean
            msg["tool_calls"] = tools
            if tools:
                choice["finish_reason"] = "tool_calls"
    return response


def to_minimax_msgs(msgs: List[ChatMessage]) -> List[Dict]:
    """Convert messages to MiniMax format."""
    result = []
    for m in msgs:
        c = m.content if isinstance(m.content, str) else ""
        result.append({"role": m.role or "user", "content": c or ""})
    return result


async def stream_resp(req: ChatCompletionRequest, req_id: str, http_req: Request):
    """Stream MiniMax response."""
    body = {"model": config.big_model, "messages": to_minimax_msgs(req.messages), "stream": True}
    try:
        async for line in minimax_client.create_chat_completion_stream(body, req_id):
            if line.startswith("data: ") and line[6:].strip() != "[DONE]":
                yield line + "\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error(f"Stream error: {e}")
        raise


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest, http_req: Request):
    """Chat completions endpoint."""
    req_id = str(uuid.uuid4())
    body = {"model": config.big_model, "messages": to_minimax_msgs(req.messages)}
    
    if req.stream:
        return StreamingResponse(stream_resp(req, req_id, http_req), media_type="text/event-stream")
    else:
        resp = await minimax_client.create_chat_completion(body, req_id)
        resp = parse_response(resp)
        choices = [ChatChoice(index=c.get("index", 0), message=ChatMessage(role=c.get("message", {}).get("role", "assistant"), content=c.get("message", {}).get("content"), tool_calls=c.get("message", {}).get("tool_calls")), finish_reason=c.get("finish_reason", "stop")) for c in resp.get("choices", [])]
        usage = resp.get("usage", {})
        return ChatCompletionResponse(id=resp.get("id", f"chatcmpl-{req_id}"), created=int(time.time()), model=req.model, choices=choices, usage=UsageInfo(prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0), total_tokens=usage.get("total_tokens", 0)) if usage else None)


@router.get("/v1/models")
@router.get("/models")
async def list_models():
    """List available models."""
    return {"object": "list", "data": [{"id": config.big_model, "object": "model", "created": int(time.time()), "owned_by": "minimax"}]}
