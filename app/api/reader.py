from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pathlib import Path
from io import BytesIO
from html import escape
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
import asyncio
import httpx
import json

import shutil

from app.api.bookshelf import load_db, mark_cached, unmark_cached, save_db

router = APIRouter()

BASE_URL = "https://novel.cooks.tw"
CACHE_ROOT = Path("data/cache")


def book_cache_dir(aid: str):
    return CACHE_ROOT / str(aid)


def chapters_cache_path(aid: str):
    return book_cache_dir(aid) / "chapters.json"


def content_cache_path(aid: str, cid: str):
    return book_cache_dir(aid) / f"{cid}.json"


def read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_filename(name: str, default: str = "book"):
    value = (name or default).strip() or default
    for char in '<>:"/\\|?*':
        value = value.replace(char, "_")
    value = value.rstrip(". ")
    return value[:80] or default


def get_book_from_shelf(aid: str):
    for book in load_db()["bookshelf"]:
        if str(book.get("aid")) == str(aid):
            return book
    return None


def get_source_config(source_id: str) -> dict | None:
    if not source_id:
        return None
    db = load_db()
    for s in db.get("sources", []):
        if s.get("id") == source_id:
            return s
    return None


def _build_url(source: dict | None, path_template: str, **kwargs) -> str:
    if source:
        base = (source.get("base_url") or "").rstrip("/")
        return base + path_template.format(**kwargs)
    return BASE_URL + path_template.format(**kwargs)


def normalize_chapter_content(payload):
    data = (payload or {}).get("data")
    if isinstance(data, dict):
        return str(data.get("content") or "")
    return ""


def build_txt(book_name: str, author: str, chapters: list[dict]):
    lines = [book_name]
    if author:
        lines.append(f"作者：{author}")
    lines.append("")

    for index, chapter in enumerate(chapters, start=1):
        title = chapter.get("chaptername") or f"第 {index} 章"
        content = (chapter.get("content") or "").strip()
        lines.extend([
            "",
            title,
            "=" * min(max(len(title), 8), 32),
            content or "本章内容下载失败。",
        ])

    return "\n".join(lines).replace("\r\n", "\n").replace("\r", "\n")


def chapter_paragraphs(content: str):
    paragraphs = [
        line.strip()
        for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]
    if not paragraphs:
        paragraphs = ["本章内容下载失败。"]
    return "\n".join(f"<p>{escape(line)}</p>" for line in paragraphs)


def download_cover(cover_url: str) -> bytes:
    if not cover_url:
        return b""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(cover_url)
            resp.raise_for_status()
            return resp.content
    except Exception:
        return b""


def build_epub(book_name: str, author: str, aid: str, chapters: list[dict], cover_url: str = ""):
    book_id = f"cloud-reader-{aid}"
    chapter_files = [
        (f"chapters/chapter_{index:04d}.xhtml", chapter)
        for index, chapter in enumerate(chapters, start=1)
    ]

    cover_data = download_cover(cover_url)
    has_cover = len(cover_data) > 0

    manifest_items = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="style" href="styles/book.css" media-type="text/css"/>',
    ]

    if has_cover:
        manifest_items.append('<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>')

    spine_items = []
    nav_items = []
    ncx_items = []

    for index, (file_path, chapter) in enumerate(chapter_files, start=1):
        item_id = f"chapter_{index:04d}"
        title = escape(chapter.get("chaptername") or f"第 {index} 章")
        manifest_items.append(
            f'<item id="{item_id}" href="{file_path}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="{item_id}"/>')
        nav_items.append(f'<li><a href="{file_path}">{title}</a></li>')
        ncx_items.append(
            f"""
            <navPoint id="navPoint-{index}" playOrder="{index}">
                <navLabel><text>{title}</text></navLabel>
                <content src="{file_path}"/>
            </navPoint>
            """.strip()
        )

    cover_meta = '<meta name="cover" content="cover-image"/>' if has_cover else ''

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{escape(book_id)}</dc:identifier>
    <dc:title>{escape(book_name)}</dc:title>
    <dc:creator>{escape(author or "未知作者")}</dc:creator>
    <dc:language>zh-CN</dc:language>
    {cover_meta}
  </metadata>
  <manifest>
    {chr(10).join(manifest_items)}
  </manifest>
  <spine toc="ncx">
    {chr(10).join(spine_items)}
  </spine>
</package>
"""

    nav = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">
  <head>
    <title>{escape(book_name)} - 目录</title>
    <link rel="stylesheet" type="text/css" href="styles/book.css"/>
  </head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>目录</h1>
      <ol>
        {chr(10).join(nav_items)}
      </ol>
    </nav>
  </body>
</html>
"""

    ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{escape(book_id)}"/>
  </head>
  <docTitle><text>{escape(book_name)}</text></docTitle>
  <navMap>
    {chr(10).join(ncx_items)}
  </navMap>
</ncx>
"""

    css = """
body { font-family: serif; line-height: 1.85; color: #222; }
h1 { text-align: center; font-size: 1.5em; margin: 1.5em 0; }
p { text-indent: 2em; margin: 0 0 1em; }
"""

    buffer = BytesIO()
    with ZipFile(buffer, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        epub.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
            compress_type=ZIP_DEFLATED,
        )
        epub.writestr("EPUB/content.opf", opf, compress_type=ZIP_DEFLATED)
        epub.writestr("EPUB/nav.xhtml", nav, compress_type=ZIP_DEFLATED)
        epub.writestr("EPUB/toc.ncx", ncx, compress_type=ZIP_DEFLATED)
        epub.writestr("EPUB/styles/book.css", css, compress_type=ZIP_DEFLATED)

        if has_cover:
            epub.writestr("EPUB/images/cover.jpg", cover_data, compress_type=ZIP_DEFLATED)

        for index, (file_path, chapter) in enumerate(chapter_files, start=1):
            title = escape(chapter.get("chaptername") or f"第 {index} 章")
            body = chapter_paragraphs(chapter.get("content") or "")
            chapter_html = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN" xml:lang="zh-CN">
  <head>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="../styles/book.css"/>
  </head>
  <body>
    <h1>{title}</h1>
    {body}
  </body>
</html>
"""
            epub.writestr(f"EPUB/{file_path}", chapter_html, compress_type=ZIP_DEFLATED)

    return buffer.getvalue()


def download_headers(filename: str):
    encoded = quote(filename)
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}


def _resolve_source(aid: str, source_id: str) -> tuple[dict | None, str]:
    source = get_source_config(source_id)
    if not source:
        book = get_book_from_shelf(aid)
        if book and book.get("source_id"):
            source = get_source_config(book["source_id"])
    tpl = "/api/chapter/list/{aid}?lang=zh-CN"
    if source:
        tpl = source.get("chapter_list_path") or tpl
    return source, tpl


def _resolve_content_source(aid: str, source_id: str) -> tuple[dict | None, str]:
    source = get_source_config(source_id)
    if not source:
        book = get_book_from_shelf(aid)
        if book and book.get("source_id"):
            source = get_source_config(book["source_id"])
    tpl = "/api/chapter/content/{aid}/{cid}?lang=zh-CN"
    if source:
        tpl = source.get("chapter_content_path") or tpl
    return source, tpl


async def fetch_chapters(aid: str, source_id: str = ""):
    source, tpl = _resolve_source(aid, source_id)
    url = _build_url(source, tpl, aid=aid)
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def fetch_content(aid: str, cid: str, source_id: str = ""):
    source, tpl = _resolve_content_source(aid, source_id)
    url = _build_url(source, tpl, aid=aid, cid=cid)
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def fetch_content_with_client(client: httpx.AsyncClient, aid: str, cid: str, source_id: str = ""):
    source, tpl = _resolve_content_source(aid, source_id)
    url = _build_url(source, tpl, aid=aid, cid=cid)
    resp = await client.get(url, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


async def load_chapters_for_download(aid: str, source_id: str = ""):
    try:
        data = await fetch_chapters(aid, source_id)
        write_json(chapters_cache_path(aid), data)
        return data
    except Exception:
        cached = read_json(chapters_cache_path(aid))
        if cached:
            return cached
        raise HTTPException(status_code=503, detail="目录加载失败，且没有本地缓存")


async def collect_book_chapters(aid: str, chapter_items: list[dict], source_id: str = ""):
    results = [None] * len(chapter_items)
    semaphore = asyncio.Semaphore(8)

    async with httpx.AsyncClient() as client:
        async def load_one(index: int, chapter: dict):
            cid = str(chapter.get("chapterid") or "")
            title = chapter.get("chaptername") or f"第 {index + 1} 章"
            content = ""

            if cid:
                cached = read_json(content_cache_path(aid, cid))
                if cached:
                    content = normalize_chapter_content(cached)
                else:
                    async with semaphore:
                        try:
                            payload = await fetch_content_with_client(client, aid, cid, source_id)
                            write_json(content_cache_path(aid, cid), payload)
                            content = normalize_chapter_content(payload)
                        except Exception:
                            content = ""

            results[index] = {
                "chapterid": cid,
                "chaptername": title,
                "content": content,
            }

        await asyncio.gather(*[
            load_one(index, chapter)
            for index, chapter in enumerate(chapter_items)
        ])

    loaded = [item for item in results if item]
    if not any((item.get("content") or "").strip() for item in loaded):
        raise HTTPException(status_code=503, detail="正文下载失败，且没有可用缓存")
    return loaded


@router.get("/chapters/{aid}")
async def get_chapters(aid: str, source: str = Query("", description="书源ID")):
    """获取书籍目录"""
    try:
        data = await fetch_chapters(aid, source)
        write_json(chapters_cache_path(aid), data)
        return data
    except Exception:
        cached = read_json(chapters_cache_path(aid))
        if cached:
            cached["cached"] = True
            return cached
        raise HTTPException(status_code=503, detail="目录加载失败，且没有本地缓存")


@router.get("/content/{aid}/{cid}")
async def get_content(aid: str, cid: str, source: str = Query("", description="书源ID")):
    """获取章节正文"""
    cached = read_json(content_cache_path(aid, cid))
    if cached:
        cached["cached"] = True
        return cached

    try:
        data = await fetch_content(aid, cid, source)
        write_json(content_cache_path(aid, cid), data)
        return data
    except Exception:
        raise HTTPException(status_code=503, detail="正文加载失败，且没有本地缓存")


@router.get("/cache/status/{aid}")
async def cache_status(aid: str):
    """查看本地缓存状态"""
    chapters = read_json(chapters_cache_path(aid))
    chapter_items = (chapters or {}).get("data") or []
    cached_count = len(list(book_cache_dir(aid).glob("*.json"))) - (1 if chapters else 0)
    cached_count = max(cached_count, 0)
    return {
        "cached": bool(chapter_items and cached_count >= len(chapter_items)),
        "cached_count": cached_count,
        "total": len(chapter_items),
    }


def _clear_book_cache(aid: str):
    d = book_cache_dir(aid)
    if d.exists():
        shutil.rmtree(d)
    unmark_cached(aid)


@router.delete("/cache")
async def clear_all_cache():
    """清除所有书籍的本地缓存"""
    if CACHE_ROOT.exists():
        shutil.rmtree(CACHE_ROOT)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    db = load_db()
    for book in db.get("bookshelf", []):
        book["cached"] = False
        book["cached_at"] = ""
    save_db(db)
    return {"msg": "已清除全部缓存"}


@router.delete("/cache/{aid}")
async def clear_book_cache(aid: str):
    """清除指定书籍的本地缓存"""
    _clear_book_cache(aid)
    return {"msg": "已清除缓存"}


@router.post("/cache/{aid}")
async def cache_book(aid: str, source: str = Query("", description="书源ID")):
    """缓存整本书到本地 data/cache 目录（SSE 流式返回进度）"""
    chapters = await fetch_chapters(aid, source)
    chapter_items = chapters.get("data") or []
    write_json(chapters_cache_path(aid), chapters)

    total = len(chapter_items)

    async def progress_stream():
        cached_count = 0
        failed = []
        for chapter in chapter_items:
            cid = str(chapter.get("chapterid", ""))
            if not cid:
                continue

            target = content_cache_path(aid, cid)
            if target.exists():
                cached_count += 1
            else:
                try:
                    content = await fetch_content(aid, cid, source)
                    write_json(target, content)
                    cached_count += 1
                except Exception:
                    failed.append({
                        "chapterid": cid,
                        "chaptername": chapter.get("chaptername", ""),
                    })

            yield f"data: {json.dumps({'current': cached_count, 'total': total, 'failed': len(failed)}, ensure_ascii=False)}\n\n"

        if cached_count:
            mark_cached(aid)

        yield f"data: {json.dumps({'done': True, 'msg': '缓存完成' if not failed else '部分章节缓存失败', 'cached_count': cached_count, 'total': total, 'failed': failed[:20]}, ensure_ascii=False)}\n\n"

    return StreamingResponse(progress_stream(), media_type="text/event-stream")


@router.get("/download/{file_format}/{aid}")
async def download_book(
    file_format: str,
    aid: str,
    name: str = Query("", description="书名"),
    author: str = Query("", description="作者"),
    source: str = Query("", description="书源ID"),
):
    """下载整本书，支持 txt 和 epub"""
    normalized_format = file_format.lower().strip()
    if normalized_format == "ebup":
        normalized_format = "epub"
    if normalized_format not in {"txt", "epub"}:
        raise HTTPException(status_code=400, detail="暂只支持 txt 和 epub 格式")

    shelf_book = get_book_from_shelf(aid)
    book_name = name.strip() or (shelf_book or {}).get("name") or f"book-{aid}"
    book_author = author.strip() or (shelf_book or {}).get("author") or ""
    cover_url = (shelf_book or {}).get("cover", "")

    chapters_payload = await load_chapters_for_download(aid, source)
    chapter_items = chapters_payload.get("data") or []
    if not chapter_items:
        raise HTTPException(status_code=404, detail="没有可下载的章节")

    chapters = await collect_book_chapters(aid, chapter_items, source)
    filename = f"{safe_filename(book_name)}.{normalized_format}"

    if normalized_format == "txt":
        content = build_txt(book_name, book_author, chapters).encode("utf-8-sig")
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers=download_headers(filename),
        )

    return Response(
        content=build_epub(book_name, book_author, aid, chapters, cover_url),
        media_type="application/epub+zip",
        headers=download_headers(filename),
    )
