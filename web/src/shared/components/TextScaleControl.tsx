import { Button } from "@/shared/components/ui/button";
import { useTextScale, type TextScale } from "@/shared/hooks/useTextScale";
import { cn } from "@/shared/lib/utils";

const OPTION: { value: TextScale; label: string; glyph: string }[] = [
  { value: "small", label: "ตัวอักษรเล็ก", glyph: "text-xs" },
  { value: "normal", label: "ตัวอักษรปกติ", glyph: "text-sm" },
  { value: "large", label: "ตัวอักษรใหญ่", glyph: "text-base" },
];

export function TextScaleControl() {
  const { scale, setScale } = useTextScale();

  return (
    <div role="group" aria-label="ปรับขนาดตัวอักษร" className="flex items-center">
      {OPTION.map((opt) => (
        <Button
          key={opt.value}
          type="button"
          variant="ghost"
          size="icon"
          aria-label={opt.label}
          aria-pressed={scale === opt.value}
          onClick={() => setScale(opt.value)}
          className={cn(
            "h-8 w-7 rounded-full font-semibold leading-none",
            opt.glyph,
            scale === opt.value ? "bg-primary/10 text-primary" : "text-muted-foreground",
          )}
        >
          A
        </Button>
      ))}
    </div>
  );
}
