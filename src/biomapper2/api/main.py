"""FastAPI application for biomapper2 REST API."""

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..mapper import Mapper
from .auth import validate_api_key
from .constants import API_VERSION
from .kestrel_discovery import derive_presets_with_fallback
from .routes import discovery, mapping

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for FastAPI app.

    Initializes the Mapper singleton on startup and stores it in app.state.
    The Mapper is heavy to initialize (loads Biolink model) so we do it once.
    """
    logger.info("Initializing Mapper...")
    start = time.time()
    try:
        app.state.mapper = Mapper()
        duration = time.time() - start
        logger.info(f"Mapper initialized in {duration:.2f}s")
    except Exception as e:
        logger.error(f"Failed to initialize Mapper: {e}")
        app.state.mapper = None
        app.state.mapper_error = str(e)

    # Derive entity type presets from Kestrel (never crashes startup).
    try:
        app.state.entity_type_presets = derive_presets_with_fallback()
        logger.info("Loaded %d entity type presets", len(app.state.entity_type_presets))
    except Exception as e:
        logger.error(f"Failed to load entity type presets: {e}")
        app.state.entity_type_presets = None

    yield
    # Cleanup on shutdown (if needed)
    logger.info("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Biomapper2 API",
    description="REST API for mapping biological entities to knowledge graph nodes",
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    """Add request timing to response headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000  # ms
    response.headers["X-Process-Time-Ms"] = str(round(process_time, 2))
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
        },
    )


# Health check — no auth required, mounted at both /api/v1 and /discovery
app.include_router(discovery.health_router, prefix="/api/v1", tags=["Discovery"])
app.include_router(discovery.health_router, prefix="/discovery", include_in_schema=False)

# Primary routes — require X-API-Key
app.include_router(discovery.router, prefix="/api/v1", tags=["Discovery"], dependencies=[Depends(validate_api_key)])
app.include_router(mapping.router, prefix="/api/v1/map", tags=["Mapping"])

# Proxy routes — no API key (biomapper-ui Clerk handles auth)
app.include_router(discovery.router, prefix="/discovery", include_in_schema=False)
app.include_router(mapping.router, prefix="/map", include_in_schema=False)


# Root redirect
@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to API docs."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/api/v1/docs")
