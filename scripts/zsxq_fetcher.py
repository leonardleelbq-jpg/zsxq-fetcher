#!/usr/bin/env python3
"""
知识星球帖子抓取工具 v2 — Playwright 浏览器 + SQLite 去重 + 增量更新。
用法:
  python zsxq_fetcher.py --list                       # 列出星球
  python zsxq_fetcher.py -g "数局"                     # 全量抓取
  python zsxq_fetcher.py -g "数局" --incremental       # 只抓新帖
  python zsxq_fetcher.py -g "数局" --download-files    # 含附件下载
"""

import json, os, re, sys, time, argparse, base64, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "https://api.zsxq.com/v2"
DATA_DIR = Path(__file__).parent / "data"
CONFIG_PATH = Path(__file__).parent / "config.json"
DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "zsxq.db"
DB_PATH = DATA_DIR / "zsxq.db"
INTERVAL = 1.5
# Auto-detect Playwright Chromium
def _find_chrome():
    import glob as _glob
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ms-playwright")
    candidates = _glob.glob(os.path.join(base, "chromium-*", "chrome-win*", "chrome.exe"))
    if candidates:
        return sorted(candidates)[-1]
    # fallback for non-Windows
    candidates = _glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright", "chromium-*", "chrome-linux*", "chrome"))
    return sorted(candidates)[-1] if candidates else "chromium"

CHROME_PATH = _find_chrome()


# ═══════════════════════════════════════════════════════
# 数据库
# ═══════════════════════════════════════════════════════

def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            topic_id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            group_name TEXT NOT NULL,
            create_time TEXT NOT NULL,
            type TEXT,
            title TEXT,
            author TEXT,
            text TEXT,
            images TEXT,
            files TEXT,
            likes_count INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            readings_count INTEGER DEFAULT 0,
            rewards_count INTEGER DEFAULT 0,
            raw_json TEXT,
            fetched_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fetch_state (
            group_id TEXT PRIMARY KEY,
            last_topic_time TEXT,
            last_fetch_at TEXT DEFAULT (datetime('now')),
            total_fetched INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS downloaded_files (
            file_id TEXT PRIMARY KEY,
            topic_id TEXT NOT NULL,
            group_id TEXT NOT NULL,
            name TEXT,
            size INTEGER,
            saved_path TEXT,
            downloaded_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def topic_exists(conn, topic_id):
    return conn.execute("SELECT 1 FROM topics WHERE topic_id=?", (str(topic_id),)).fetchone() is not None


def save_topic(conn, topic, group_id, group_name):
    d = topic_to_dict(topic)
    conn.execute("""
        INSERT OR IGNORE INTO topics
        (topic_id, group_id, group_name, create_time, type, title, author, text,
         images, files, likes_count, comments_count, readings_count, rewards_count, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(d["topic_id"]), str(group_id), group_name, str(d["create_time"]),
        d["type"], d["title"], d["author"], d["text"],
        json.dumps(d["images"], ensure_ascii=False),
        json.dumps(d["files"], ensure_ascii=False),
        d["likes_count"], d["comments_count"], d["readings_count"], d["rewards_count"],
        json.dumps(topic, ensure_ascii=False),
    ))


def get_last_fetch_time(conn, group_id):
    row = conn.execute(
        "SELECT last_topic_time FROM fetch_state WHERE group_id=?", (str(group_id),)
    ).fetchone()
    return row[0] if row else None


def update_fetch_state(conn, group_id, latest_time, count):
    conn.execute("""
        INSERT INTO fetch_state (group_id, last_topic_time, last_fetch_at, total_fetched)
        VALUES (?,?,datetime('now'),?)
        ON CONFLICT(group_id) DO UPDATE SET
            last_topic_time=excluded.last_topic_time,
            last_fetch_at=excluded.last_fetch_at,
            total_fetched=fetch_state.total_fetched + excluded.total_fetched
    """, (str(group_id), latest_time, count))
    conn.commit()


def file_already_downloaded(conn, file_id):
    return conn.execute(
        "SELECT 1 FROM downloaded_files WHERE file_id=?", (str(file_id),)
    ).fetchone() is not None


def mark_file_downloaded(conn, file_id, topic_id, group_id, name, size, path):
    conn.execute(
        "INSERT OR IGNORE INTO downloaded_files (file_id, topic_id, group_id, name, size, saved_path) VALUES (?,?,?,?,?,?)",
        (str(file_id), str(topic_id), str(group_id), name, size, path),
    )


# ═══════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def sanitize_name(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def _fmt_time(ts):
    if ts is None: return "?"
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    if isinstance(ts, str):
        ts = ts.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return ts[:19] if len(ts) >= 19 else str(ts)
    return str(ts)


# ═══════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════

def api_fetch(page, path, params=None, retries=3):
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    for attempt in range(retries):
        resp = page.evaluate("""
            async (url) => {
                const r = await fetch(url, { credentials: "include" });
                return await r.json();
            }
        """, url)
        if resp.get("succeeded", True):
            return resp.get("resp_data", resp)
        code = resp.get("code", 0)
        if code == 1059:
            wait = (attempt + 1) * 5
            print(f"    (限流 {wait}s...)")
            time.sleep(wait)
        elif code == 1007:
            return None
        else:
            raise RuntimeError(f"API {resp}")
    raise RuntimeError(f"API 重试耗尽: {resp}")


def list_groups(page):
    return api_fetch(page, "/groups").get("groups", [])


def fetch_topics(page, group_id, end_time=None, count=20):
    params = {"scope": "all", "count": count}
    if end_time:
        params["end_time"] = end_time
    data = api_fetch(page, f"/groups/{group_id}/topics", params)
    if data is None:
        return [], None
    return data.get("topics", []), data.get("next_end_time")


def fetch_download_url(page, file_id):
    resp = api_fetch(page, f"/files/{file_id}/download_url")
    if resp:
        return resp.get("download_url", "")
    return ""


# ═══════════════════════════════════════════════════════
# 内容提取
# ═══════════════════════════════════════════════════════

def extract_author(topic):
    author = topic.get("author") or {}
    if author.get("name"): return author["name"]
    for key in ("talk", "question", "task", "solution"):
        block = topic.get(key) or {}
        owner = block.get("owner") or {}
        if owner.get("name"): return owner["name"]
    return ""


def extract_topic_text(topic):
    content = topic.get("talk") or topic.get("question") or topic.get("task") or topic.get("solution") or {}
    text = content.get("text", "")
    images = [img.get("large", {}).get("url") or img.get("original", {}).get("url", "")
              for img in content.get("images", [])]
    files = [{"name": f.get("name", ""), "url": f.get("url", "")} for f in content.get("files", [])]
    return text, images, files


def extract_files_detail(topic):
    content = topic.get("talk") or topic.get("question") or topic.get("task") or topic.get("solution") or {}
    return [{"file_id": f.get("file_id"), "name": f.get("name", ""), "size": f.get("size", 0)}
            for f in content.get("files", [])]


def topic_to_dict(topic):
    text, images, files = extract_topic_text(topic)
    return {
        "topic_id": topic.get("topic_id"), "type": topic.get("type"),
        "title": topic.get("title", ""), "create_time": topic.get("create_time"),
        "text": text, "images": images, "files": files,
        "likes_count": topic.get("likes_count", 0),
        "comments_count": topic.get("comments_count", 0),
        "readings_count": topic.get("readings_count", 0),
        "rewards_count": topic.get("rewards_count", 0),
        "author": extract_author(topic),
    }


# ═══════════════════════════════════════════════════════
# 存储
# ═══════════════════════════════════════════════════════

def save_markdown(topics, group_id, group_name):
    d = DATA_DIR / sanitize_name(f"{group_id}_{group_name}") / "md"
    d.mkdir(parents=True, exist_ok=True)
    for t in topics:
        dd = topic_to_dict(t)
        ts = dd["create_time"]
        dp = _fmt_time(ts).replace("-", "")[:8] if ts else "nodate"
        path = d / f"{dp}_{dd['topic_id']}.md"
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                f.write(_to_markdown(dd, group_name))


def _to_markdown(d, group_name):
    lines = [
        f"# {d['title']}", "",
        f"- **作者**: {d['author']}", f"- **时间**: {_fmt_time(d['create_time'])}",
        f"- **类型**: {d['type']}",
        f"- **点赞**: {d['likes_count']} | **评论**: {d['comments_count']} | **阅读**: {d['readings_count']}",
        f"- **星球**: {group_name}", "", "---", "", d["text"],
    ]
    if d["images"]:
        lines += ["", "## 图片"] + [f"![]({u})" for u in d["images"]]
    if d["files"]:
        lines += ["", "## 附件"] + [f"- [{x['name']}]" for x in d["files"]]
    return "\n".join(lines)


def save_jsonl(topics, group_id, group_name):
    d = DATA_DIR / sanitize_name(f"{group_id}_{group_name}")
    d.mkdir(parents=True, exist_ok=True)
    p = d / "topics.jsonl"
    existing = set()
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    existing.add(json.loads(line)["topic_id"])
                except: pass
    with open(p, "a", encoding="utf-8") as f:
        for t in topics:
            tid = str(t.get("topic_id"))
            if tid not in existing:
                f.write(json.dumps(topic_to_dict(t), ensure_ascii=False) + "\n")
                existing.add(tid)


def download_file(page, download_url, save_path):
    resp = page.evaluate("""
        async (url) => {
            const r = await fetch(url);
            if (!r.ok) return null;
            const buf = await r.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
            return btoa(binary);
        }
    """, download_url)
    if resp:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(resp))
        return os.path.getsize(save_path)
    return 0


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="知识星球帖子抓取工具 v2")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--group", "-g", type=str)
    parser.add_argument("--incremental", "-i", action="store_true", help="只抓新帖")
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--format", choices=["jsonl", "md", "both"], default="both")
    parser.add_argument("--download-files", action="store_true", help="下载附件 (PDF等)")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    config = load_config()
    conn = init_db()

    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            os.path.join(os.environ["TEMP"], "zsxq-playwright-v2"),
            headless=args.headless,
            executable_path=CHROME_PATH,
            args=["--no-sandbox"],
            viewport={"width": 1280, "height": 800},
        )
        browser.add_cookies([
            {"name": "zsxq_access_token", "value": config["zsxq_access_token"], "domain": ".zsxq.com", "path": "/"},
            {"name": "zsxq_access_token", "value": config["zsxq_access_token"], "domain": "api.zsxq.com", "path": "/"},
        ])
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://wx.zsxq.com", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1500)

        # 列出星球
        print("[*] 获取星球列表...")
        groups = list_groups(page)
        print(f"  共 {len(groups)} 个星球:\n")
        for g in groups:
            fid = conn.execute("SELECT COUNT(*) FROM topics WHERE group_id=?", (str(g["group_id"]),)).fetchone()[0]
            last = get_last_fetch_time(conn, g["group_id"])
            info = f"已存{fid}条" if fid else "未抓取"
            if last: info += f", 上次:{last[:10]}"
            print(f"  ID: {g.get('group_id'):>14}    {g.get('name','?'):<12} [{info}]")
        if args.list:
            browser.close(); conn.close(); return

        # 选择目标
        target = None
        for g in groups:
            if args.group == str(g.get("group_id")) or args.group.lower() in g.get("name", "").lower():
                target = g; break
        if not target:
            print(f"[错误] 未找到: {args.group}"); browser.close(); conn.close(); sys.exit(1)

        group_id, group_name = target["group_id"], target["name"]
        incremental = args.incremental
        if incremental:
            last_time = get_last_fetch_time(conn, group_id)
            if last_time and last_time.strip():
                print(f"\n[*] 增量模式: 上次同步 {last_time[:16]}")
            else:
                last_time = None
                print(f"\n[*] 增量模式: 首次运行，将全量抓取")
        print(f"[*] 目标: {group_name} (ID: {group_id})")
        print(f"[*] 开始抓取...")

        end_time = None; page_num = 0; total = 0; skipped = 0
        file_count = 0; latest_time = ""

        while True:
            page_num += 1
            if args.max_pages and page_num > args.max_pages: break
            print(f"  第 {page_num} 页 ...", end=" ", flush=True)
            topics, next_et = fetch_topics(page, group_id, end_time)
            if topics is None:
                print("API 失败"); break

            # 去重：跳过已入库的
            new_topics = []
            for t in topics:
                tid = str(t["topic_id"])
                if topic_exists(conn, tid):
                    skipped += 1
                    continue
                # 增量模式：遇到早于上次记录的就停
                if incremental and last_time:
                    ct = str(t.get("create_time", ""))
                    if ct and ct < last_time:
                        new_topics.clear()
                        next_et = None
                        break
                new_topics.append(t)

            if not new_topics:
                print(f"无新帖 ({skipped}条已跳过), 完成"); break

            for t in new_topics:
                save_topic(conn, t, group_id, group_name)
                ct = str(t.get("create_time", ""))
                if ct > latest_time:
                    latest_time = ct
            total += len(new_topics)
            conn.commit()
            print(f"{len(new_topics)} 条 (累计 {total}, 跳过 {skipped})")

            # Markdown / JSONL 导出
            if args.format in ("md", "both"):
                save_markdown(new_topics, group_id, group_name)
            if args.format in ("jsonl", "both"):
                save_jsonl(new_topics, group_id, group_name)

            # 文件下载
            if args.download_files:
                for t in new_topics:
                    try:
                        tid = str(t["topic_id"])
                        detail = api_fetch(page, f"/topics/{tid}")
                        if detail is None: continue
                        topic_detail = detail.get("topic", detail)
                        for finfo in extract_files_detail(topic_detail):
                            fid = str(finfo["file_id"])
                            if file_already_downloaded(conn, fid):
                                continue
                            dl_url = fetch_download_url(page, fid)
                            if not dl_url: continue
                            fd = DATA_DIR / sanitize_name(f"{group_id}_{group_name}") / "files"
                            fd.mkdir(parents=True, exist_ok=True)
                            fname = sanitize_name(finfo["name"])
                            save_path = str(fd / f"{tid}_{fname}")
                            size = download_file(page, dl_url, save_path)
                            if size:
                                file_count += 1
                                mark_file_downloaded(conn, fid, tid, group_id, finfo["name"], size, save_path)
                                print(f"    PDF: {fname} ({size/1024:.0f} KB)")
                            time.sleep(0.4)
                    except Exception as e:
                        print(f"    !文件失败 {tid}: {str(e)[:60]}")
                conn.commit()

            if not next_et:
                print("  已到最后一页"); break
            end_time = next_et
            time.sleep(INTERVAL)

        # 更新状态：从数据库取最新时间确保准确
        row = conn.execute(
            "SELECT create_time FROM topics WHERE group_id=? ORDER BY create_time DESC LIMIT 1",
            (str(group_id),)
        ).fetchone()
        actual_latest = row[0] if row else ""
        if total > 0 or actual_latest:
            update_fetch_state(conn, group_id, actual_latest or latest_time, total)
        elif skipped > 0:
            update_fetch_state(conn, group_id, "", 0)

        print(f"\n[DONE] 新增 {total} 条, 跳过 {skipped} 条", end="")
        if file_count: print(f", 下载 {file_count} 个文件", end="")
        print(f"\n  数据: {DATA_DIR / sanitize_name(f'{group_id}_{group_name}')}")
        print(f"  数据库: {DB_PATH}")
        browser.close()
        conn.close()


if __name__ == "__main__":
    main()