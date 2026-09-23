import { cn } from "@/shared/lib/utils";

const IMAGE_PREFIXES = ["/api/", "/uploads/", "http", "data:"];

function isImageLogo(logo: string): boolean {
  return IMAGE_PREFIXES.some((prefix) => logo.startsWith(prefix));
}

interface Props {
  logo: string | null | undefined;
  alt: string;
  className?: string;
}

/** Renders an agency's `logo`: an `<img>` for an uploaded image path/URL, else the emoji text. */
export function AgencyLogo({ logo, alt, className }: Props) {
  if (!logo) return null;
  if (isImageLogo(logo)) {
    return <img src={logo} alt={alt} className={cn("object-cover", className)} />;
  }
  return <span className={className}>{logo}</span>;
}
