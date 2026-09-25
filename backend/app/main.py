"""Application startup, patient routes, and consistent API error envelopes."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from .database import initialize_database
from .routers.patients import router as patients_router
from .routers.vapi import router as vapi_router
from .schemas import Envelope
from .seed import seed_demo_patients


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    seed_demo_patients()
    yield


app = FastAPI(title="Voice AI Patient Registration", lifespan=lifespan)
app.include_router(patients_router)
app.include_router(vapi_router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"data": None, "error": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Exclude raw inputs and exception contexts: these can contain patient data
    # or non-JSON-serializable ValueError objects.
    errors = [
        {"field": ".".join(map(str, error["loc"])),
         "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"data": None, "error": {"details": errors}})


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    return JSONResponse(
        status_code=500,
        content={"data": None, "error": "Database operation failed. Please try again."},
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"data": None, "error": "An unexpected server error occurred."},
    )


@app.get(
    "/health", response_model=Envelope[dict[str, str]],
    responses={500: {"model": Envelope[None], "description": "Server failure"}},
)
def health():
    return {"data": {"status": "ok"}, "error": None}
