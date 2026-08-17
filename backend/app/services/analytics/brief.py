import logging
from datetime import timedelta

from tortoise.expressions import RawSQL
from tortoise.transactions import in_transaction

from app.config import settings
from app.models import Conversation, ExecutiveBrief, Message
from app.schemas.executive_summary import ExecutiveData, ExecutiveKPIs
from app.utils import now

logger = logging.getLogger(__name__)

# Shown on the executive page until a brief has been generated (GET never blocks on the LLM).
_BRIEF_PLACEHOLDER = "ยังไม่มีรายงานสรุปประจำสัปดาห์ กรุณารอการสร้างอัตโนมัติหรือกดสร้างใหม่"
# Stored as the brief content when the LLM call fails.
_BRIEF_FALLBACK = "ไม่สามารถสร้างสรุปประจำสัปดาห์ได้ในขณะนี้"


async def _generate_brief_content(prompt: str) -> tuple[str, str]:
    """Call the LLM for the brief. Returns (content, status) where status is 'ok' | 'error'."""
    from app.services.llm import Purpose, chat
    try:
        res = await chat(purpose=Purpose.BRIEF, messages=[{"role": "user", "content": prompt}])
        return res.content, "ok"
    except Exception as e:
        logger.error("Error generating weekly brief: %s", e)
        return _BRIEF_FALLBACK, "error"


async def regenerate_weekly_brief() -> ExecutiveBrief:
    """Compute metrics, generate the brief via the LLM, and persist it as a new row.

    Called by the daily scheduler job and the admin force-regenerate endpoint.
    """
    metrics = await _compute_executive_metrics()
    prompt = _build_brief_prompt(metrics)
    content, status = await _generate_brief_content(prompt)
    return await ExecutiveBrief.create(content=content, status=status)


async def _latest_brief() -> str:
    """Return the most recent stored brief, or a placeholder if none exists yet."""
    row = await ExecutiveBrief.all().order_by("-generated_at").first()
    return row.content if row else _BRIEF_PLACEHOLDER


async def _compute_executive_metrics() -> dict:
    """Compute the executive KPIs and monthly trend. Shared by the GET path and regen."""
    async with in_transaction() as conn:
        await conn.execute_query(f"SET TIME ZONE '{settings.TIMEZONE}';")

        # (now().month - 1) is 0 in January, which is an invalid month value.
        # Use modular arithmetic so January wraps to December (month 12).
        prev_month = (now().month - 2) % 12 + 1

        thisMonthQuestions = await Message.filter(role="user", created_at__month=now().month).count()
        lastMonthQuestions = await Message.filter(role="user", created_at__month=prev_month).count()
        thisYearQuestions = await Message.filter(role="user", created_at__year=now().year).count()
        lastYearQuestions = await Message.filter(role="user", created_at__year=now().year - 1).count()

        momGrowthQuestions = ((thisMonthQuestions - lastMonthQuestions) / lastMonthQuestions * 100) if lastMonthQuestions > 0 else thisMonthQuestions * 100.0
        yoyGrowthQuestions = ((thisYearQuestions - lastYearQuestions) / lastYearQuestions * 100) if lastYearQuestions > 0 else thisYearQuestions * 100.0

        thisMonthCitizens = await Conversation.filter(created_at__month=now().month).count()
        lastMonthCitizens = await Conversation.filter(created_at__month=prev_month).count()
        thisYearCitizens = await Conversation.filter(created_at__year=now().year).count()
        lastYearCitizens = await Conversation.filter(created_at__year=now().year - 1).count()

        momGrowthCitizens = ((thisMonthCitizens - lastMonthCitizens) / lastMonthCitizens * 100) if lastMonthCitizens > 0 else thisMonthCitizens * 100.0
        yoyGrowthCitizens = ((thisYearCitizens - lastYearCitizens) / lastYearCitizens * 100) if lastYearCitizens > 0 else thisYearCitizens * 100.0

        monthlyTrend = await Message \
            .annotate(month=RawSQL("TO_CHAR(created_at, 'YYYY-MM')")) \
            .filter(created_at__gte=now() - timedelta(days=365)) \
            .group_by("month") \
            .annotate(questions=RawSQL("SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END)")) \
            .annotate(rating_up=RawSQL("SUM(CASE WHEN rating = 'up' THEN 1 ELSE 0 END)")) \
            .annotate(rating_down=RawSQL("SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END)")) \
            .values("month", "questions", "rating_up", "rating_down")

        for index, entry in enumerate(monthlyTrend):
            satisfaction = (entry["rating_up"] / (entry["rating_up"] + entry["rating_down"]) * 100) if (entry["rating_up"] + entry["rating_down"]) > 0 else 0.0
            monthlyTrend[index]["satisfaction"] = round(satisfaction, 2)

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


async def get_executive_summary() -> ExecutiveData:
    m = await _compute_executive_metrics()
    weeklyBrief = await _latest_brief()

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
