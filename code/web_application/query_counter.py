"""
DATA-260 Homework 4 - Part 3: SQL query counting.

Counts the actual SQL statements executed on a given database connection
during one request, via SQLAlchemy's before_cursor_execute event, storing
the count on that Connection's own .info dict (scoped per connection
checkout - i.e., per request, since each request's Session uses one
connection for its duration). The count is then smuggled out to the
middleware via request.state, which is safe because it's a plain shared
object reference passed explicitly through the ASGI call chain - NOT a
contextvar, which (as discovered the hard way) does not propagate
mutations made inside FastAPI's separate sync-endpoint thread back to
the async middleware's copy of the context.
"""

from sqlalchemy import event


def register_query_counter(engine):
    @event.listens_for(engine, "before_cursor_execute")
    def _count_query(conn, cursor, statement, parameters, context, executemany):
        conn.info["query_count"] = conn.info.get("query_count", 0) + 1


async def query_count_middleware(request, call_next):
    response = await call_next(request)
    count = getattr(request.state, "sql_query_count", None)
    if count is not None:
        response.headers["X-SQL-Query-Count"] = str(count)
    return response