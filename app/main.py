from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import asyncio

from app.api import search, bookshelf, reader, sources

DEFAULT_SOURCE_ID = "cooks_tw"
DEFAULT_SOURCE = {
    "id": DEFAULT_SOURCE_ID,
    "name": "Cooks小说",
    "base_url": "https://novel.cooks.tw",
    "search_path": "/api/novel/search?q={query}&page={page}&limit=20&lang=zh-CN",
    "chapter_list_path": "/api/chapter/list/{aid}?lang=zh-CN",
    "chapter_content_path": "/api/chapter/content/{aid}/{cid}?lang=zh-CN",
    "enabled": True,
    "color": "#0d9488",
    "field_map": {
        "name": "articlename",
        "author": "author",
        "aid": "articleid",
        "cover": "cover",
        "intro": "intro",
    },
}

def ensure_default_source():
    db = bookshelf.load_db()
    sources_list = db.get("sources", [])
    if not any(s.get("id") == DEFAULT_SOURCE_ID for s in sources_list):
        sources_list.append(DEFAULT_SOURCE)
        db["sources"] = sources_list
        bookshelf.save_db(db)

app = FastAPI(
    title="云读小说 API",
    description="基于 FastAPI 的高性能异步小说阅读器后端",
    version="1.0.0"
)

# --- 1. 配置跨域 (CORS) ---
# 允许前端页面（如 Live Server 或本地文件）访问 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. 挂载静态资源 ---
# 假设你的前端文件放在项目根目录下的 /web 文件夹中
# 如果该文件夹不存在，我们先创建一个空的，防止报错
if not os.path.exists("web"):
    os.makedirs("web")

# 挂载后，你可以通过 /static/xxx 访问 web 目录下的文件
app.mount("/static", StaticFiles(directory="web"), name="static")

app.include_router(search.router, prefix="/api/search", tags=["搜索"])
app.include_router(bookshelf.router, prefix="/api/bookshelf", tags=["书架"])
app.include_router(reader.router, prefix="/api/reader", tags=["阅读"])
app.include_router(sources.router, prefix="/api/sources", tags=["书源"])

# --- 4. 基础路由 ---

@app.on_event("startup")
async def start_bookshelf_update_watcher():
    """初始化并启动后台任务"""
    ensure_default_source()
    asyncio.create_task(bookshelf.update_watcher())

@app.get("/")
async def index():
    """主页入口：自动返回前端页面"""
    index_path = os.path.join("web", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "云读小说后端已启动，请将前端 index.html 放入 web 文件夹中。"}

@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "service": "cloud-reader-api"}

# --- 5. 启动配置 ---
if __name__ == "__main__":
    import uvicorn
    import sys
    import os
    
    # 将当前目录的上一级添加到路径，这样就能找到 app 包了
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
