"""Username/password auth -- see db/models.py's User/SessionToken.

Mirrors LongTermMemory's shape (memory/long_term.py): own engine/session,
`init_schema()` delegating to the same `Base.metadata.create_all`, one
method per operation, each opening its own `with self._Session()` block.

Sessions are opaque bearer tokens (`secrets.token_urlsafe`), not JWTs --
there is no JWT library anywhere in this project's dependencies, and an
opaque token looked up against a `session_tokens` row is the simplest thing
that actually works with this app's existing sync/SQLAlchemy style. A
lookup-per-request is a single indexed primary-key read, not a real cost
at this project's scale.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from aio.config import settings
from aio.db.models import Base, SessionToken, User

SESSION_TTL = timedelta(days=30)


class UsernameTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class AuthService:
    def __init__(self, database_url: str | None = None) -> None:
        self._engine = create_engine(database_url or settings.database_url, future=True)
        self._Session: sessionmaker[Session] = sessionmaker(bind=self._engine, future=True)

    def init_schema(self) -> None:
        Base.metadata.create_all(self._engine)

    def signup(self, username: str, password: str) -> str:
        """Creates the user and an initial session in one call, returns the
        session token. Raises UsernameTaken if the username is already in
        use -- checked before hashing, so a duplicate signup doesn't pay
        bcrypt's deliberately-slow cost for nothing."""
        with self._Session() as session:
            existing = session.scalar(select(User).where(User.username == username))
            if existing is not None:
                raise UsernameTaken(username)

            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            user = User(username=username, password_hash=password_hash)
            session.add(user)
            session.commit()
            session.refresh(user)
            return self._issue_session(session, user.id)

    def login(self, username: str, password: str) -> str:
        with self._Session() as session:
            user = session.scalar(select(User).where(User.username == username))
            if user is None or not bcrypt.checkpw(
                password.encode(), user.password_hash.encode()
            ):
                # Same error for "no such user" and "wrong password" --
                # distinguishing them lets an attacker enumerate valid
                # usernames.
                raise InvalidCredentials(username)
            return self._issue_session(session, user.id)

    def _issue_session(self, session: Session, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        session.add(SessionToken(token=token, user_id=user_id, expires_at=now + SESSION_TTL))
        session.commit()
        return token

    def get_user_for_token(self, token: str) -> User | None:
        with self._Session() as session:
            record = session.get(SessionToken, token)
            if record is None:
                return None
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                # SQLite round-trips DateTime(timezone=True) values as
                # naive -- Postgres does not. Compare in UTC either way.
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                return None
            return session.get(User, record.user_id)
