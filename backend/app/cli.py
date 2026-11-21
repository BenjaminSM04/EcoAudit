"""Tareas de administración.

python -m app.cli create-user --email a@b.c --name "Nombre" --role admin
python -m app.cli register-model RUTA_DEL_BUNDLE --activate
python -m app.cli db-upgrade
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import select

from .db import init_db, new_session
from .deps import record
from .migrate import AdoptionError
from .models import Role, User
from .pipeline.bundle import BundleError
from .registry import register_bundle
from .security import hash_password


def _create_user(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Contraseña (mínimo 10 caracteres): ")
    if len(password) < 10:
        print("La contraseña debe tener al menos 10 caracteres.", file=sys.stderr)
        return 1
    email = args.email.strip().lower()
    with new_session() as db:
        if db.scalar(select(User).where(User.email == email)) is not None:
            print(f"Ya existe un usuario con el correo {email}.", file=sys.stderr)
            return 1
        user = User(
            email=email,
            full_name=args.name,
            password_hash=hash_password(password),
            role=Role(args.role),
        )
        db.add(user)
        db.flush()
        record(db, None, "user_created", "user", user.id, role=args.role, via="cli")
        db.commit()
        print(f"Usuario creado: {email} ({args.role})")
    return 0


def _register_model(args: argparse.Namespace) -> int:
    with new_session() as db:
        try:
            model = register_bundle(db, Path(args.directory), activate=args.activate)
        except BundleError as exc:
            print(f"Bundle rechazado: {exc}", file=sys.stderr)
            return 1
        record(
            db,
            None,
            "model_registered",
            "model_version",
            model.id,
            sha256=model.bundle_sha256,
            activated=args.activate,
            via="cli",
        )
        db.commit()
        state = "activo" if model.is_active else "inactivo"
        print(f"Modelo registrado: {model.name} {model.version} (id {model.id}, {state})")
    return 0


def _db_upgrade(args: argparse.Namespace) -> int:
    report = init_db()
    if report.adopted:
        print("Base anterior a Alembic adoptada y marcada como 0001.")
        print(f"  Tablas creadas: {', '.join(report.tables_created) or 'ninguna'}")
        print(f"  Columnas agregadas: {', '.join(report.columns_added) or 'ninguna'}")
    print(f"Base de datos en la revisión {report.revision}.")
    return 0


def _make_demo_bundle(args: argparse.Namespace) -> int:
    from .devtools import make_demo_bundle

    path = make_demo_bundle(Path(args.directory))
    print(f"Bundle de demostración escrito en {path}. No tiene validez diagnóstica.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    user = sub.add_parser("create-user", help="Crea un usuario")
    user.add_argument("--email", required=True)
    user.add_argument("--name", required=True)
    user.add_argument("--role", required=True, choices=[r.value for r in Role])
    user.add_argument("--password", help="Si se omite, se pide por teclado")
    user.set_defaults(func=_create_user)

    model = sub.add_parser("register-model", help="Valida y registra un bundle de modelo")
    model.add_argument("directory")
    model.add_argument("--activate", action="store_true")
    model.set_defaults(func=_register_model)

    demo = sub.add_parser(
        "make-demo-bundle", help="Genera un bundle de demostración (sin validez alguna)"
    )
    demo.add_argument("directory")
    demo.set_defaults(func=_make_demo_bundle)

    upgrade = sub.add_parser(
        "db-upgrade",
        help="Lleva la base a la última migración (adopta antes una base anterior a Alembic)",
    )
    # Es la propia migración: no hace falta migrar antes de ejecutarla.
    upgrade.set_defaults(func=_db_upgrade, skip_init=True)

    args = parser.parse_args(argv)
    try:
        if not getattr(args, "skip_init", False):
            init_db()
        return args.func(args)
    except AdoptionError as exc:
        print(f"No se pudo migrar la base de datos: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
