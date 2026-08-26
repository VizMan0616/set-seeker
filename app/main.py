from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import get_engine
from app.engine.service import CpSatSearchService
from app.pack_loader import PackLoader
from app.repository.game_data import GameDataRepository
from app.repository.user_data import UserDataRepository
from app.sessions import SessionMiddleware
from app.web.resolvers import RepositoryCatalog, RepositoryNameResolver
from app.web.routes import pages, search


def create_app() -> FastAPI:
    app = FastAPI(title="set-seeker")
    app.add_middleware(SessionMiddleware)
    app.include_router(pages.router)
    app.include_router(search.router)
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "web" / "static"),
        name="static",
    )

    settings = get_settings()
    engine = get_engine()
    game_data = GameDataRepository(engine)
    user_data = UserDataRepository(engine)

    try:
        games = game_data.list_games()
    except Exception as exc:
        raise RuntimeError(
            f"cannot read game data from {settings.DATABASE_URL!r} — "
            "run `python -m app.etl --pack mhfu` to build the database first"
        ) from exc
    if not games:
        raise RuntimeError(
            f"no game packs loaded in {settings.DATABASE_URL!r} — "
            "run `python -m app.etl --pack mhfu` first"
        )

    # Pack data is loaded once at startup and cached for the process lifetime.
    pack_loader = PackLoader(game_data)
    for game in games:
        pack_loader(game["code"])

    app.state.search_service = CpSatSearchService(
        user_data,
        pack_loader,
        time_limit_ms=settings.SOLVER_TIME_LIMIT_MS,
        num_workers=settings.SOLVER_NUM_WORKERS,
    )
    app.state.catalog = RepositoryCatalog(game_data)
    app.state.name_resolver = RepositoryNameResolver(game_data)
    return app
