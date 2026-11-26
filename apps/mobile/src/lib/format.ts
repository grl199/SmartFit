export function clampPercent(value: number, target: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(target) || target <= 0) return 0;
  return Math.max(0, Math.min(100, (value / target) * 100));
}
export function formatKcal(value: number | null | undefined): string {
  const rounded = String(Math.round(value ?? 0));
  return rounded.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}
export function localDateISO(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return year + "-" + month + "-" + day;
}
export function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" }).format(new Date(value + "T12:00:00"));
}