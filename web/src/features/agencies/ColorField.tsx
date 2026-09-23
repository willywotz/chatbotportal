import { Label } from "@/shared/components/ui/label";

import { toHexColor } from "./color";

interface Props {
  id: string;
  label?: string;
  value: string;
  onChange: (hex: string) => void;
}

/** Native `<input type="color">` seeded with a valid hex value, converting any legacy hsl(). */
export function ColorField({ id, label = "สี", value, onChange }: Props) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <input
        id={id}
        type="color"
        value={toHexColor(value)}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-md border border-input bg-transparent p-1 cursor-pointer"
      />
    </div>
  );
}
