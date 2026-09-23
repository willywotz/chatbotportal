from pydantic import BaseModel


class SettingFieldOut(BaseModel):
    key: str
    value: str
    field_type: str
    group: str
    is_secret: bool
    default_value: str


class SettingsGroupOut(BaseModel):
    group: str
    fields: list[SettingFieldOut]


class SettingsResponse(BaseModel):
    groups: list[SettingsGroupOut]


class SettingUpdateIn(BaseModel):
    key: str
    value: str


class SettingsUpdateRequest(BaseModel):
    settings: list[SettingUpdateIn]