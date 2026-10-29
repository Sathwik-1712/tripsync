/** Rupees with Indian digit grouping: ₹1,50,000 (design.md, section 3). */
export function inr(n: number): string {
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

export function fmtDay(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

export function weekday(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short" });
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ");
}

/** Tag for a place. Every place of worship shares the "temple" kind, so name it from the place's name. */
export function kindLabel(kind: string, name: string): string {
  if (kind === "temple") {
    const n = name.toLowerCase();
    if (/church|cathedral|basilica|chapel/.test(n)) return "Church";
    if (/masjid|mosque|dargah/.test(n)) return "Mosque";
    if (/gurudwara|gurdwara|golden temple/.test(n)) return "Gurdwara";
    if (/monastery|gompa|stupa|pagoda/.test(n)) return "Monastery";
    if (/synagogue/.test(n)) return "Synagogue";
    if (/ashram/.test(n)) return "Ashram";
    if (/ghat/.test(n)) return "Ghat";
  }
  return capitalize(kind.replace(/_/g, " "));
}

/** Straight-line distance in km. */
export function haversineKm(a: [number, number], b: [number, number]): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const h = Math.sin(r(b[0] - a[0]) / 2) ** 2 + Math.cos(r(a[0])) * Math.cos(r(b[0])) * Math.sin(r(b[1] - a[1]) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

export function hm(minutes: number): string {
  const h = Math.floor(minutes / 60), m = Math.round(minutes % 60);
  return h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`;
}

export const hhmm = (iso: string | null | undefined) => (iso ? iso.slice(11, 16) : "");

export function mapsSearch(lat: number, lon: number): string {
  return `https://www.google.com/maps/search/?api=1&query=${lat.toFixed(5)},${lon.toFixed(5)}`;
}
