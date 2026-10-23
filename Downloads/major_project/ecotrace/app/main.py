"""FastAPI application factory for EcoTrace AI.

Auth model:
  admin    — full access (create resources, HITL approve, revoke badges)
  operator — create collections, submit evidence / completion / narration, upload media
  viewer   — read-only (GET endpoints, marketplace)

Every router is protected by get_current_user except /auth/* and /health.
The Swagger UI at /docs includes an Authorize button for the Bearer token.
"""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.auth import get_current_user, require_admin, require_operator, require_viewer
from app.routers import auth, badges, collections, facilities, marketplace, producers, uploads

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="EcoTrace AI",
    version="0.2.0-dev",
    description=(
        "E-waste EPR compliance verification platform.\n\n"
        "Issues a **Trust Badge** (technical verification attestation — not a legal document).\n\n"
        "**Step 1 (complete):** Backend engine, state machine, REST API, 58 tests.\n\n"
        "**Step 2 (in progress):** JWT auth + file uploads wired. "
        "Alembic, Docker, and CI are upcoming.\n\n"
        "Use `/auth/register` → `/auth/login` to get a Bearer token, then click **Authorize**."
    ),
    openapi_tags=[
        {"name": "auth",        "description": "Register, login, profile"},
        {"name": "progress",    "description": "Build progress — what is complete vs pending"},
        {"name": "facilities",  "description": "Recycling facilities"},
        {"name": "collections", "description": "Collection lifecycle + state machine"},
        {"name": "badges",      "description": "Trust Badge reference and revocation"},
        {"name": "marketplace", "description": "Badge marketplace listing"},
        {"name": "producers",   "description": "Producers and EPR obligations"},
        {"name": "uploads",     "description": "Evidence media and invoice file uploads"},
    ],
)

# CORS — wide open for dev; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
# Auth is public
app.include_router(auth.router)

# Admin-only management endpoints
app.include_router(
    facilities.router,
    dependencies=[Depends(require_admin)],
)
app.include_router(
    producers.router,
    dependencies=[Depends(require_admin)],
)

# Operators manage collections, evidence, uploads
app.include_router(
    collections.router,
    dependencies=[Depends(require_operator)],
)
app.include_router(
    uploads.router,
    dependencies=[Depends(require_operator)],
)

# Admin only for badge lifecycle (reference / revoke)
app.include_router(
    badges.router,
    dependencies=[Depends(require_admin)],
)

# Marketplace is viewer-accessible
app.include_router(
    marketplace.router,
    dependencies=[Depends(require_viewer)],
)


# ── Public endpoints ───────────────────────────────────────────────────────────
@app.get("/health", tags=["progress"])
def health():
    """Service liveness probe — no auth required."""
    return {"status": "ok", "version": "0.2.0-dev"}


# ── Progress dashboard ─────────────────────────────────────────────────────────
@app.get("/progress", tags=["progress"])
def progress():
    """
    Human-readable build progress tracker.

    Shows which steps are complete and what remains, so reviewers can see
    exactly how far the project has come at a glance.
    """
    return {
        "project": "EcoTrace AI — EPR e-waste compliance verification",
        "steps": [
            {
                "step": 1,
                "name": "Backend Core",
                "status": "complete",
                "items": [
                    "config.py — all weights/thresholds as single source of truth",
                    "models.py — 11 SQLAlchemy 2.0 tables, naive UTC, Postgres-compatible",
                    "Pure engine — evidence, completion, narration, badge_state (no ORM)",
                    "REST API — facilities, producers, collections, badges, marketplace",
                    "Collection state machine enforced (409 on illegal transitions)",
                    "58 pytest tests — engine unit tests + full API flow tests",
                    "Deterministic synthetic seed — 120 collections, 8 scenarios, CSVs",
                ],
            },
            {
                "step": 2,
                "name": "Auth + Uploads",
                "status": "in_progress",
                "items": [
                    "✅ JWT Bearer auth (python-jose + passlib bcrypt)",
                    "✅ User model with roles: admin / operator / viewer",
                    "✅ POST /auth/register  POST /auth/login  GET /auth/me",
                    "✅ All routers protected by role-based dependencies",
                    "✅ File uploads — POST /collections/{id}/media (multipart, 50 MB cap)",
                    "✅ MediaFile model — stores file refs in DB, bytes on disk",
                    "⏳ Alembic migrations + Postgres deployment (pending)",
                    "⏳ Dockerfile + docker-compose (pending)",
                    "⏳ GitHub Actions CI (pending)",
                ],
            },
            {
                "step": 3,
                "name": "CV Signal Pipeline",
                "status": "pending",
                "items": [
                    "YOLO/OCR/image processing → precomputed numeric signals",
                    "Signals feed existing EvidenceInputs (device_serial_confidence etc.)",
                    "POST /collections/{id}/media/process triggers CV pipeline",
                ],
            },
            {
                "step": 4,
                "name": "Narration Generation",
                "status": "pending",
                "items": [
                    "LangGraph / LLM / RAG generates narrative from verified evidence",
                    "Generated text fed into existing NarrationInputs for scoring",
                    "Two independent scores stay separate (never blended)",
                ],
            },
            {
                "step": 5,
                "name": "Frontend / UI",
                "status": "pending",
                "items": [
                    "Operator dashboard — collections, HITL review queue",
                    "Admin panel — facilities, producers, badge lifecycle",
                    "Badge marketplace — public listing + filter",
                    "Producer obligation dashboard",
                ],
            },
        ],
        "conventions": {
            "datetime":     "naive UTC everywhere (datetime.utcnow())",
            "engine_purity": "app/engine/ imports no ORM/FastAPI/models",
            "weights":      "literals ONLY in app/config.py",
            "output_name":  "Trust Badge (never 'certificate')",
            "scores":       "Evidence Trust Score and Narration Confidence are always separate",
        },
    }
