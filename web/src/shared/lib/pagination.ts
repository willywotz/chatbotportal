/**
 * Build a windowed page list for pagination controls: always shows the first
 * and last page, the current page with one neighbor on each side, and an
 * "ellipsis" marker wherever pages are skipped.
 */
export function getPaginationRange(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 1) return [1];

  const neighbors = 1;
  const shown = new Set<number>([1, total]);
  for (let page = current - neighbors; page <= current + neighbors; page++) {
    if (page >= 1 && page <= total) shown.add(page);
  }

  const items: (number | "ellipsis")[] = [];
  let prev = 0;
  for (const page of [...shown].sort((a, b) => a - b)) {
    // Collapse a run of hidden pages into an ellipsis, but render a lone gap.
    if (page - prev === 2) items.push(prev + 1);
    else if (page - prev > 2) items.push("ellipsis");
    items.push(page);
    prev = page;
  }
  return items;
}
