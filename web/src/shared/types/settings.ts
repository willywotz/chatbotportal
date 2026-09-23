export type FieldType = "str" | "int" | "float" | "bool" | "list_str";

export interface SettingField {
  key: string;
  value: string;
  field_type: FieldType;
  group: string;
  is_secret: boolean;
  default_value: string;
}

export interface SettingsGroup {
  group: string;
  fields: SettingField[];
}

export interface SettingsResponse {
  groups: SettingsGroup[];
}

export interface SettingUpdate {
  key: string;
  value: string;
}