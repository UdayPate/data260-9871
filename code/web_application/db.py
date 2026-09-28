"""
DATA-260 Homework 4 - Part 2: MySQL database connection setup.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

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