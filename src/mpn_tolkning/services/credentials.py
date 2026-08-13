from __future__ import annotations

import keyring


class CredentialStore:
    """Store provider secrets only in the operating-system credential backend."""

    service_prefix = "mpn-tolkning"

    def set(self, provider: str, username: str, password: str) -> None:
        keyring.set_password(self._service(provider), username, password)

    def get(self, provider: str, username: str) -> str | None:
        if not username:
            return None
        return keyring.get_password(self._service(provider), username)

    def delete(self, provider: str, username: str) -> None:
        keyring.delete_password(self._service(provider), username)

    def _service(self, provider: str) -> str:
        cleaned = str(provider).strip()
        if not cleaned:
            raise ValueError("Provider name is required.")
        return f"{self.service_prefix}:{cleaned}"
