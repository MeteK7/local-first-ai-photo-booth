import argparse
import re
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import AdminUser
from app.ai_photos import AITemplate
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


def configure_template(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.template_id) or len(args.template_id) > 64:
        parser.error("Use an ID of at most 64 lowercase letters, digits, and hyphens.")
    updates = {field: getattr(args, field) for field in ("name", "description", "prompt")
               if getattr(args, field) is not None}
    for field, limit in (("name", 80), ("description", 240), ("prompt", 32000)):
        if field in updates and not 1 <= len(updates[field].strip()) <= limit:
            parser.error(f"{field.capitalize()} must contain 1 to {limit} characters.")
    if args.enabled is not None:
        updates["enabled"] = args.enabled
    if not updates:
        parser.error("Specify one or more template fields.")
    engine = make_engine(Settings())
    try:
        with Session(engine) as db, db.begin():
            template = db.get(AITemplate, args.template_id, with_for_update=True)
            if template is None:
                if not {"name", "description", "prompt"} <= updates.keys():
                    parser.error("A new template requires --name, --description, and --prompt.")
                updates.setdefault("enabled", True)
                db.add(AITemplate(id=args.template_id, **updates))
            else:
                for field, value in updates.items():
                    setattr(template, field, value)
    finally:
        engine.dispose()
    print(f"Photo effect template saved: {args.template_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Photo booth administration tasks")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin")
    admin.add_argument("username")
    template = commands.add_parser("set-ai-template")
    template.add_argument("template_id")
    template.add_argument("--name")
    template.add_argument("--description")
    template.add_argument("--prompt")
    template.add_argument("--enabled", action=argparse.BooleanOptionalAction)
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(admin, args.username)
    else:
        configure_template(template, args)


if __name__ == "__main__":
    main()
