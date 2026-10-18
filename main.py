
import logging
import time
import uuid
from collections import deque
from threading import Lock

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

EMAIL = "25f1002516@ds.study.iitm.ac.in"

app = FastAPI(title="Prometheus Monitoring API")

# Prometheus counter: counts requests to every endpoint.
REQUESTS = Counter(
    "http_requests_total",
    "Total number of HTTP requests received",
)

START_TIME = time.monotonic()
LOG_LIMIT = 500
recent_logs = deque(maxlen=LOG_LIMIT)
log_lock = Lock()

# Log to the terminal as structured JSON.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("monitoring_api")


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    # Count every request, including /metrics and /healthz.
    REQUESTS.inc()

    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - start
        entry = {
            "level": "ERROR",
            "ts": time.time(),
            "path": request.url.path,
            "request_id": request_id,
        }
        with log_lock:
            recent_logs.append(entry)
        logger.error(
            '{"level":"ERROR","ts":%s,"path":"%s","request_id":"%s"}',
            entry["ts"], entry["path"], request_id,
        )
        raise

    duration = time.perf_counter() - start
    entry = {
        "level": "INFO",
        "ts": time.time(),
        "path": request.url.path,
        "request_id": request_id,
    }

    with log_lock:
        recent_logs.append(entry)

    logger.info(
        '{"level":"INFO","ts":%s,"path":"%s","request_id":"%s"}',
        entry["ts"], entry["path"], request_id,
    )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{duration:.6f}"
    return response


@app.get("/work")
async def do_work(n: int = Query(...)):
    return {"email": EMAIL, "done": n}


@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_s": max(0.0, time.monotonic() - START_TIME),
    }


@app.get("/logs/tail")
async def logs_tail(limit: int = Query(10, ge=1, le=500)):
    with log_lock:
        entries = list(recent_logs)
    return entries[-limit:]
