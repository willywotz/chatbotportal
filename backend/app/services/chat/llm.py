import logging

from app.repositories import message as message_repo

logger = logging.getLogger(__name__)


async def classify_message_category(message_id: str, query: str, answer: str) -> None:
    content = f"""\
คุณเป็นโมเดลภาษา LLM ที่เชี่ยวชาญด้านการวิเคราะห์ข้อความและการจัดหมวดหมู่คำถามในบริบทของการให้บริการข้อมูลภาครัฐไทย
โปรดวิเคราะห์คำถามของผู้ใช้และระบุหมวดหมู่ที่ตรงที่สุด 1 หมวด จากนี้: สอบถามข้อมูล | ตรวจสอบสถานะ | ขั้นตอนดำเนินการ | กฎหมาย/ระเบียบ
ตอบเป็นข้อความที่มีเพียงหมวดหมู่ที่วิเคราะห์ได้เท่านั้น เช่น:
ขั้นตอนดำเนินการ

ถ้าคำถามไม่ชัดเจนหรือไม่สามารถจัดหมวดหมู่ได้ ให้ตอบว่า "ไม่สามารถจัดหมวดหมู่ได้"

คำถาม: {query}

คำตอบ: {answer}
"""
    from app.services.llm import LlmError, Purpose, chat
    try:
        res = await chat(purpose=Purpose.CLASSIFICATION, messages=[{"role": "user", "content": content}])
        await message_repo.set_category(message_id, res.content)
    except (LlmError, Exception) as e:
        logger.error("Error classifying message category: %s", e)
