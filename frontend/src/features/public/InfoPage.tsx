import { Link, useLocation, Navigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { infoSections } from '@/features/public/infoContent';

export default function InfoPage() {
  const { pathname } = useLocation();
  const section = infoSections.find((s) => s.path === pathname);

  if (!section) return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b border-border bg-card/80 backdrop-blur-sm px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <Link to="/" className="flex items-center gap-2.5 text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="h-4 w-4" />
          <span className="font-semibold text-foreground">Agentic AI Chatbot</span>
        </Link>
        <a href="/chat" className="text-xs text-primary hover:underline flex items-center gap-1 font-medium">
          เข้าสู่ระบบ <ArrowRight className="w-3 h-3" />
        </a>
      </header>

      <main className="flex-1 px-6 py-10">
        <article className="max-w-2xl mx-auto">
          <nav className="mb-8 flex flex-wrap gap-4 border-b border-border pb-6 text-xs text-muted-foreground">
            {infoSections.map((s) => (
              <Link
                key={s.key}
                to={s.path}
                className={
                  s.path === pathname
                    ? 'text-foreground font-medium'
                    : 'hover:text-foreground transition-colors'
                }
              >
                {s.title}
              </Link>
            ))}
            <Link to="/" className="hover:text-foreground transition-colors">กลับหน้าหลัก</Link>
          </nav>

          <h1 className="text-2xl text-foreground mb-1">{section.title}</h1>
          <p className="text-xs text-muted-foreground mb-6">{section.updated}</p>

          <p className="text-sm md:text-base text-foreground/90 leading-relaxed whitespace-pre-line mb-8">
            {section.intro}
          </p>

          <div className="space-y-8">
            {section.blocks.map((block, i) => (
              <section key={i}>
                {block.heading && (
                  <h2 className="text-base text-foreground mb-2">{block.heading}</h2>
                )}
                {block.paragraphs?.map((p, j) => (
                  <p key={j} className="text-sm md:text-base text-muted-foreground leading-relaxed whitespace-pre-line mb-2">
                    {p}
                  </p>
                ))}
                {block.bullets && (
                  <ul className="mt-2 list-disc pl-5 space-y-1.5 text-sm md:text-base text-muted-foreground leading-relaxed">
                    {block.bullets.map((b, j) => (
                      <li key={j}>{b}</li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>
        </article>
      </main>
    </div>
  );
}
