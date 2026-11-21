"""Almacén de objetos sobre disco local.

La interfaz (claves tipo ``images/12/ab.png``) es la de un almacén de objetos, de modo que
cambiar a MinIO/S3 solo exige reimplementar esta clase.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import get_settings


class Storage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError(f"Clave fuera del almacén: {key!r}")
        return target

    def put_bytes(self, key: str, data: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def put_dir(self, key: str, source: Path) -> None:
        target = self.path(key)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)

    def delete(self, key: str) -> None:
        """Borra un objeto si existe (para deshacer una carga que no llegó a confirmarse)."""
        self.path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self.path(key).exists()


def get_storage() -> Storage:
    return Storage(get_settings().storage_dir)
