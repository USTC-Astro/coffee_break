#!/usr/bin/env python3
"""
fetch_benty.py
从 Benty-Fields Journal Club 抓取「当前 agenda」投票论文，
下载 LaTeX 源码，用 arxiv_on_deck_2 生成带图摘要 Markdown。

用法：
    export BENTY_PASSWORD="your_password"
    python fetch_benty.py --output-dir /path/to/arxiv_display/docs/

调试（跳过登录，直接解析本地 HTML）：
    python fetch_benty.py --debug-html manage_jc.html --no-summaries

依赖：
    pip install requests beautifulsoup4
    pip install git+https://github.com/mfouesneau/arxiv_on_deck_2.git
"""

import os, re, sys, json, time, shutil, logging, datetime, argparse, getpass, tempfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup

GROUP_ID    = 2179
BENTY_BASE  = "https://www.benty-fields.com"
LOGIN_URL   = f"{BENTY_BASE}/login"
AGENDA_URL  = f"{BENTY_BASE}/manage_jc?groupid={GROUP_ID}"
BENTY_EMAIL = "zbsu@mail.ustc.edu.cn"
TOP_N       = 10

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)


# ── 登录 ────────────────────────────────────────────────────────────────
def _make_session():
    """创建兼容旧 TLS 的 requests session"""
    import ssl
    import urllib3
    from requests.adapters import HTTPAdapter
    from urllib3.util.ssl_ import create_urllib3_context

    class TLSAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            ctx = create_urllib3_context()
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
            ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            kwargs["ssl_context"] = ctx
            super().init_poolmanager(*args, **kwargs)

    session = requests.Session()
    session.mount("https://", TLSAdapter())
    session.verify = False
    return session


def login(email, password):
    session = _make_session()
    session.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64)"
    r = session.get(LOGIN_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    payload = {"email": email, "password": password}
    for inp in soup.select("form input[type=hidden]"):
        if inp.get("name"):
            payload[inp["name"]] = inp.get("value", "")
    r2 = session.post(LOGIN_URL, data=payload, timeout=20, allow_redirects=True)
    r2.raise_for_status()
    if 'name="password"' in r2.text:
        raise RuntimeError("登录失败，请检查邮箱和密码")
    log.info("登录成功")
    return session


# ── 抓取页面 ─────────────────────────────────────────────────────────────
def fetch_agenda_html(session):
    r = session.get(AGENDA_URL, timeout=20)
    r.raise_for_status()
    log.info(f"获取 agenda 页面：{len(r.text)} bytes")
    return r.text


# ── 解析论文列表（只取当前 agenda，跳过 old votes）────────────────────────
def parse_papers(html):
    """
    只解析 id="new_votes_table" 表格里的论文（当前 agenda）。
    返回按票数降序排列的列表，每项：
        {"arxiv_id": "2604.13000", "votes": 4, "title": "...", "author": "..."}
    """
    soup = BeautifulSoup(html, "html.parser")

    # 只看当前 agenda 表格，彻底排除 old votes
    table = soup.find("table", id="new_votes_table")
    if not table:
        log.error("未找到 new_votes_table，页面结构可能已变化")
        return []

    papers = []
    for tr in table.find_all("tr", class_="table_entry"):
        # arXiv ID：从 paper_id= 链接提取
        a_tag = tr.find("a", href=re.compile(r"paper_id=\d{4}\.\d{4,5}"))
        if not a_tag:
            continue
        arxiv_id = re.search(r"paper_id=(\d{4}\.\d{4,5})", a_tag["href"]).group(1)

        # 标题
        title = a_tag.get_text(strip=True)
        title = title.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")

        # 票数：vote_count<id> div
        vote_div = tr.find("div", id=re.compile(rf"vote_count{re.escape(arxiv_id)}"))
        votes = int(vote_div.get_text(strip=True)) if vote_div else 0

        # 提取 vote_id（用于 Benty-Fields mark as discussed）
        vote_id_match = re.search(r"jc_entry(\d+)", tr.get("id", ""))
        vote_id = vote_id_match.group(1) if vote_id_match else ""

        # 作者
        ctext = tr.get_text(" ", strip=True)
        m_a = re.search(
            r"Author:\s*(.+?)(?:\s+Discussion leader|\s+Volunteer|\s+Vote\b|\s+Admin|$)",
            ctext
        )
        author = m_a.group(1).strip() if m_a else ""

        papers.append({"arxiv_id": arxiv_id, "votes": votes,
                       "title": title, "author": author[:200], "vote_id": vote_id})

    papers.sort(key=lambda x: x["votes"], reverse=True)
    # 只保留票数 >= 2 的论文
    papers = [p for p in papers if p["votes"] >= 2]
    log.info(f"当前 agenda 解析到 {len(papers)} 篇论文（≥2票）")
    return papers[:TOP_N]


# ── 生成带图摘要 Markdown ────────────────────────────────────────────────

N_FIGURES = 5   # 每篇论文最多展示几张图（按正文引用次数排序）


def _copy_figures(selected_figures, src_dir, fig_dir, arxiv_id):
    """把选出的图片从 src_dir 复制到 fig_dir，返回 (web_paths, caption, label, num) 列表。"""
    results = []
    for fig in selected_figures:
        images = fig.get("images", [])
        # 过滤各种空值情况
        if isinstance(images, str):
            images = [images] if images else []
        images = [p for p in images if p and p.strip()]
        if not images:
            continue

        web_paths = []
        for img_path in images:
            if img_path.startswith("http"):
                web_paths.append(img_path)
                continue
            fname = Path(img_path).name
            if not fname:
                continue
            dst = fig_dir / fname
            src_img = src_dir / img_path
            if src_img.exists():
                shutil.copy2(src_img, dst)
            else:
                found = list(src_dir.rglob(fname))
                if found:
                    shutil.copy2(found[0], dst)
                else:
                    log.warning(f"    找不到图片：{img_path}")
                    continue
            log.info(f"    复制图片：{fname}")
            web_paths.append(f"/data/figs/{arxiv_id}/{fname}")

        # 只有成功复制到图片才加入结果
        if web_paths:
            results.append((web_paths, fig.get("caption", ""),
                            fig.get("label", ""), fig.get("num", 0)))
        else:
            log.warning(f"    跳过无有效图片的 figure: label={fig.get('label','')}")
    return results


def _clean_latex(text: str) -> str:
    """清理 tex2md 无法处理的 LaTeX 宏。
    数学环境 $...$ 内的宏保留给 MathJax，只清理文字部分的宏。
    """
    if not text:
        return text

    # $\MacroName$ 形式（单纯宏名）-> 去掉 $，让后续处理宏名
    text = re.sub(r'\$\\([A-Za-z]+)(\{[^}]*\})?\$', lambda m: '\\' + m.group(1) + (m.group(2) or ''), text)
    # $_ text_$ 或 $_ text _$ 形式（斜体变量名）-> 直接变成 _text_
    text = re.sub(r'\$_\s*([^_$]+?)\s*_\$', r'_\1_', text)

    # 先把真正的数学块替换为占位符，保护其内容
    math_blocks = []
    def save_math(m):
        math_blocks.append(m.group(0))
        return f"\x00MATH{len(math_blocks)-1}\x00"
    text = re.sub(r'\$\$.*?\$\$', save_math, text, flags=re.DOTALL)
    text = re.sub(r'\$[^$\n]+?\$', save_math, text)

    # 删除特定宏（不保留内容）
    for macro in ['thanks', 'footnote', 'CJK', 'CJKfamily', 'fontencoding',
                  'selectfont', 'usefont', 'setCJKmainfont',
                  'affil', 'affiliation', 'orgdiv', 'orgname', 'orgaddress',
                  'street', 'city', 'postcode', 'state', 'country']:
        text = re.sub(rf'\\{macro}\*?(\[\d+\])?\{{[^}}]*\}}', '', text)
    # 删除 \maketitle, \affil[N]{...} 整块
    text = re.sub(r'\\maketitle\b', '', text)
    text = re.sub(r'\\affil\*?(?:\[\d+\])?\{[^}]*\}', '', text)

    # 删除环境 \begin{CJK}...\end{CJK}
    text = re.sub(r'\\begin\{CJK\*?\}.*?\\end\{CJK\*?\}', '', text, flags=re.DOTALL)

    # \textcolor{color}{content} -> content
    text = re.sub(r'\\textcolor\{[^}]*\}\{([^}]*)\}', r'\1', text)
    # \textbf{} \textit{} 等保留内容
    text = re.sub(r'\\text(?:bf|it|rm|sf|tt|sc|up|sl|md|lf)\{([^}]*)\}', r'\1', text)
    # 多参数宏 \MacroName{a}{b} -> b（保留最后参数）
    text = re.sub(r'\\[A-Za-z]+(?:\{[^}]*\}){2,}', lambda m: re.findall(r'\{([^}]*)\}', m.group())[-1], text)
    # 单参数宏 \MacroName{content} -> content
    text = re.sub(r'\\[A-Za-z]+\{([^}]*)\}', r'\1', text)
    # 孤立宏 \MacroName -> 保留宏名（如 \Euclid -> Euclid）
    text = re.sub(r'\\([A-Za-z]+)\b', r'\1', text)
    # 清理残留花括号
    text = re.sub(r'[{}]', '', text)
    # 清理 tex2md 转换后残留的 CJK 标记
    text = re.sub(r'\bCJK[A-Za-z]*\b', '', text)
    # ~ -> 空格（LaTeX 不换行空格）
    text = text.replace('~', ' ')
    # ORCID 号：16位数字串（如 0000-0001-7545-3504）
    text = re.sub(r'\b\d{4}-\d{4}-\d{4}-\d{4}\b', '', text)
    # 清理多余空格和逗号
    text = re.sub(r'  +', ' ', text).strip()

    # 还原数学块
    for i, block in enumerate(math_blocks):
        text = text.replace(f"\x00MATH{i}\x00", block)

    return text


def _build_markdown(doc, fig_data, arxiv_id, fallback_author=""):
    """自定义 Markdown 生成，图片使用已修正的 web 路径。"""
    from arxiv_on_deck_2.latex import tex2md, force_macros_mathmode

    try:
        title = _clean_latex(tex2md(doc.title.replace("~", " ")))
    except Exception:
        title = _clean_latex(doc.title or arxiv_id)

    try:
        authors = ", ".join(doc.short_authors)
        authors = _clean_latex(authors)
        authors = re.sub(r'[ \t]*\n[ \t]*,[ \t]*', ', ', authors)
        authors = re.sub(r',[ \t]*,', ',', authors).strip(', ')
    except Exception:
        authors = fallback_author or "(author list unavailable)"
        log.warning(f"    作者列表解析失败，使用降级值")

    try:
        abstract = _clean_latex(tex2md(doc.abstract))
    except Exception:
        abstract = _clean_latex(doc.abstract or "")

    # 如果摘要为空（Nature 格式等），从 arXiv API 获取
    if not abstract or len(abstract.strip()) < 20:
        import xml.etree.ElementTree as ET
        for wait in [3, 10, 30]:  # 重试，遇到429等待后重试
            try:
                url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
                resp = _make_session().get(url, timeout=15)
                if resp.status_code == 429:
                    log.warning(f"  arXiv API 限速，等待 {wait}s 后重试...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                tree = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entry = tree.find("atom:entry", ns)
                if entry is not None:
                    abstract = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
                    log.info(f"  从 arXiv API 获取摘要 ✓")
                break
            except Exception as e:
                log.warning(f"  arXiv API 获取摘要失败：{e}")
                break

    try:
        macros_md = doc.get_macros_markdown_text()
    except Exception:
        macros_md = ""

    text  = f"{macros_md}\n\n"
    text += f'''<div id="title" markdown="1">\n\n# {title}\n\n</div>\n'''
    if doc.comment:
        text += f'''<div id="comments" markdown="1">\n\n{doc.comment}\n\n</div>\n'''
    text += f'''<div id="authors" markdown="1">\n\n{authors}\n\n</div>\n'''
    text += f'''<div id="abstract" markdown="1">\n\n**Abstract:** {abstract}\n\n</div>\n'''

    fig_blocks = []
    for i, (paths, caption, label, num) in enumerate(fig_data, 1):
        valid_paths = [p for p in paths if p and p.strip()]
        if not valid_paths:
            continue
        if len(valid_paths) > 1:
            w = 100 // len(valid_paths)
            imgs = "".join(
                f'<img src="{p}" alt="Fig{num}.{j}" width="{w}%"/>' for j, p in enumerate(valid_paths, 1)
            )
        else:
            imgs = f'<img src="{valid_paths[0]}" alt="Fig{num}" width="100%"/>'
        try:
            cap_md = _clean_latex(tex2md(caption)) if caption else ""
        except Exception:
            cap_md = _clean_latex(caption) if caption else ""
        fig_blocks.append(
            f'<div id="div_fig{i}" markdown="1">\n\n{imgs}\n\n**Figure {num}. -** {cap_md} (*{label}*)\n\n</div>'
        )

    if fig_blocks:
        figs_text = "\n".join(fig_blocks)
        text += "\n" + force_macros_mathmode(figs_text, doc.macros)

    return text


def _download_source(arxiv_id: str, directory: str):
    """用 requests 下载 arXiv LaTeX 源码，绕过 urllib 的 SSL 问题。"""
    import tarfile, io, shutil, ssl
    from pathlib import Path

    url = f"https://arxiv.org/e-print/{arxiv_id}"
    print(f"Retrieving document from  {url}")

    # 用 requests + 降级 SSL
    session = _make_session()
    r = session.get(url, timeout=60, stream=True)
    r.raise_for_status()

    dst = Path(directory)
    if dst.exists():
        shutil.rmtree(dst)

    raw = io.BytesIO(r.content)
    try:
        tar = tarfile.open(mode='r|gz', fileobj=raw)
    except tarfile.ReadError:
        raw.seek(0)
        tar = tarfile.open(mode='r|*', fileobj=raw)

    print(f"extracting tarball to {directory}...", end='')
    tar.extractall(directory)
    print(" done.")


def generate_summary(arxiv_id, votes, output_dir, paper_author=""):
    """下载 arXiv LaTeX 源码，解析生成带图 Markdown，失败降级为纯文字。"""
    out_file = output_dir / f"{arxiv_id}.md"
    if out_file.exists():
        log.info(f"  {arxiv_id} 已存在，跳过")
        return out_file

    try:
        from arxiv_on_deck_2.arxiv2 import retrieve_document_source
        from arxiv_on_deck_2.latex import LatexDocument, select_most_cited_figures
    except ImportError:
        log.warning("未找到 arxiv_on_deck_2，改用 arXiv API 生成基础摘要")
        return fallback_summary(arxiv_id, votes, output_dir)

    src_dir = output_dir / f"_src_{arxiv_id}"
    fig_dir = output_dir / "figs" / arxiv_id
    fig_dir.mkdir(parents=True, exist_ok=True)

    try:
        log.info(f"  下载 LaTeX 源码：{arxiv_id}")
        _download_source(arxiv_id, str(src_dir))

        log.info(f"  解析 LaTeX：{arxiv_id}")
        doc = LatexDocument(str(src_dir))

        # 优先用论文作者标记的图（%@arxiver{}），否则取引用次数前 N_FIGURES 张
        selected = doc.select_arxivertag_figures()
        if not selected:
            selected = select_most_cited_figures(doc.figures, doc.content, N=N_FIGURES)
        log.info(f"  选出 {len(selected)}/{len(doc.figures)} 张图（上限 {N_FIGURES}）")

        fig_data = _copy_figures(selected, src_dir, fig_dir, arxiv_id)
        md = _build_markdown(doc, fig_data, arxiv_id, fallback_author=paper_author)

        header = (f"<!-- votes: {votes} -->\n\n"
                  f"[![arXiv](https://img.shields.io/badge/arXiv-{arxiv_id}-b31b1b.svg)]"
                  f"(https://arxiv.org/abs/{arxiv_id})\n\n")
        out_file.write_text(header + md, encoding="utf-8")
        return out_file

    except Exception as e:
        import traceback
        log.warning(f"  {arxiv_id} 生成失败：{e}")
        log.debug(traceback.format_exc())
        # 打印完整 traceback 到 stderr 方便调试
        traceback.print_exc()
        return fallback_summary(arxiv_id, votes, output_dir)
    finally:
        if src_dir.exists():
            shutil.rmtree(src_dir, ignore_errors=True)


def fallback_summary(arxiv_id, votes, output_dir):
    """
    备用方案：从 arXiv API 获取基础元数据，生成无图 Markdown。
    """
    out_file = output_dir / f"{arxiv_id}.md"
    try:
        import urllib.request, xml.etree.ElementTree as ET
        url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
        with urllib.request.urlopen(url, timeout=15) as resp:
            tree = ET.parse(resp)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = tree.find("atom:entry", ns)
        if entry is None:
            return None
        title   = entry.find("atom:title", ns).text.strip().replace("\n", " ")
        summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
        authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]

        md = (f"<!-- votes: {votes} -->\n\n"
              f"[![arXiv](https://img.shields.io/badge/arXiv-{arxiv_id}-b31b1b.svg)]"
              f"(https://arxiv.org/abs/{arxiv_id})\n\n"
              f"# {title}\n\n"
              f"{', '.join(authors)}\n\n"
              f"**Abstract:** {summary}\n\n"
              f"> ⚠️ LaTeX 源码解析失败，无图版本\n")
        out_file.write_text(md, encoding="utf-8")
        log.info(f"  {arxiv_id} 降级为无图版本")
        return out_file
    except Exception as e:
        log.warning(f"  {arxiv_id} 降级也失败：{e}")
        return None


def generate_summaries(papers, output_dir):
    generated = []
    for p in papers:
        f = generate_summary(p["arxiv_id"], p["votes"], output_dir, paper_author=p.get("author", ""))
        if f:
            generated.append(f)
        time.sleep(2)   # 避免请求过快
    return generated


# ── 生成索引页 ───────────────────────────────────────────────────────────
def write_index(papers, output_dir):
    today = datetime.date.today().strftime("%Y-%m-%d")
    lines = [
        f"# USTC Astro Coffee — {today}\n\n",
        f"Benty-Fields Journal Club 当前 agenda，投票前 {len(papers)} 篇\n\n",
        "| 票数 | arXiv | 标题 |\n",
        "|:----:|-------|------|\n",
    ]
    for p in papers:
        aid   = p["arxiv_id"]
        votes = p["votes"]
        title = p["title"][:80]
        lines.append(f"| **{votes}** | [{aid}]({aid}.md) | {title} |\n")
    (output_dir / "jc_latest.md").write_text("".join(lines), encoding="utf-8")
    log.info(f"索引写入完成")


def save_json(papers, output_dir):
    out = output_dir / "jc_papers.json"
    out.write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"JSON 写入：{out}")

    # 历史存档：只在 agenda 内容发生变化时才存新档
    hist_dir = output_dir / "history"
    hist_dir.mkdir(exist_ok=True)

    # 提取当前 arxiv_id 集合作为对比指纹
    current_ids = sorted(p["arxiv_id"] for p in papers)

    # 找最新一份历史，比较内容
    all_hist = sorted(hist_dir.glob("20*.json"), reverse=True)
    # 跳过 mark_discussed 生成的日内存档（那些只有部分论文）
    last_snapshot = None
    for f in all_hist:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            # 只认 fetch 生成的完整快照（有 vote_id 字段）
            if data and "vote_id" in data[0]:
                last_snapshot = data
                break
        except Exception:
            continue

    last_ids = sorted(p["arxiv_id"] for p in last_snapshot) if last_snapshot else []

    if current_ids == last_ids:
        log.info("Agenda 未变化，跳过历史存档")
        return

    today = datetime.date.today().isoformat()
    hist_file = hist_dir / f"{today}.json"
    hist_file.write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"历史存档：{hist_file}（新 agenda）")

    # 只保留最新 20 份
    all_hist = sorted(hist_dir.glob("20*.json"), reverse=True)
    for old_f in all_hist[20:]:
        old_f.unlink()
        log.info(f"删除旧存档：{old_f.name}")


# ── 主函数 ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fetch Benty-Fields JC current agenda")
    parser.add_argument("--debug-html", help="直接解析本地 HTML（跳过登录）")
    parser.add_argument("--no-summaries", action="store_true", help="只抓列表，不生成摘要")
    parser.add_argument("--output-dir", default="./docs", help="输出目录（默认 ./docs）")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.debug_html:
        log.info(f"调试模式：读取 {args.debug_html}")
        html = Path(args.debug_html).read_text(encoding="utf-8")
    else:
        password = os.environ.get("BENTY_PASSWORD") or getpass.getpass(f"密码（{BENTY_EMAIL}）：")
        session  = login(BENTY_EMAIL, password)
        html     = fetch_agenda_html(session)
        (output_dir / "debug_agenda.html").write_text(html, encoding="utf-8")

    papers = parse_papers(html)
    if not papers:
        log.error("未解析到论文，退出")
        sys.exit(1)

    save_json(papers, output_dir)
    write_index(papers, output_dir)

    if not args.no_summaries:
        generate_summaries(papers, output_dir)

    log.info(f"完成 ✓  共 {len(papers)} 篇，输出至 {output_dir.resolve()}")


if __name__ == "__main__":
    main()
