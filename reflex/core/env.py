"""Zero-dependency .env file loader.

Reads KEY=VALUE pairs from a .env file and sets them in os.environ.
Does NOT overwrite existing environment variables (shell wins over .env).
Supports comments (#), blank lines, and quoted values.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load environment variables from a .env file.

    Args:
        path: Path to the .env file. Defaults to '.env' in CWD.

    Rules:
        - Lines starting with # are comments.
        - Blank lines are ignored.
        - Format: KEY=VALUE (inline comments after # are stripped).
        - Values can be single-quoted, double-quoted, or unquoted.
        - Existing os.environ values are never overwritten.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return

    content = env_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue

        # Split on first =
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        # Remove inline comments (but not inside quotes)
        if not (value.startswith('"') or value.startswith("'")):
            if " #" in value:
                value = value[: value.index(" #")]
            elif "\t#" in value:
                value = value[: value.index("\t#")]

        # Strip quotes
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        # Never override existing env vars
        if key and key not in os.environ:
            os.environ[key] = value
