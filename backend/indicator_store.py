"""Persist each named indicator's settings in the workstation SQLite file."""

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from backend.indicators import INDICATOR_TYPES, IndicatorPoint, Window


class DuplicateIndicator(ValueError):
    pass


class IndicatorSettings(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    type: str
    window: Window

    @field_validator("type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in INDICATOR_TYPES:
            raise ValueError("Unknown indicator type")
        return value


class SavedIndicator(IndicatorSettings):
    id: int


class EvaluatedIndicator(SavedIndicator):
    values: list[IndicatorPoint]


class IndicatorStore:
    def __init__(self, path: Path):
        self.path = path
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS chart_indicators (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    name_key TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL,
                    window INTEGER NOT NULL CHECK (window > 0)
                )
            """)

    def add(self, settings: IndicatorSettings) -> SavedIndicator:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            cursor = connection.execute("""
                INSERT INTO chart_indicators (name, name_key, type, window)
                VALUES (?, ?, ?, ?) ON CONFLICT(name_key) DO NOTHING
            """, (settings.name, settings.name.casefold(), settings.type, settings.window))
            if not cursor.rowcount:
                raise DuplicateIndicator("An indicator already uses that name")
            return SavedIndicator(id=cursor.lastrowid, **settings.model_dump())

    def all(self) -> list[SavedIndicator]:
        with closing(sqlite3.connect(self.path)) as connection:
            return [
                SavedIndicator(id=id_, name=name, type=kind, window=window)
                for id_, name, kind, window in connection.execute(
                    "SELECT id, name, type, window FROM chart_indicators ORDER BY id"
                )
            ]

    def change_window(self, indicator_id: int, window: int) -> SavedIndicator | None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute(
                "UPDATE chart_indicators SET window=? WHERE id=? RETURNING name,type,window",
                (window, indicator_id),
            ).fetchone()
            return SavedIndicator(id=indicator_id, name=row[0], type=row[1], window=row[2]) if row else None


class IndicatorWindowUpdate(BaseModel):
    window: Window
