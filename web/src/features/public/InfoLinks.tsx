import { Link } from 'react-router-dom';
import { infoSections } from '@/features/public/infoContent';

export function InfoLinks() {
  return (
    <div className="flex gap-4 text-xs text-muted-foreground">
      {infoSections.map((s) => (
        <Link key={s.key} to={s.path} className="hover:text-foreground transition-colors">
          {s.title}
        </Link>
      ))}
    </div>
  );
}
