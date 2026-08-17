"""Agencies router package.

Registration order preserves the critical FastAPI matching constraint:
literal paths (/mcp/discover, /parse-spec) must be registered
BEFORE parametric /{agency_id} paths to avoid UUID wildcard shadowing.

list_agencies and create_agency are registered directly on this router
(not via include_router) to avoid FastAPI's empty-path constraint, which
rejects sub-routers whose combined prefix+path would be empty.
"""

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import require_admin
from app.models.user import User
from app.routers.agencies import crud, golden, lifecycle, logo, spec
from app.schemas.agency import AgencyCreate, AgencyListResponse, AgencyResponse

router = APIRouter(prefix="/agencies", tags=["Agencies"])

# Root collection routes registered directly (prefix="/agencies" + path="" = /agencies)
router.get("", response_model=AgencyListResponse, summary="List agencies")(crud.list_agencies)
router.post("", response_model=AgencyResponse, status_code=status.HTTP_201_CREATED, summary="Create agency")(crud.create_agency)

# Literal-path sub-routers first (no /{agency_id} wildcard)
router.include_router(spec.router)

# Sub-resource routers
router.include_router(lifecycle.router)
router.include_router(golden.router)
router.include_router(logo.router)

# CRUD parametric routes last (/{id} catch-all)
router.include_router(crud.router)

# Re-export handler functions that tests import directly from this package.
create_agency = crud.create_agency
list_agencies = crud.list_agencies
get_agency = crud.get_agency
update_agency_status = lifecycle.update_agency_status
agency_health_history = lifecycle.agency_health_history
mcp_discover = spec.mcp_discover
upload_agency_logo = logo.upload_agency_logo
get_agency_logo = logo.get_agency_logo
