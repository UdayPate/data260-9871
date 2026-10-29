"""
DATA-260 Homework 8 Part 1 - FastAPI wrapper around the Kafka request/response service.

    POST /fixtures          -> CREATE_ENTITY
    GET  /fixtures/{id}     -> GET_ENTITY
    POST /kafka/request     -> any operation (used to show the Unknown operation error)

The API never touches the entity dict: every call becomes a Kafka request and waits for the matching
response. A caller may pass its own X-Correlation-ID header (used by the Part 3 replay tests); otherwise
the API creates one. The correlation_id is returned in both the body and the X-Correlation-ID header.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi import Header

from common import PORT_BASE, setup_logging
from kafka_rpc import KafkaRpcClient

log = setup_logging("api")
rpc: KafkaRpcClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rpc
    rpc = await run_in_threadpool(KafkaRpcClient, log)
    log.info("Kafka client ready. FastAPI server started at http://127.0.0.1:%d", PORT_BASE)
    yield
    rpc.close()


app = FastAPI(title="HW8 Fixture service over Kafka", lifespan=lifespan)


async def call(operation: str, data, correlation_id: str | None) -> JSONResponse:
    log.info("HTTP -> Kafka op=%s", operation)
    response = await run_in_threadpool(rpc.request, operation, data, correlation_id)
    log.info("Kafka -> HTTP corr=%s success=%s", response["correlation_id"], response["success"])
    if response["success"]:
        status = 200
    elif response.get("error") == "Entity not found":
        status = 404
    elif response.get("error", "").startswith("Timed out"):
        status = 504
    else:
        status = 400
    return JSONResponse(response, status_code=status, headers={"X-Correlation-ID": response["correlation_id"]})


@app.post("/fixtures")
async def create_fixture(data: dict, x_correlation_id: str | None = Header(None)):
    return await call("CREATE_ENTITY", data, x_correlation_id)


@app.get("/fixtures/{entity_id}")
async def get_fixture(entity_id: str, x_correlation_id: str | None = Header(None)):
    return await call("GET_ENTITY", {"entity_id": entity_id}, x_correlation_id)


@app.post("/kafka/request")
async def raw_request(body: dict, x_correlation_id: str | None = Header(None)):
    return await call(body.get("operation", ""), body.get("data", {}), x_correlation_id)


@app.get("/health")
def health():
    return {"status": "ok"}
