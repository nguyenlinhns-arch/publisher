from __future__ import annotations

import getpass
import os
from dataclasses import dataclass


SERVICE_NAME = "MXHPublisher"
FACEBOOK_TOKEN_NAME = "facebook_page_token"


class SecretStoreError(RuntimeError):
    pass


@dataclass(slots=True)
class SecretStore:
    service_name: str = SERVICE_NAME

    def _keyring(self):
        try:
            import keyring
        except ImportError as exc:
            raise SecretStoreError(
                "Chưa cài keyring. Chạy pip install -r requirements.txt."
            ) from exc
        return keyring

    def get(self, name: str) -> str | None:
        environment_name = f"MXH_{name.upper()}"
        if value := os.environ.get(environment_name):
            return value
        try:
            return self._keyring().get_password(self.service_name, name)
        except Exception as exc:
            raise SecretStoreError(
                f"Không đọc được Windows Credential Manager: {exc}"
            ) from exc

    def set(self, name: str, value: str) -> None:
        if not value.strip():
            raise ValueError("Bí mật không được để trống.")
        try:
            self._keyring().set_password(self.service_name, name, value.strip())
        except Exception as exc:
            raise SecretStoreError(
                f"Không lưu được Windows Credential Manager: {exc}"
            ) from exc

    def delete(self, name: str) -> None:
        try:
            self._keyring().delete_password(self.service_name, name)
        except Exception as exc:
            raise SecretStoreError(f"Không xóa được bí mật: {exc}") from exc


def prompt_and_store_facebook_token(store: SecretStore | None = None) -> None:
    store = store or SecretStore()
    token = getpass.getpass("Dán Page access token (không hiển thị): ")
    store.set(FACEBOOK_TOKEN_NAME, token)
    print("Đã lưu token an toàn trong kho thông tin xác thực của hệ điều hành.")
