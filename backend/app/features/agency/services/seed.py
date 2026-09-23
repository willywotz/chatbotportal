"""Default-data seeding logic (government agencies).

Kept out of the router so the seed operations can be reused by app startup and a
future management command, and unit-tested directly.
"""

from app.core.db import AsyncSessionLocal
from app.features.agency.repositories import agency as agency_repo


DEFAULT_AGENCIES = [
    {
        "name": "สำนักงานคณะกรรมการอาหารและยา",
        "short_name": "อย.",
        "logo": "🏥",
        "connection_type": "MCP",
        "status": "active",
        "description": "ระบบตรวจสอบทะเบียนยา อาหาร เครื่องสำอาง และผลิตภัณฑ์สุขภาพ",
        "data_scope": ["ทะเบียนยา", "ทะเบียนอาหาร", "เครื่องสำอาง", "ผลิตภัณฑ์สุขภาพ", "การขออนุญาต"],
        "total_calls": 12450,
        "color": "#2e9e5d",
        "endpoint_url": "https://api.fda.moph.go.th/mcp",
    },
    {
        "name": "กรมสรรพากร",
        "short_name": "กรมสรรพากร",
        "logo": "💰",
        "connection_type": "API",
        "status": "active",
        "description": "ระบบสอบถามข้อมูลภาษี การยื่นแบบ และสิทธิประโยชน์ทางภาษี",
        "data_scope": ["ภาษีเงินได้บุคคลธรรมดา", "ภาษีนิติบุคคล", "ภาษีมูลค่าเพิ่ม", "การยื่นแบบ", "สิทธิลดหย่อน"],
        "total_calls": 18320,
        "color": "#226bc3",
        "endpoint_url": "https://api.rd.go.th/v1",
    },
    {
        "name": "กรมการปกครอง",
        "short_name": "กรมการปกครอง",
        "logo": "🏛️",
        "connection_type": "A2A",
        "status": "active",
        "description": "ระบบตรวจสอบข้อมูลทะเบียนราษฎร์ บัตรประชาชน และงานปกครอง",
        "data_scope": ["ทะเบียนราษฎร์", "บัตรประจำตัวประชาชน", "ทะเบียนบ้าน", "การเปลี่ยนชื่อ", "สถานะบุคคล"],
        "total_calls": 9870,
        "color": "#ee7c2b",
        "endpoint_url": "https://api.dopa.go.th/a2a",
    },
    {
        "name": "กรมที่ดิน",
        "short_name": "กรมที่ดิน",
        "logo": "🗺️",
        "connection_type": "MCP",
        "status": "active",
        "description": "ระบบสอบถามข้อมูลที่ดิน โฉนด การจดทะเบียนสิทธิและนิติกรรม",
        "data_scope": ["โฉนดที่ดิน", "การจดทะเบียน", "ราคาประเมิน", "การรังวัด", "สิทธิและนิติกรรม"],
        "total_calls": 7650,
        "color": "#9540bf",
        "endpoint_url": "https://api.dol.go.th/mcp",
    },
]

async def run_seed_agencies() -> dict:
    async with AsyncSessionLocal() as session, session.begin():
        existing = await agency_repo.count_all(session)
        if existing > 0:
            return {"status": "skipped", "message": f"{existing} agencies already exist"}

        created = []
        for data in DEFAULT_AGENCIES:
            await agency_repo.create(session, **data)
            created.append(data["name"])

    return {"status": "created", "message": f"{len(created)} agencies created", "agencies": created}
