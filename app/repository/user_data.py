"""User-data repository: sessions, charm inventories, search pagination state.

Runtime-owned data — never touched by ETL. Portable SQL only (select-then-insert
instead of dialect upserts) so the MariaDB swap stays a config change.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Engine

from app.repository import tables as t


def _utcnow() -> datetime:
    # Naive UTC: portable across SQLite and MariaDB DATETIME columns.
    return datetime.now(UTC).replace(tzinfo=None)


class UserDataRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # --- sessions ---

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(t.sessions).where(t.sessions.c.id == session_id)
            ).one_or_none()
            return dict(row._mapping) if row is not None else None

    def get_or_create_session(self, session_id: str) -> dict[str, Any]:
        existing = self.get_session(session_id)
        if existing is not None:
            self.touch_session(session_id)
            return existing
        now = _utcnow()
        with self._engine.begin() as conn:
            conn.execute(
                insert(t.sessions).values(id=session_id, created_at=now, last_seen_at=now)
            )
        return {"id": session_id, "created_at": now, "last_seen_at": now}

    def touch_session(self, session_id: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                update(t.sessions)
                .where(t.sessions.c.id == session_id)
                .values(last_seen_at=_utcnow())
            )
            return result.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(delete(t.sessions).where(t.sessions.c.id == session_id))
            return result.rowcount > 0

    # --- search_states (iterate+exclude pagination) ---

    def create_search_state(self, *, session_id: str, game_id: int, query_json: str,
                            search_id: str | None = None) -> dict[str, Any]:
        search_id = search_id or uuid.uuid4().hex
        now = _utcnow()
        with self._engine.begin() as conn:
            conn.execute(
                insert(t.search_states).values(
                    id=search_id, session_id=session_id, game_id=game_id,
                    query_json=query_json, exclusions="[]", created_at=now,
                )
            )
        return {"id": search_id, "session_id": session_id, "game_id": game_id,
                "query_json": query_json, "exclusions": "[]", "created_at": now}

    def get_search_state(self, search_id: str) -> dict[str, Any] | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(t.search_states).where(t.search_states.c.id == search_id)
            ).one_or_none()
            return dict(row._mapping) if row is not None else None

    def append_exclusions(self, search_id: str,
                          new_exclusions: list[Any]) -> dict[str, Any] | None:
        """Read-modify-write the JSON exclusion list inside one transaction."""
        with self._engine.begin() as conn:
            row = conn.execute(
                select(t.search_states).where(t.search_states.c.id == search_id)
            ).one_or_none()
            if row is None:
                return None
            state = dict(row._mapping)
            exclusions = json.loads(state["exclusions"])
            exclusions.extend(new_exclusions)
            state["exclusions"] = json.dumps(exclusions)
            conn.execute(
                update(t.search_states)
                .where(t.search_states.c.id == search_id)
                .values(exclusions=state["exclusions"])
            )
            return state

    def delete_search_state(self, search_id: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                delete(t.search_states).where(t.search_states.c.id == search_id)
            )
            return result.rowcount > 0

    def delete_search_states_for_session(self, session_id: str) -> int:
        """A new start_search invalidates the session's prior states (phase0 §4)."""
        with self._engine.begin() as conn:
            result = conn.execute(
                delete(t.search_states).where(t.search_states.c.session_id == session_id)
            )
            return result.rowcount

    # --- user_charms ---

    def add_charm(self, *, session_id: str, game_id: int, slots: int,
                  skill1_tree: int | None = None, skill1_points: int | None = None,
                  skill2_tree: int | None = None, skill2_points: int | None = None,
                  note: str | None = None) -> dict[str, Any]:
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(t.user_charms).values(
                    session_id=session_id, game_id=game_id, slots=slots,
                    skill1_tree=skill1_tree, skill1_points=skill1_points,
                    skill2_tree=skill2_tree, skill2_points=skill2_points, note=note,
                )
            )
            charm_id = result.inserted_primary_key[0]
            row = conn.execute(
                select(t.user_charms).where(t.user_charms.c.id == charm_id)
            ).one()
            return dict(row._mapping)

    def get_charm(self, charm_id: int) -> dict[str, Any] | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(t.user_charms).where(t.user_charms.c.id == charm_id)
            ).one_or_none()
            return dict(row._mapping) if row is not None else None

    def list_charms(self, session_id: str,
                    game_id: int | None = None) -> list[dict[str, Any]]:
        c = t.user_charms.c
        criteria = [c.session_id == session_id]
        if game_id is not None:
            criteria.append(c.game_id == game_id)
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(t.user_charms).where(*criteria).order_by(c.id)
            ).all()
            return [dict(row._mapping) for row in rows]

    def update_charm(self, charm_id: int, **values) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                update(t.user_charms)
                .where(t.user_charms.c.id == charm_id)
                .values(**values)
            )
            return result.rowcount > 0

    def delete_charm(self, charm_id: int) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                delete(t.user_charms).where(t.user_charms.c.id == charm_id)
            )
            return result.rowcount > 0
