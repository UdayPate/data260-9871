"""
DATA-260 Homework 5 - Part 2A: TheMealDB tutorial MCP server.

A local MCP server named "meals" exposing four tools over STDIO:
    search_meals_by_name(query, limit=5)
    meals_by_ingredient(ingredient, limit=12)
    meal_details(id)
    random_meal()

Run it with the MCP Inspector from the repo root:
    mcp dev code/meals_server.py --with typer

The `--with typer` is not optional, and the reason is a bug in the SDK, not
in this file. `mcp dev` hands the Inspector the command
    uv run --with mcp==<version> mcp run <file>
which builds a fresh throwaway environment containing `mcp` but NOT the
`[cli]` extra. The `mcp run` entry point then dies at startup with
    Error: typer is required. Install with 'pip install mcp[cli]'
and it writes that line to STDOUT, which corrupts the JSON-RPC stream. The
Inspector then loops on "Unexpected token 'E', \"Error: typ\"... is not
valid JSON". Passing `--with typer` puts typer in that environment and the
server starts normally. httpx does not need a flag because it is declared
in `dependencies=` below, which `mcp dev` appends to the uv command itself.

SDK note: the assignment says "runs FastMCP over STDIO". `pip install
"mcp[cli]"` now installs mcp 2.x, where FastMCP was renamed to MCPServer;
the API is otherwise the same and `mcp dev` is unchanged. This file uses
the current name.

LOGGING RULE: this is a STDIO server, so stdout carries the JSON-RPC
stream. Anything printed there corrupts it. Every diagnostic goes to
stderr through the logger below - there is no print() in this file.

ERROR RULE: failures are raised as ToolError. In mcp 2.x that is the only
exception type whose message is forwarded to the client - a ValueError or
RuntimeError is deliberately masked as the generic "Error executing tool
<name>", which would hide the reason in the MCP Inspector.
"""

import logging
import sys
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,  # never stdout
    format="%(asctime)s %(levelname)s [meals] %(message)s",
)
log = logging.getLogger("meals")

API_BASE = "https://www.themealdb.com/api/json/v1/1"
TIMEOUT = httpx.Timeout(15.0, connect=10.0)

# dependencies= is read by `mcp dev`, which appends each entry to the uv
# command as another --with. Without it the throwaway environment the
# Inspector builds would have no httpx and the import would fail.
mcp = MCPServer("meals", dependencies=["httpx"])


def _get(path: str, params: dict[str, Any]) -> dict:
    """One place for the HTTP call, the timeout and the error translation.

    Network and JSON failures are raised as ToolError so the client (the
    MCP Inspector) shows a clean, specific message rather than a masked
    generic string.
    """
    url = f"{API_BASE}/{path}"
    log.info("GET %s params=%s", url, params)
    try:
        response = httpx.get(url, params=params, timeout=TIMEOUT)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise ToolError(f"TheMealDB timed out after {TIMEOUT.read}s") from exc
    except httpx.HTTPStatusError as exc:
        raise ToolError(
            f"TheMealDB returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"Could not reach TheMealDB: {exc}") from exc

    try:
        return response.json()
    except ValueError as exc:
        raise ToolError("TheMealDB returned a response that is not JSON") from exc


def _card(meal: dict) -> dict:
    """The small shape used by the two list tools."""
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "area": meal.get("strArea"),
        "category": meal.get("strCategory"),
        "thumb": meal.get("strMealThumb"),
    }


def _full(meal: dict) -> dict:
    """The full recipe shape used by meal_details and random_meal.

    TheMealDB stores ingredients as 20 flat pairs of strIngredientN /
    strMeasureN, mostly empty. They are zipped back into a list here and
    blank slots dropped.
    """
    ingredients = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        if name:
            ingredients.append({"name": name, "measure": measure})

    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource"),
        "youtube": meal.get("strYoutube"),
        "ingredients": ingredients,
    }


@mcp.tool()
def search_meals_by_name(query: str, limit: int = 5) -> list[dict] | str:
    """Search TheMealDB for meals whose name matches `query`.

    Returns up to `limit` meals as objects with id, name, area, category
    and thumb. When there are no matches, returns a short message instead
    of an empty list, so the result is unambiguous in the Inspector.
    """
    if not query or not query.strip():
        raise ToolError("query must not be empty")
    if not 1 <= limit <= 25:
        raise ToolError(f"limit must be between 1 and 25, got {limit}")

    data = _get("search.php", {"s": query.strip()})
    meals = data.get("meals")
    if not meals:
        log.info("no matches for query=%r", query)
        return f"no matches for {query!r}"
    return [_card(m) for m in meals[:limit]]


@mcp.tool()
def meals_by_ingredient(ingredient: str, limit: int = 12) -> list[dict] | str:
    """Filter TheMealDB by main ingredient.

    Returns up to `limit` small cards with id, name and thumb. This
    endpoint does not return area or category, so those are omitted
    rather than reported as null.
    """
    if not ingredient or not ingredient.strip():
        raise ToolError("ingredient must not be empty")
    if not 1 <= limit <= 50:
        raise ToolError(f"limit must be between 1 and 50, got {limit}")

    data = _get("filter.php", {"i": ingredient.strip()})
    meals = data.get("meals")
    if not meals:
        log.info("no matches for ingredient=%r", ingredient)
        return f"no matches for ingredient {ingredient!r}"
    return [
        {"id": m.get("idMeal"), "name": m.get("strMeal"), "thumb": m.get("strMealThumb")}
        for m in meals[:limit]
    ]


@mcp.tool()
def meal_details(id: str | int) -> dict | str:
    """Look up one meal by its TheMealDB id and return the full recipe."""
    meal_id = str(id).strip()
    if not meal_id.isdigit():
        raise ToolError(f"id must be numeric, got {id!r}")

    data = _get("lookup.php", {"i": meal_id})
    meals = data.get("meals")
    if not meals:
        log.info("no meal with id=%s", meal_id)
        return f"no meal found with id {meal_id}"
    return _full(meals[0])


@mcp.tool()
def random_meal() -> dict | str:
    """Return one random meal, in the same shape as meal_details."""
    data = _get("random.php", {})
    meals = data.get("meals")
    if not meals:
        return "no random meal available right now"
    return _full(meals[0])


if __name__ == "__main__":
    log.info("starting meals MCP server on stdio")
    mcp.run(transport="stdio")
