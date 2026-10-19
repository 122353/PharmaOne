"""Copy only the browser-public Supabase settings to the linked Vercel project.

Values are passed to the official CLI on stdin, never in arguments or output.
Run this from the repository root after `vercel link` in web/.
"""

from pathlib import Path
import os
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
KEYS = ("NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY")


def local_values() -> dict[str, str]:
    values = {}
    for line in (WEB / ".env.local").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def main() -> int:
    if not (WEB / ".vercel" / "project.json").exists():
        raise SystemExit("Link web/ to the Vercel Hobby project first")
    values = local_values()
    if not values.get("NEXT_PUBLIC_API_URL", "").startswith("https://"):
        raise SystemExit("NEXT_PUBLIC_API_URL must be an HTTPS production API URL")
    if not values.get("NEXT_PUBLIC_SUPABASE_URL", "").startswith("https://") or "your-project" in values.get("NEXT_PUBLIC_SUPABASE_URL", ""):
        raise SystemExit("Public Supabase URL must be configured locally")
    if not values.get("NEXT_PUBLIC_SUPABASE_ANON_KEY"):
        raise SystemExit("Public Supabase publishable key must be configured locally")
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    if not npx:
        raise SystemExit("npx is unavailable; install Node.js before configuring Vercel")
    for key in KEYS:
        result = subprocess.run(
            [npx, "--yes", "vercel", "env", "add", key, "production,preview", "--type", "config", "--yes", "--force", "--no-color"],
            input=values[key] + "\n", text=True, capture_output=True, cwd=WEB, timeout=90, check=False,
        )
        if result.returncode:
            # Mask both values before exposing a CLI diagnostic.
            diagnostic = (result.stdout + "\n" + result.stderr).strip()
            for configured_value in values.values():
                if configured_value:
                    diagnostic = diagnostic.replace(configured_value, "[REDACTED]")
            raise SystemExit(f"Vercel rejected {key} (exit {result.returncode}): {diagnostic[-1000:]}")
        print(f"Configured {key} for Production and Preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
