"""
Session Management Service

Provides secure session token management and CSRF protection.
"""

import secrets
import time
import threading
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Session:
    """Represents an authenticated session"""
    token: str
    csrf_token: str
    created_at: float
    last_access: float


class SessionManager:
    """
    Manages secure session tokens and CSRF protection.

    Security features:
    - Cryptographic session tokens (not passwords in cookies)
    - CSRF tokens per session
    - Session expiration
    - Timing-safe comparisons
    """

    SESSION_LIFETIME = 86400  # 24 hours
    CLEANUP_INTERVAL = 3600  # Clean expired sessions every hour

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def create_session(self) -> Tuple[str, str]:
        """
        Create a new session.

        Returns:
            Tuple of (session_token, csrf_token)
        """
        self._maybe_cleanup()

        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        now = time.time()

        session = Session(
            token=session_token,
            csrf_token=csrf_token,
            created_at=now,
            last_access=now
        )

        with self._lock:
            self._sessions[session_token] = session

        return session_token, csrf_token

    def validate_session(self, token: Optional[str]) -> Optional[Session]:
        """
        Validate a session token and return the session if valid.

        Uses timing-safe comparison to prevent timing attacks.

        Args:
            token: Session token from cookie

        Returns:
            Session if valid, None otherwise
        """
        if not token:
            return None

        self._maybe_cleanup()

        with self._lock:
            # Use timing-safe comparison by checking against all tokens
            for stored_token, session in self._sessions.items():
                if secrets.compare_digest(stored_token, token):
                    # Check expiration
                    if time.time() - session.created_at > self.SESSION_LIFETIME:
                        del self._sessions[stored_token]
                        return None

                    # Update last access
                    session.last_access = time.time()
                    return session

        return None

    def validate_csrf(self, session_token: Optional[str], csrf_token: Optional[str]) -> bool:
        """
        Validate a CSRF token for a session.

        Args:
            session_token: Session token from cookie
            csrf_token: CSRF token from request

        Returns:
            True if valid, False otherwise
        """
        if not session_token or not csrf_token:
            return False

        session = self.validate_session(session_token)
        if not session:
            return False

        return secrets.compare_digest(session.csrf_token, csrf_token)

    def get_csrf_token(self, session_token: Optional[str]) -> Optional[str]:
        """
        Get the CSRF token for a session.

        Args:
            session_token: Session token from cookie

        Returns:
            CSRF token if session valid, None otherwise
        """
        session = self.validate_session(session_token)
        return session.csrf_token if session else None

    def destroy_session(self, token: Optional[str]) -> None:
        """
        Destroy a session.

        Args:
            token: Session token to destroy
        """
        if not token:
            return

        with self._lock:
            # Use timing-safe lookup
            for stored_token in list(self._sessions.keys()):
                if secrets.compare_digest(stored_token, token):
                    del self._sessions[stored_token]
                    break

    def _maybe_cleanup(self) -> None:
        """Clean up expired sessions periodically"""
        now = time.time()
        if now - self._last_cleanup < self.CLEANUP_INTERVAL:
            return

        with self._lock:
            self._last_cleanup = now
            expired = []
            for token, session in self._sessions.items():
                if now - session.created_at > self.SESSION_LIFETIME:
                    expired.append(token)

            for token in expired:
                del self._sessions[token]


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get the global session manager, creating it if needed"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
