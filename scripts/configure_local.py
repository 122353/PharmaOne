"""Create ignored local PharmaOne configuration without echoing credentials."""
import base64
import getpass
import os
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import urlopen
import json


ROOT = Path(__file__).resolve().parents[1]
API_ENV = ROOT / "api/.env"
WEB_ENV = ROOT / "web/.env.local"


def database_url(template: str, password: str) -> str:
    if "[YOUR-PASSWORD]" not in template or not template.startswith("postgresql://"):
        raise ValueError("Copy the Session pooler URI with its [YOUR-PASSWORD] placeholder")
    uri = template.replace("[YOUR-PASSWORD]", quote(password, safe=""), 1)
    parsed = urlparse(uri)
    if not parsed.hostname or parsed.port != 5432 or not parsed.username:
        raise ValueError("Use the Session pooler URI on port 5432")
    uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)
    return uri + ("&" if "?" in uri else "?") + "sslmode=require"


def main() -> None:
    if API_ENV.exists() or WEB_ENV.exists():
        raise SystemExit("A local env file already exists. Nothing was overwritten.")
    print("Use your Supabase project's Project URL, publishable key, and Connect → Session pooler URI.")
    print("Inputs are saved only in ignored local files. No credential is printed.")
    project_url = input("Project URL: ").strip().rstrip("/")
    if urlparse(project_url).scheme != "https" or not urlparse(project_url).hostname:
        raise SystemExit("Project URL must be HTTPS.")
    public_key = getpass.getpass("Publishable key (input hidden): ").strip()
    if not public_key.startswith("sb_publishable_"):
        raise SystemExit("Use the sb_publishable_ key, never a secret or service-role key.")
    uri_template = input("Session pooler URI with [YOUR-PASSWORD] unchanged: ").strip()
    password = getpass.getpass("Database password (input hidden): ")
    try:
        postgres_url = database_url(uri_template, password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        with urlopen(project_url + "/auth/v1/.well-known/jwks.json", timeout=12) as response:
            keys = json.load(response).get("keys", [])
        if not keys:
            raise SystemExit("Supabase has no asymmetric JWT signing key yet. Enable one in Project Settings.")
    except OSError as exc:
        raise SystemExit("Could not validate the Supabase JWKS endpoint. No files were written.") from exc

    encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    API_ENV.write_text(
        f"DATABASE_URL={postgres_url}\nSUPABASE_URL={project_url}\n"
        f"SUPABASE_JWT_AUDIENCE=authenticated\nTINYFISH_ENCRYPTION_KEY={encryption_key}\n"
        "ALLOWED_ORIGINS=http://localhost:3000\n",
        encoding="utf-8",
    )
    WEB_ENV.write_text(
        f"NEXT_PUBLIC_API_URL=http://localhost:8000\nNEXT_PUBLIC_SUPABASE_URL={project_url}\n"
        f"NEXT_PUBLIC_SUPABASE_ANON_KEY={public_key}\n",
        encoding="utf-8",
    )
    print("Created api/.env and web/.env.local. Keep both files private and do not commit them.")


if __name__ == "__main__":
    main()
