"""Create a consistent local SQLite backup of MemoryVault's database."""

import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "instance" / "memoryvault.db"
BACKUP_DIR = ROOT / "instance" / "backups"


def main():
    if not SOURCE.exists():
        raise SystemExit(f"Database not found: {SOURCE}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"memoryvault-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    source = sqlite3.connect(SOURCE)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    print(f"Backup created: {target}")


if __name__ == "__main__":
    main()
