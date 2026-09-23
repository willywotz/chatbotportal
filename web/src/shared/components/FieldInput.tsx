import { Input } from "@/shared/components/ui/input";
import { PasswordInput } from "@/shared/components/ui/password-input";
import { Switch } from "@/shared/components/ui/switch";
import { Textarea } from "@/shared/components/ui/textarea";
import type { SettingField } from "@/shared/types/settings";

const MASK = "*****";

interface FieldInputProps {
  field: SettingField;
  value: string;
  onChange: (v: string) => void;
}

export function FieldInput({ field, value, onChange }: FieldInputProps) {
  if (field.is_secret) {
    return (
      <PasswordInput
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={MASK}
      />
    );
  }

  switch (field.field_type) {
    case "bool":
      return (
        <div className="flex items-center gap-2">
          <Switch
            checked={value === "true"}
            onCheckedChange={(checked) => onChange(checked ? "true" : "false")}
          />
          <span className="text-sm text-muted-foreground">{value}</span>
        </div>
      );
    case "int":
      return (
        <Input
          type="number"
          step="1"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "float":
      return (
        <Input
          type="number"
          step="0.01"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "list_str":
      return (
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={2}
          placeholder='["item1", "item2"]'
          className="font-mono text-xs"
        />
      );
    default:
      return (
        <Input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      );
  }
}
