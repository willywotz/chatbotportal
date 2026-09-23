import logging
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.conversation import Conversation, Message
from app.repositories import analytics as analytics_repo
from app.repositories import executive_brief as brief_repo
from app.schemas.executive_summary import ExecutiveData, ExecutiveKPIs
from app.utils import now

logger = logging.getLogger(__name__)

# Shown on the executive page until a brief has been generated (GET never blocks on the LLM).
_BRIEF_PLACEHOLDER = "ยังไม่มีรายงานสรุปประจำสัปดาห์ กรุณารอการสร้างอัตโนมัติหรือกดสร้างใหม่"
# Stored as the brief content when the LLM call fails.
_BRIEF_FALLBACK = "ไม่สามารถสร้างสรุปประจำสัปดาห์ได้ในขณะนี้"


async def _generate_brief_content(session: AsyncSession, prompt: str) -> tuple[str, str]:
    """Call the LLM for the brief. Returns (content, status) where status is 'ok' | 'error'."""
    from app.services.llm import Purpose, chat
    try:
        res = await chat(session, purpose=Purpose.BRIEF, messages=[{"role": "user", "content": prompt}])
        return res.content, "ok"
    except Exception as e:
        logger.error("Error generating weekly brief: %s", e)
        return _BRIEF_FALLBACK, "error"


async def regenerate_weekly_brief(session: AsyncSession):
    """Compute metrics, generate the brief via the LLM, and persist it as a new row.

    Called by the daily scheduler job and the admin force-regenerate endpoint.
    """
    metrics = await _compute_executive_metrics(session)
    prompt = _build_brief_prompt(metrics)
    content, status = await _generate_brief_content(session, prompt)
    return await brief_repo.create(session, content=content, status=status)


async def _latest_brief(session: AsyncSession) -> str:
    """Return the most recent stored brief, or a placeholder if none exists yet."""
    row = await brief_repo.latest(session)
    return row.content if row else _BRIEF_PLACEHOLDER


async def _count_by_calendar_part(session: AsyncSession, model, unit: str, value: int, *extra) -> int:
    """COUNT(*) WHERE EXTRACT(unit FROM created_at) = value, ignoring the other calendar part."""
    stmt = select(func.count()).select_from(model).where(func.extract(unit, model.created_at) == value, *extra)
    return await session.scalar(stmt)


async def _compute_executive_metrics(session: AsyncSession) -> dict:
    """Compute the executive KPIs and monthly trend. Shared by the GET path and regen."""
    await session.execute(text(f"SET LOCAL TIME ZONE '{settings.TIMEZONE}'"))

    # (now().month - 1) is 0 in January, which is an invalid month value.
    # Use modular arithmetic so January wraps to December (month 12).
    prev_month = (now().month - 2) % 12 + 1

    thisMonthQuestions = await _count_by_calendar_part(session, Message, "month", now().month, Message.role == "user")
    lastMonthQuestions = await _count_by_calendar_part(session, Message, "month", prev_month, Message.role == "user")
    thisYearQuestions = await _count_by_calendar_part(session, Message, "year", now().year, Message.role == "user")
    lastYearQuestions = await _count_by_calendar_part(session, Message, "year", now().year - 1, Message.role == "user")

    momGrowthQuestions = ((thisMonthQuestions - lastMonthQuestions) / lastMonthQuestions * 100) if lastMonthQuestions > 0 else thisMonthQuestions * 100.0
    yoyGrowthQuestions = ((thisYearQuestions - lastYearQuestions) / lastYearQuestions * 100) if lastYearQuestions > 0 else thisYearQuestions * 100.0

    thisMonthCitizens = await _count_by_calendar_part(session, Conversation, "month", now().month)
    lastMonthCitizens = await _count_by_calendar_part(session, Conversation, "month", prev_month)
    thisYearCitizens = await _count_by_calendar_part(session, Conversation, "year", now().year)
    lastYearCitizens = await _count_by_calendar_part(session, Conversation, "year", now().year - 1)

    momGrowthCitizens = ((thisMonthCitizens - lastMonthCitizens) / lastMonthCitizens * 100) if lastMonthCitizens > 0 else thisMonthCitizens * 100.0
    yoyGrowthCitizens = ((thisYearCitizens - lastYearCitizens) / lastYearCitizens * 100) if lastYearCitizens > 0 else thisYearCitizens * 100.0

    monthlyTrend = await analytics_repo.message_monthly_trend(session, since=now() - timedelta(days=365))
    for entry in monthlyTrend:
        up, down = entry["rating_up"], entry["rating_down"]
        satisfaction = (up / (up + down) * 100) if (up + down) > 0 else 0.0
        entry["satisfaction"] = round(satisfaction, 2)

    return {
        "thisMonthQuestions": thisMonthQuestions,
        "lastMonthQuestions": lastMonthQuestions,
        "thisYearQuestions": thisYearQuestions,
        "lastYearQuestions": lastYearQuestions,
        "momGrowthQuestions": momGrowthQuestions,
        "yoyGrowthQuestions": yoyGrowthQuestions,
        "thisMonthCitizens": thisMonthCitizens,
        "lastMonthCitizens": lastMonthCitizens,
        "thisYearCitizens": thisYearCitizens,
        "lastYearCitizens": lastYearCitizens,
        "momGrowthCitizens": momGrowthCitizens,
        "yoyGrowthCitizens": yoyGrowthCitizens,
        "monthlyTrend": monthlyTrend,
    }


def _build_brief_prompt(m: dict) -> str:
    return f"""
        คุณเป็นนักวิเคราะห์ข้อมูลให้ผู้บริหารระดับสูงของรัฐบาลไทย กรุณาสรุปข้อมูลการใช้งาน AI Portal ในสัปดาห์นี้เป็นภาษาไทย ความยาว 3-4 ย่อหน้า เน้น insights เชิงกลยุทธ์และข้อเสนอแนะเชิงนโยบาย
    ข้อมูล:
    - คำถามรวมเดือนนี้: {m['thisMonthQuestions']} (เพิ่มขึ้น {m['momGrowthQuestions']:.2f}% จากเดือนก่อน, เพิ่มขึ้น {m['yoyGrowthQuestions']:.2f}% จากปีก่อน)
    - ประชาชนที่ได้รับบริการเดือนนี้: {m['thisMonthCitizens']} คน (เพิ่มขึ้น {m['momGrowthCitizens']:.2f}% จากเดือนก่อน, เพิ่มขึ้น {m['yoyGrowthCitizens']:.2f}% จากปีก่อน)
    - แนวโน้มรายเดือน: {m['monthlyTrend']}
    โครงสร้าง:
    1. ภาพรวมและไฮไลท์สัปดาห์
    2. แนวโน้มที่น่าสนใจและสาเหตุที่เป็นไปได้
    3. ข้อเสนอแนะเชิงนโยบายสำหรับผู้บริหาร
    ใช้ภาษาทางการ กระชับ ชัดเจน มี emoji ประกอบเล็กน้อย"""


async def get_executive_summary(session: AsyncSession) -> ExecutiveData:
    m = await _compute_executive_metrics(session)
    weeklyBrief = await _latest_brief(session)

    return ExecutiveData(
        kpis=ExecutiveKPIs(
            totalQuestions=m["thisYearQuestions"],
            momGrowth=float(f"{m['momGrowthQuestions']:.2f}"),
            yoyGrowth=float(f"{m['yoyGrowthQuestions']:.2f}"),
            uniqueCitizens=0,
            totalHoursSaved=0.0,
            costSaved=0.0,
            healthScore=0.0,
            uptime=0.0,
            satisfaction=0.0,
            avgResponseTime=0.0,

            thisMonthQuestions=m["thisMonthQuestions"],
            lastMonthQuestions=m["lastMonthQuestions"],
            thisYearQuestions=m["thisYearQuestions"],
            lastYearQuestions=m["lastYearQuestions"],
            momGrowthQuestions=float(f"{m['momGrowthQuestions']:.2f}"),
            yoyGrowthQuestions=float(f"{m['yoyGrowthQuestions']:.2f}"),

            thisMonthCitizens=m["thisMonthCitizens"],
            lastMonthCitizens=m["lastMonthCitizens"],
            thisYearCitizens=m["thisYearCitizens"],
            lastYearCitizens=m["lastYearCitizens"],
            momGrowthCitizens=float(f"{m['momGrowthCitizens']:.2f}"),
            yoyGrowthCitizens=float(f"{m['yoyGrowthCitizens']:.2f}")
        ),
        agencyScorecard=[],
        monthlyTrend=m["monthlyTrend"],
        topIssues=[],
        weeklyBrief=weeklyBrief,
        generatedAt=now()
    )
