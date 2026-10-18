"""Report whether configured provider keys appear outside ignored local configuration.

Only key names and file paths are printed; secret values never are.
"""
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {".git", ".next", "node_modules", ".pytest_cache", "__pycache__", "test-results"}
IGNORED_FILES = {ROOT / "api" / ".env", ROOT / "web" / ".env.local"}
KEY_NAMES = {"TINYFISH_API_KEY", "SARVAM_API_KEY", "DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET", "ENCRYPTION_KEY"}


def configured_keys() -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for source in IGNORED_FILES:
        if not source.exists():
            continue
        for line in source.read_bytes().splitlines():
            if b"=" not in line or line.lstrip().startswith(b"#"):
                continue
            name, value = line.split(b"=", 1)
            decoded = name.strip().decode("ascii", errors="ignore")
            value = value.strip().strip(b"\"'")
            if decoded in KEY_NAMES and len(value) >= 12:
                values[decoded] = value
    return values


def main() -> int:
    keys = configured_keys()
    leaks: list[tuple[str, str]] = []
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        for filename in files:
            path = Path(folder) / filename
            if path in IGNORED_FILES:
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            for name, value in keys.items():
                if value in data:
                    leaks.append((name, str(path.relative_to(ROOT))))
    if leaks:
        for name, path in leaks:
            print(f"Possible {name} exposure in {path}")
        return 1
    print(f"No configured secret values found outside ignored env files ({len(keys)} values checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
