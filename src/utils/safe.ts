export function truncateText(value: string, max = 3500): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max)}\n\n…`;
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
