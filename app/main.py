from fastapi import FastAPI

from app.sessions import SessionMiddleware
from app.web.routes import pages, search


def create_app() -> FastAPI:
    app = FastAPI(title="set-seeker")
    app.add_middleware(SessionMiddleware)
    app.include_router(pages.router)
    app.include_router(search.router)
    return app


app = create_app()
