from typing import Literal

from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """Category of a Thai government-service question."""
    category: Literal[
        "สอบถามข้อมูล", "ตรวจสอบสถานะ", "ขั้นตอนดำเนินการ",
        "กฎหมาย/ระเบียบ", "ไม่สามารถจัดหมวดหมู่ได้",
    ] = Field(description="The single best-fit category.")


class JudgeResult(BaseModel):
    """Grade of an agency answer against expected topics."""
    score: float = Field(description="Quality score from 0.0 to 1.0.")
    reason: str = Field(default="", description="Short justification for the score.")


class SpecEndpoint(BaseModel):
    """One API endpoint found in a specification."""
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    path: str
    description: str


class SpecResponseField(BaseModel):
    """One common response field found across endpoints."""
    field: str = Field(description="Field name or dot path, e.g. data.items[].name.")
    type: str = Field(description="Data type: string, number, boolean, array, object, date.")
    description: str
    example: str | None = None


class SpecResult(BaseModel):
    """Structured API specification extracted from a document."""
    auth_method: Literal["api_key", "oauth2", "basic_auth", "none"]
    auth_header: str = Field(description="Auth header name, e.g. X-API-Key.")
    base_path: str = Field(description="Base path prefix, e.g. /api/v1.")
    request_format: Literal["json", "xml"]
    endpoints: list[SpecEndpoint]
    response_schema: list[SpecResponseField]


class PopularQuestionItem(BaseModel):
    """One synthesized popular question."""
    text: str
    agency_id: str | None = None
    score: float | None = None


class PopularQuestionsResult(BaseModel):
    """The set of synthesized popular questions."""
    questions: list[PopularQuestionItem]
