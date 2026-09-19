"""GRIDPOINT — Warehouse Location Optimization Platform.
FastAPI Application Entrypoint (Hack-A-Matics 2026).
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
        if not solver.available():
            raise SolverUnavailableError("Solver binary could not be verified.")
        logger.info(f"✅ CBC MILP solver detected and active: {type(solver).__name__}")
    except Exception as exc:
        msg = (
            "\n" + "=" * 70 + "\n"
            "🚨 CRITICAL ERROR: CBC MILP Solver Not Available!\n"
            f"Details: {exc}\n"
            "Please install the CBC solver package:\n"
            "    pip install \"pulp[cbc]\"\n"
            "or ensure the 'cbc' executable is present on your system PATH.\n"
            + "=" * 70 + "\n"
        )
        logger.error(msg)
        raise RuntimeError(msg) from exc

    yield
    logger.info("GRIDPOINT platform shutting down.")


app = FastAPI(
    title="GRIDPOINT — Warehouse Location Optimization Platform",
    description="Operations-research B2B platform coupling Strategic CFLP (PuLP/CBC) and Tactical CVRP (Google OR-Tools).",
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
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
