import argparse
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import AdminUser
from app.config import Settings
from app.db import make_engine
from app.security import hash_password


def create_admin(parser: argparse.ArgumentParser, name: str) -> None:
    username = name.strip().lower()
    if not username or len(username) > 64:
        parser.error("Enter a username between 1 and 64 characters.")
    password = getpass("New admin password: ")
    if not 12 <= len(password) <= 256 or password != getpass("Confirm password: "):
        parser.error("Passwords must match and contain 12–256 characters.")
    engine = make_engine(Settings())
    try:
        with Session(engine) as db, db.begin():
            if db.scalar(select(AdminUser.id).where(AdminUser.username == username)):
                parser.error("This administrator already exists.")
            db.add(AdminUser(username=username, password_hash=hash_password(password)))
    finally:
        engine.dispose()
    print(f"Administrator created: {username}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Photo booth administration tasks")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin")
    admin.add_argument("username")
    args = parser.parse_args()
    create_admin(admin, args.username)


if __name__ == "__main__":
    main()
