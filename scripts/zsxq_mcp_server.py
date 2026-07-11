#!/usr/bin/env python3
"""
ZSXQ MCP Server — 让 AI 直接读取知识星球内容。
支持 Claude Desktop、Cursor、Codex 等 MCP 客户端接入。

配置 Claude Desktop (`claude_desktop_config.json`):
{
  "mcpServers": {
    "zsxq": {
      "command": "python",
      "args": ["路径/zsxq_mcp_server.py"],
      "env": { "ZSXQ_TOKEN": "你的token" }
    }
  }
}
"""

import os, sys, json, asyncio, base64
from pathlib import Path

# ═══ Playwright ═══
from playwright.async_api import async_playwright

# ═══ MCP SDK ═══
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

# ═══════════════════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════════════════

BASE_URL = "https://api.zsxq.com/v2"
_browser = None
_page = None
_playwright = None


def _find_chrome():
    import glob as _glob
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ms-playwright")
    candidates = _glob.glob(os.path.join(base, "chromium-*", "chrome-win*", "chrome.exe"))
    if candidates:
        return sorted(candidates)[-1]
    candidates = _glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright", "chromium-*", "chrome-linux*", "chrome"))
    return sorted(candidates)[-1] if candidates else "chromium"


async def _start_browser():
    global _playwright, _browser, _page
    token = os.environ.get("ZSXQ_TOKEN", "")
    if not token:
        # 尝试从 config.json 读取
        config_path = Path(__file__).parent / "config.json"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                token = json.load(f).get("zsxq_access_token", "")
    if not token:
        raise RuntimeError("请设置 ZSXQ_TOKEN 环境变量或在 config.json 中配置 zsxq_access_token")

    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch_persistent_context(
        os.path.join(os.environ.get("TEMP", "/tmp"), "zsxq-mcp"),
        headless=True,
        executable_path=_find_chrome(),
        args=["--no-sandbox"],
        viewport={"width": 1280, "height": 800},
    )
    await _browser.add_cookies([
        {"name": "zsxq_access_token", "value": token, "domain": ".zsxq.com", "path": "/"},
        {"name": "zsxq_access_token", "value": token, "domain": "api.zsxq.com", "path": "/"},
    ])
    pages = _browser.pages
    _page = pages[0] if pages else await _browser.new_page()
    await _page.goto("https://wx.zsxq.com", wait_until="domcontentloaded", timeout=20000)
    await _page.wait_for_timeout(1500)
    return True


async def _call_api(path, params=None):
    """通过浏览器发起 API 请求."""
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    for attempt in range(3):
        try:
            resp = await _page.evaluate("""
                async (url) => {
                    const r = await fetch(url, { credentials: "include" });
                    return await r.json();
                }
            """, url)
            if resp.get("succeeded", True):
                return resp.get("resp_data", resp)
            if resp.get("code") == 1059:
                await asyncio.sleep((attempt + 1) * 3)
                continue
            return {"error": str(resp)}
        except Exception as e:
            if attempt == 2:
                return {"error": str(e)}
            await asyncio.sleep(2)
    return {"error": "重试耗尽"}


# ═══════════════════════════════════════════════════════
# MCP Server
# ═══════════════════════════════════════════════════════

server = Server("zsxq-mcp")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="zsxq_list_groups",
            description="列出当前账号已加入的所有知识星球及其基本信息",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="zsxq_list_topics",
            description="获取指定星球的帖子列表，支持分页",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "string",
                        "description": "星球 ID（数字）",
                    },
                    "count": {
                        "type": "integer",
                        "description": "每页数量，默认 20",
                        "default": 20,
                    },
                    "end_time": {
                        "type": "string",
                        "description": "翻页标记（上一页返回的 next_end_time），首次留空",
                    },
                },
                "required": ["group_id"],
            },
        ),
        Tool(
            name="zsxq_get_topic",
            description="获取单条帖子的完整内容，包含正文、图片、附件信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic_id": {
                        "type": "string",
                        "description": "帖子 ID（数字）",
                    },
                },
                "required": ["topic_id"],
            },
        ),
        Tool(
            name="zsxq_get_file_url",
            description="获取附件的下载链接",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "文件 ID（数字）",
                    },
                },
                "required": ["file_id"],
            },
        ),
        Tool(
            name="zsxq_search",
            description="在星球内搜索帖子（按关键词或时间范围）",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "string",
                        "description": "星球 ID",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "count": {
                        "type": "integer",
                        "description": "返回数量，默认 20",
                        "default": 20,
                    },
                },
                "required": ["group_id", "keyword"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "zsxq_list_groups":
        data = await _call_api("/groups")
        groups = data.get("groups", [])
        result = []
        for g in groups:
            result.append({
                "group_id": str(g.get("group_id", "")),
                "name": g.get("name", "未命名"),
                "background_url": g.get("background_url", ""),
                "member_count": g.get("members_count", 0),
                "topics_count": g.get("topics_count", 0),
            })
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "zsxq_list_topics":
        group_id = arguments["group_id"]
        count = arguments.get("count", 20)
        end_time = arguments.get("end_time")
        params = {"scope": "all", "count": count}
        if end_time:
            params["end_time"] = str(end_time)
        data = await _call_api(f"/groups/{group_id}/topics", params)
        topics = data.get("topics", [])
        next_end_time = data.get("next_end_time", "")
        result = {
            "next_end_time": next_end_time,
            "count": len(topics),
            "topics": [],
        }
        for t in topics:
            author = _extract_author(t)
            text, images, files = _extract_content(t)
            result["topics"].append({
                "topic_id": str(t.get("topic_id", "")),
                "type": t.get("type", "talk"),
                "title": t.get("title", ""),
                "create_time": str(t.get("create_time", "")),
                "author": author,
                "text": text[:2000],
                "image_count": len(images),
                "file_count": len(files),
                "files": files,
                "likes": t.get("likes_count", 0),
                "comments": t.get("comments_count", 0),
            })
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "zsxq_get_topic":
        tid = arguments["topic_id"]
        data = await _call_api(f"/topics/{tid}")
        if data is None or "error" in data:
            return [TextContent(type="text", text=json.dumps({"error": str(data)}, ensure_ascii=False))]
        topic = data.get("topic", data)
        author = _extract_author(topic)
        text, images, files = _extract_content(topic)
        result = {
            "topic_id": str(topic.get("topic_id", "")),
            "type": topic.get("type", "talk"),
            "title": topic.get("title", ""),
            "create_time": str(topic.get("create_time", "")),
            "author": author,
            "text": text,
            "images": images,
            "files": files,
            "likes": topic.get("likes_count", 0),
            "comments": topic.get("comments_count", 0),
            "readings": topic.get("readings_count", 0),
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "zsxq_get_file_url":
        fid = arguments["file_id"]
        data = await _call_api(f"/files/{fid}/download_url")
        if data and "download_url" in data:
            return [TextContent(type="text", text=data["download_url"])]
        return [TextContent(type="text", text=json.dumps({"error": "获取失败"}, ensure_ascii=False))]

    elif name == "zsxq_search":
        group_id = arguments["group_id"]
        keyword = arguments["keyword"]
        count = arguments.get("count", 20)
        params = {"scope": "all", "count": count, "q": keyword}
        data = await _call_api(f"/groups/{group_id}/topics", params)
        topics = data.get("topics", [])
        result = {
            "keyword": keyword,
            "count": len(topics),
            "results": [],
        }
        for t in topics:
            text, _, _ = _extract_content(t)
            result["results"].append({
                "topic_id": str(t.get("topic_id", "")),
                "title": t.get("title", ""),
                "snippet": text[:300],
                "create_time": str(t.get("create_time", "")),
                "author": _extract_author(t),
            })
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    else:
        raise ValueError(f"Unknown tool: {name}")


# ═══ 工具函数 ═══

def _extract_author(topic):
    author = topic.get("author") or {}
    if author.get("name"):
        return author["name"]
    for key in ("talk", "question", "task", "solution"):
        block = topic.get(key) or {}
        owner = block.get("owner") or {}
        if owner.get("name"):
            return owner["name"]
    return ""


def _extract_content(topic):
    content = topic.get("talk") or topic.get("question") or topic.get("task") or topic.get("solution") or {}
    text = content.get("text", "")
    images = [img.get("large", {}).get("url") or img.get("original", {}).get("url", "")
              for img in content.get("images", [])]
    files = [{"name": f.get("name", ""), "file_id": str(f.get("file_id", "")), "size": f.get("size", 0)}
             for f in content.get("files", [])]
    return text, images, files


# ═══════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════

async def main():
    await _start_browser()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())