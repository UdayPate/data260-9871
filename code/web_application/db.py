"""
DATA-260 Homework 4 - Part 2: MySQL database connection setup.

HW5 addition: credentials are read from a gitignored `.env` file sitting
next to this module if one exists, so scripts and test runners pick up
the same MYSQL_USER / MYSQL_PASSWORD without them being typed on a
command line. Real environment variables always win over the file.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    # encoding="utf-8-sig", not "utf-8": PowerShell 5.1's
    # `Set-Content -Encoding utf8` writes a UTF-8 BOM, which would
    # otherwise become part of the FIRST key's name ("\ufeffMYSQL_USER")
    # and silently leave that variable unset.
    for _line in _ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _value = _line.split("=", 1)
        _value = _value.strip().strip('"').strip("'")
        # setdefault: a real environment variable takes precedence.
        os.environ.setdefault(_key.strip(), _value)

MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_HOST = "localhost"
MYSQL_DB = "s9871_rel"

DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"

# echo=True logs every actual SQL statement SQLAlchemy sends to MySQL -
# this will be essential later in Part 3 for literally counting N+1 queries.
engine = create_engine(DATABASE_URL, echo=True)

# Required exact variable name per the assignment.
db_session_basede26 = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields one DB session per request, always
    closing it afterward even if the request raised an error."""
    db = db_session_basede26()
    try:
        yield db
    finally:
        db.close()
