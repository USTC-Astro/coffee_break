"""
app.py — USTC Astro Coffee Break 展示网站
运行：uvicorn app:app --host 0.0.0.0 --port 10027
"""

import json
import re
import os
import threading
from pathlib import Path
from datetime import datetime

import requests
import markdown
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
TMPL_DIR = BASE_DIR / "templates"

BENTY_EMAIL    = "zbsu@mail.ustc.edu.cn"
BENTY_PASSWORD = os.environ.get("BENTY_PASSWORD", "")
ADMIN_TOKEN    = os.environ.get("ADMIN_TOKEN", "ustc1958")
BENTY_BASE     = "https://www.benty-fields.com"

app = FastAPI(title="USTC Astro Coffee")

# 挂载图片静态文件
@app.on_event("startup")
async def mount_static():
    figs_dir = DATA_DIR / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/data/figs", StaticFiles(directory=str(figs_dir)), name="figs")

    posters_dir = DATA_DIR / "posters"
    posters_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/data/posters", StaticFiles(directory=str(posters_dir)), name="posters")

jinja = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)

# ── Benty-Fields session（全局维持登录状态）────────────────────────────────
_benty_session = None
_session_lock  = threading.Lock()

def _make_tls_session() -> requests.Session:
    """创建兼容旧 TLS 的 session"""
    import ssl
    from requests.adapters import HTTPAdapter
    from urllib3.util.ssl_ import create_urllib3_context

    class TLSAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            ctx = create_urllib3_context()
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
            ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
            ctx.check_hostname = False
            kwargs["ssl_context"] = ctx
            super().init_poolmanager(*args, **kwargs)

    session = requests.Session()
    session.mount("https://", TLSAdapter())
    return session


def get_benty_session() -> requests.Session:
    global _benty_session
    with _session_lock:
        if _benty_session is not None:
            return _benty_session
        session = _make_tls_session()
        session.headers["User-Agent"] = "Mozilla/5.0"
        try:
            r = session.get(f"{BENTY_BASE}/login", timeout=15)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            payload = {"email": BENTY_EMAIL, "password": BENTY_PASSWORD}
            for inp in soup.select("form input[type=hidden]"):
                if inp.get("name"):
                    payload[inp["name"]] = inp.get("value", "")
            r2 = session.post(f"{BENTY_BASE}/login", data=payload, timeout=15, allow_redirects=True)
            if 'name="password"' in r2.text:
                raise RuntimeError("Benty-Fields 登录失败")
            _benty_session = session
        except Exception as e:
            print(f"[WARNING] Benty-Fields 登录失败：{e}")
            _benty_session = session  # 即使失败也缓存，避免反复重试
        return _benty_session


# ── 数据加载 ──────────────────────────────────────────────────────────────
def load_papers(json_path=None) -> list[dict]:
    json_file = json_path or DATA_DIR / "jc_papers.json"
    if not json_file.exists():
        return []
    with open(json_file, encoding="utf-8") as f:
        papers = json.load(f)
    for p in papers:
        p["has_summary"] = (DATA_DIR / f"{p['arxiv_id']}.md").exists()
    return papers


def get_mtime() -> str:
    json_file = DATA_DIR / "jc_papers.json"
    if not json_file.exists():
        return "未知"
    return datetime.fromtimestamp(json_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


# ── 路由 ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index():
    papers  = load_papers()
    updated = get_mtime()
    hist_dir = DATA_DIR / "history"
    dates = sorted([f.stem for f in hist_dir.glob("*.json")], reverse=True) if hist_dir.exists() else []
    tmpl = jinja.get_template("index.html")
    return tmpl.render(papers=papers, updated=updated, history_dates=dates, current_date=None)


@app.get("/paper/{arxiv_id}", response_class=HTMLResponse)
def paper(arxiv_id: str):
    if not re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
        raise HTTPException(status_code=400, detail="Invalid arXiv ID")
    md_file = DATA_DIR / f"{arxiv_id}.md"
    if not md_file.exists():
        raise HTTPException(status_code=404, detail="Summary not found")

    raw = md_file.read_text(encoding="utf-8")
    raw = re.sub(r"^<!--.*?-->\s*", "", raw, flags=re.DOTALL)
    content_html = markdown.markdown(raw, extensions=["tables", "fenced_code", "nl2br", "md_in_html"])

    papers = load_papers()
    meta   = next((p for p in papers if p["arxiv_id"] == arxiv_id), {})
    tmpl   = jinja.get_template("paper.html")
    return tmpl.render(arxiv_id=arxiv_id, content=content_html, meta=meta)


@app.get("/history/{date}", response_class=HTMLResponse)
def history_date(date: str):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(status_code=400, detail="Invalid date")
    hist_file = DATA_DIR / "history" / f"{date}.json"
    if not hist_file.exists():
        raise HTTPException(status_code=404, detail="No record for this date")
    papers = load_papers(hist_file)
    hist_dir = DATA_DIR / "history"
    dates  = sorted([f.stem for f in hist_dir.glob("*.json")], reverse=True)
    tmpl   = jinja.get_template("index.html")
    return tmpl.render(papers=papers, updated=date, history_dates=dates, current_date=date)


RATINGS = ["🔥 夯", "👑 顶级", "🧑‍💻 人上人", "😐 NPC", "💩 拉完了"]


# ── 咖啡投票 ──────────────────────────────────────────────────────────────
@app.get("/coffee_vote", response_class=HTMLResponse)
def coffee_vote_page():
    tmpl_file = TMPL_DIR / "coffee_vote.html"
    return tmpl_file.read_text(encoding="utf-8")


WEEK_RE = r"^(current|\d{4}-\d{2}-\d{2}-[A-Za-z]{3})$"


@app.get("/coffee_votes/{week}")
def get_coffee_votes(week: str):
    if not re.match(WEEK_RE, week):
        raise HTTPException(status_code=400, detail="Invalid week")
    votes_dir = DATA_DIR / "coffee_votes"
    votes_file = votes_dir / f"{week}.json"
    if not votes_file.exists():
        return JSONResponse({"votes": {}})
    return JSONResponse(json.loads(votes_file.read_text(encoding="utf-8")))


@app.post("/coffee_votes/{week}")
def post_coffee_vote(week: str, body: dict = {}):
    if not re.match(WEEK_RE, week):
        raise HTTPException(status_code=400, detail="Invalid week")
    drink     = body.get("drink", "").strip()
    name      = body.get("name", "anomaly").strip() or "anomaly"
    device_id = body.get("device_id", name)

    DRINKS = ["其他（填备注中）",  "生椰拿铁", "瑞之抹茶", "鲜萃轻轻茉莉",
  "柚C美式", "精萃澳瑞白", "柠C美式", "标准美式",
  "苹果C美式", "茉莉花香拿铁", "加浓美式",
  "生椰杨枝甘露", "橙C美式", "小黄油拿铁",
  "羽衣轻体果蔬茶", "小黄油美式", "轻椰茉莉拿铁", "冰吸生椰拿铁","埃塞金烘美式","苦瓜轻体美式", "陨石拿铁"]
    if drink not in DRINKS:
        raise HTTPException(status_code=400, detail="Invalid drink")

    import datetime as dt
    votes_dir = DATA_DIR / "coffee_votes"
    votes_dir.mkdir(exist_ok=True)
    votes_file = votes_dir / f"{week}.json"

    data = json.loads(votes_file.read_text(encoding="utf-8")) if votes_file.exists() else {"votes": {}}
    data["votes"][device_id] = {
        "drink": drink,
        "name": name,
        "time": dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    votes_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"ok": True, "votes": data["votes"]})


@app.post("/coffee_votes/{week}/cancel")
def cancel_coffee_vote(week: str, body: dict = {}):
    if not re.match(WEEK_RE, week):
        raise HTTPException(status_code=400, detail="Invalid week")
    device_id = body.get("device_id", "")
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id")

    votes_file = DATA_DIR / "coffee_votes" / f"{week}.json"
    if not votes_file.exists():
        return JSONResponse({"ok": True, "votes": {}})

    data = json.loads(votes_file.read_text(encoding="utf-8"))
    data["votes"].pop(device_id, None)
    votes_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"ok": True, "votes": data["votes"]})


@app.get("/refresh")
def refresh_coffee_votes(token: str = ""):
    """隐藏入口：把当前投票存档到 archive/ 后清空，然后跳回投票页。需 token。"""
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    import datetime as dt
    votes_dir  = DATA_DIR / "coffee_votes"
    votes_file = votes_dir / "current.json"

    # 存档现有票（有内容才存）
    if votes_file.exists():
        data = json.loads(votes_file.read_text(encoding="utf-8"))
        if data.get("votes"):
            archive_dir = votes_dir / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            (archive_dir / f"{stamp}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        votes_file.unlink()

    return RedirectResponse(url="/coffee_vote", status_code=303)


# ── 海报轮播 ──────────────────────────────────────────────────────────────
@app.get("/poster", response_class=HTMLResponse)
def poster_page():
    tmpl_file = TMPL_DIR / "poster.html"
    return tmpl_file.read_text(encoding="utf-8")


@app.get("/api/posters/{week}")
def list_posters(week: str):
    if not re.match(WEEK_RE, week):
        raise HTTPException(status_code=400, detail="Invalid week")
    posters_dir = DATA_DIR / "posters" / week
    if not posters_dir.exists():
        return JSONResponse({"images": []})
    # 支持的图片格式
    exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
    files = sorted(
        [f for f in posters_dir.iterdir() if f.suffix.lower() in exts],
        key=lambda f: f.name.lower()
    )
    images = [
        {"name": f.name, "url": f"/data/posters/{week}/{f.name}"}
        for f in files
    ]
    return JSONResponse({"images": images})


@app.get("/refresh_poster")
def refresh_posters(token: str = ""):
    """隐藏入口：把 current 海报图存档后清空，然后跳回海报页。需 token。"""
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    import datetime as dt
    import shutil
    cur_dir = DATA_DIR / "posters" / "current"
    if cur_dir.exists():
        files = [f for f in cur_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        if files:
            stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            archive_dir = DATA_DIR / "posters" / "archive" / stamp
            archive_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.move(str(f), str(archive_dir / f.name))

    return RedirectResponse(url="/poster", status_code=303)


@app.get("/ratings/{arxiv_id}")
def get_ratings(arxiv_id: str):
    if not re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
        raise HTTPException(status_code=400, detail="Invalid arXiv ID")
    ratings_file = DATA_DIR / "thoughts" / f"{arxiv_id}_ratings.json"
    if not ratings_file.exists():
        return JSONResponse({"ratings": {}})
    return JSONResponse(json.loads(ratings_file.read_text(encoding="utf-8")))


@app.post("/ratings/{arxiv_id}")
def save_rating(arxiv_id: str, token: str = "", body: dict = {}):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
        raise HTTPException(status_code=400, detail="Invalid arXiv ID")

    rating = body.get("rating", "")
    author = body.get("author", "Anonymous").strip() or "Anonymous"
    if rating not in RATINGS:
        raise HTTPException(status_code=400, detail="Invalid rating")

    import datetime as dt
    thoughts_dir = DATA_DIR / "thoughts"
    thoughts_dir.mkdir(exist_ok=True)
    ratings_file = thoughts_dir / f"{arxiv_id}_ratings.json"

    data = json.loads(ratings_file.read_text(encoding="utf-8")) if ratings_file.exists() else {"ratings": {}}
    # 按 device_id 覆盖（防止按错），显示时用 author 名字
    device_id = body.get("device_id", author)
    data["ratings"][device_id] = {
        "rating": rating,
        "author": author,
        "time": dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    ratings_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"ok": True, "ratings": data["ratings"]})


@app.get("/thoughts/{arxiv_id}")
def get_thoughts(arxiv_id: str):
    if not re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
        raise HTTPException(status_code=400, detail="Invalid arXiv ID")
    thoughts_file = DATA_DIR / "thoughts" / f"{arxiv_id}.json"
    if not thoughts_file.exists():
        return JSONResponse({"entries": []})
    return JSONResponse(json.loads(thoughts_file.read_text(encoding="utf-8")))


@app.post("/thoughts/{arxiv_id}")
def save_thought(arxiv_id: str, token: str = "", body: dict = {}):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
        raise HTTPException(status_code=400, detail="Invalid arXiv ID")

    import datetime as dt
    thoughts_dir = DATA_DIR / "thoughts"
    thoughts_dir.mkdir(exist_ok=True)
    thoughts_file = thoughts_dir / f"{arxiv_id}.json"

    if thoughts_file.exists():
        data = json.loads(thoughts_file.read_text(encoding="utf-8"))
    else:
        data = {"entries": []}

    text = body.get("text", "").strip()
    if text:
        data["entries"].append({
            "text": text,
            "author": body.get("author", "Anonymous"),
            "time": dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        thoughts_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return JSONResponse({"ok": True, "entries": data["entries"]})


@app.post("/mark_discussed/{arxiv_id}")
def mark_discussed(arxiv_id: str, token: str = ""):
    """标记论文为已讨论：同步到 Benty-Fields，移入历史，从当前列表移除。"""
    # Token 验证
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
        raise HTTPException(status_code=400, detail="Invalid arXiv ID")

    # 从本地找论文
    papers = load_papers()
    paper  = next((p for p in papers if p["arxiv_id"] == arxiv_id), None)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found in current agenda")

    vote_id  = paper.get("vote_id", "")
    benty_ok = False

    # 调用 Benty-Fields process_vote
    if vote_id:
        try:
            session = get_benty_session()
            r = session.post(
                f"{BENTY_BASE}/process_vote",
                json={"vote_id": vote_id},
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            benty_ok = r.status_code == 200
        except Exception as e:
            print(f"[WARNING] Benty mark_discussed 失败：{e}")

    # 移入历史存档（按日期追加）
    import datetime as dt
    today = dt.date.today().isoformat()
    hist_dir  = DATA_DIR / "history"
    hist_dir.mkdir(exist_ok=True)
    hist_file = hist_dir / f"{today}.json"

    if hist_file.exists():
        hist = json.loads(hist_file.read_text(encoding="utf-8"))
    else:
        hist = []

    # 避免重复
    if not any(p["arxiv_id"] == arxiv_id for p in hist):
        paper["discussed_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        hist.append(paper)
    hist_file.write_text(json.dumps(hist, indent=2, ensure_ascii=False), encoding="utf-8")

    # 从当前列表移除
    remaining = [p for p in papers if p["arxiv_id"] != arxiv_id]
    (DATA_DIR / "jc_papers.json").write_text(
        json.dumps(remaining, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return JSONResponse({"ok": True, "benty_ok": benty_ok, "arxiv_id": arxiv_id})
