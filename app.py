"""GRIDPOINT — Warehouse Location Optimization Platform.
FastAPI Application Entrypoint (Hack-A-Matics 2026).
"""

import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load environment variables from .env file
load_dotenv()

from optimization.cflp import get_milp_solver, SolverUnavailableError
from api.routes import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gridpoint")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan event: Verifies CBC solver at application startup."""
    logger.info("⚡ Initializing GRIDPOINT platform...")
    try:
        solver = get_milp_solver()
        if solver.available():
            logger.info(f"✅ CBC MILP solver detected and active: {type(solver).__name__}")
        else:
            logger.warning("⚠️ CBC binary not detected on PATH; CFLP will use greedy + 2-opt local search heuristic fallback.")
    except Exception as exc:
        logger.warning(f"⚠️ Solver detection notice ({exc}); CFLP will use greedy + 2-opt heuristic fallback.")

    # Load cities geodata once into memory at backend startup
    try:
        from core.geodata import load_cities_geodata
        cities_cache = load_cities_geodata()
        logger.info(f"✅ Cities geodata loaded into memory: {len(cities_cache):,} cities.")
    except Exception as exc:
        logger.warning(f"⚠️ Geodata loading notice: {exc}")

    yield
    logger.info("GRIDPOINT platform shutting down.")


app = FastAPI(
    title="GRIDPOINT — Warehouse Location Optimization Platform",
    description="Operations-research B2B platform coupling Strategic CFLP and Tactical CVRP.",
    version="2.0.0",
    lifespan=lifespan,
)

# Enable CORS for local development and tooling
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_router)

# Mount static files at root
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
