"""
DATA-260 Homework 5 - Part 3.19: timeout + bounded exponential-backoff retry
policy. This is the policy Part 4's execute_tool wraps every domain-tool
call in, so it returns the same {ok, data, error} envelope used everywhere
else in this homework.

call_with_retry(operation) never raises - any exception or timeout from
`operation` is caught, retried with exponential backoff up to max_retries
times, and if every attempt fails the function returns a clean
{ok: False, ...} result instead of crashing.

Each attempt runs in a worker thread so timeout_s is a REAL enforced
timeout (not just a latency measurement) and works the same on Windows
and Linux.
"""

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

_executor = ThreadPoolExecutor(max_workers=8)


class SimulatedFailure(Exception):
    """Used only by the fault-injection demo/measurement, never by real
    domain-tool calls."""


def call_with_retry(
    operation,
    *,
    max_retries: int = 3,
    base_delay_s: float = 0.05,
    max_delay_s: float = 1.0,
    timeout_s: float = 2.0,
) -> dict:
    """Call the zero-arg `operation`, retrying on any exception or timeout.

    Backoff is base_delay_s * 2**attempt, capped at max_delay_s.
    Returns {ok, data, error, attempts, latency_ms} - attempts counts the
    total number of tries (1 = succeeded or failed on the first try).
    """
    start = time.monotonic()
    last_err = None
    for attempt in range(max_retries + 1):
        future = _executor.submit(operation)
        try:
            data = future.result(timeout=timeout_s)
            return {
                "ok": True,
                "data": data,
                "error": None,
                "attempts": attempt + 1,
                "latency_ms": (time.monotonic() - start) * 1000,
            }
        except FutureTimeoutError:
            last_err = f"timed out after {timeout_s}s"
        except Exception as exc:
            last_err = str(exc)

        if attempt < max_retries:
            time.sleep(min(base_delay_s * (2**attempt), max_delay_s))

    return {
        "ok": False,
        "data": None,
        "error": last_err,
        "attempts": max_retries + 1,
        "latency_ms": (time.monotonic() - start) * 1000,
    }
