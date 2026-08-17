from app.models.agency import Agency
from app.schemas.agency import AgencyHealthEmbed, AgencyResponse
from app.services.agency_health import embedded_health


async def _with_health(agency: Agency) -> AgencyResponse:
    resp = AgencyResponse.model_validate(agency)
    resp.health = AgencyHealthEmbed(**(await embedded_health(agency.id, agency.stats_reset_at)))
    return resp
