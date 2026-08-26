from fastapi import FastAPI

from app.sessions import SessionMiddleware
from app.web.routes import pages, search


def create_app() -> FastAPI:
    app = FastAPI(title="set-seeker")
    app.add_middleware(SessionMiddleware)
    app.include_router(pages.router)
    app.include_router(search.router)

    # --- MOCK WIRING: replace with real SearchService at integration ---
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    from app.web.mock import FixtureResolver, MockCatalog, MockSearchService

    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "web" / "static"),
        name="static",
    )
    app.state.search_service = MockSearchService()
    app.state.catalog = MockCatalog()
    app.state.name_resolver = FixtureResolver()
    # --- END MOCK WIRING ---

    return app


app = create_app()
