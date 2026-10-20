import logging
import secrets
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from . import __version__
from .engines import Engines
from .errors import StudioError
from .jobs import JobManager
from .repository import Repository
from .routes_assets import router as assets_router
from .routes_jobs import router as jobs_router
from .routes_library import router as library_router
from .search import SearchService
from .security import LocalSecurity
from .settings import Settings, resource_dir
from .storage import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    repository = Repository(Database(settings.data_dir))
    engines = Engines(settings)
    manager = JobManager(repository, settings, engines)
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        manager.start()
        yield
        manager.close()

    app = FastAPI(title="拾序 · Original Studio", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.repository = repository
    app.state.engines = engines
    app.state.jobs = manager
    app.state.search = SearchService(repository, settings, engines)
    app.state.clip_lock = threading.Lock()
    app.add_middleware(LocalSecurity, token=token)

    @app.exception_handler(StudioError)
    async def known_error(request, exc):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        first = exc.errors()[0]
        field = ".".join(str(item) for item in first.get("loc", [])[1:])
        return JSONResponse({"error": {"code": "validation_error", "message": f"参数无效{('：' + field) if field else ''}；{first['msg']}"}}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"error": {"code": "http_error", "message": "请求的内容不存在" if exc.status_code == 404 else str(exc.detail)}}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logging.getLogger(__name__).exception("Unhandled request failure")
        return JSONResponse({"error": {"code": "internal_error", "message": "处理失败，请查看程序日志后重试"}}, status_code=500)

    @app.get("/api/session")
    def session():
        return {"token": token, "version": __version__, "name": "拾序 · Original Studio"}

    @app.get("/api/status")
    def status():
        return {"version": __version__, "roots": repository.roots(), "stats": repository.stats(), "active_jobs": manager.list(100, active_only=True)["items"], "capabilities": engines.capabilities(), "data_dir": str(settings.data_dir)}

    app.include_router(library_router)
    app.include_router(assets_router)
    app.include_router(jobs_router)
    static = resource_dir() / "static"
    if static.is_dir():
        app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html", media_type="text/html")

    @app.get("/favicon.ico")
    def favicon():
        return FileResponse(static / "favicon.svg", media_type="image/svg+xml")

    return app
