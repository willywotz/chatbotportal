/** Matches the `---` horizontal rule OneChat v5 puts between summary and sections. */
const DIVIDER = /\n-{3,}\n/;

/**
 * Returns the section body of a v5 `answer`, with the leading executive summary
 * (and its reference list) removed.
 *
 * v5 composes `answer` as summary → reference list → `---` → sections. The UI
 * renders the summary in its own card, so rendering the whole string as well
 * would show it twice. Splitting on the FIRST divider after the summary keeps
 * any `---` inside raw agency content intact.
 *
 * Never drops agency content: with no summary, a non-matching summary, or no
 * divider, it returns everything that is not the summary itself.
 */
export function stripSummaryPrefix(content: string, summary?: string | null): string {
  if (!summary) return content;
  if (!content.startsWith(summary)) return content;

  const rest = content.slice(summary.length);
  const match = rest.match(DIVIDER);
  if (!match || match.index === undefined) return rest.trim();

  return rest.slice(match.index + match[0].length).trim();
}
