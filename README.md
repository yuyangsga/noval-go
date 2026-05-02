# 云读小说 (noval-go)

基于 FastAPI 的高性能异步小说阅读器后端。

## 功能特性

- **搜索功能** - 支持多书源搜索小说
- **书架管理** - 收藏、管理书籍
- **阅读功能** - 获取章节内容，支持在线阅读
- **书源管理** - 灵活配置多个小说数据源

## 技术栈

- Python 3.10+
- FastAPI - Web 框架
- Uvicorn - ASGI 服务器
- Pydantic - 数据验证
- Httpx - 异步 HTTP 客户端

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirement.txt
```

或使用 uv：

```bash
uv sync
```

### 2. 启动服务

```bash
python -m app.main
```

服务将在 http://127.0.0.1:8000 启动。

### 3. 访问应用

将前端文件放入 `web` 目录，访问 http://127.0.0.1:8000 即可使用。

## API 接口

| 路径 | 说明 |
|------|------|
| `GET /api/search` | 搜索小说 |
| `GET /api/bookshelf` | 书架管理 |
| `GET /api/reader` | 章节阅读 |
| `GET /api/sources` | 书源管理 |
| `GET /api/health` | 健康检查 |

## 项目结构

```
noval-go/
├── app/
│   ├── api/
│   │   ├── bookshelf.py   # 书架相关接口
│   │   ├── reader.py      # 阅读相关接口
│   │   ├── search.py      # 搜索相关接口
│   │   └── sources.py     # 书源管理接口
│   └── main.py            # 应用入口
├── web/                   # 前端文件目录
├── data/                  # 数据存储目录
├── pyproject.toml         # 项目配置
└── requirement.txt        # Python 依赖
```
