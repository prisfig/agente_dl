export const usdt = (v: number | null | undefined, dec = 2) =>
  v == null || Number.isNaN(v) ? "—" : v.toLocaleString("es-MX", { minimumFractionDigits: dec, maximumFractionDigits: dec });

/** Precio con decimales según su magnitud (DOGE ~0.06, SOL ~75, BTC ~60,000 USDT). */
export const precio = (v: number | null | undefined) =>
  usdt(v, v == null ? 2 : Math.abs(v) < 0.1 ? 5 : Math.abs(v) < 10 ? 4 : Math.abs(v) < 1000 ? 2 : 0);

export const pct = (v: number | null | undefined, dec = 2, signo = true) =>
  v == null || Number.isNaN(v) ? "—" : `${signo && v > 0 ? "+" : ""}${(v * 100).toFixed(dec)} %`;

export const num = (v: number | null | undefined, dec = 2) => (v == null || Number.isNaN(v) ? "—" : v.toFixed(dec));

export const horaLocal = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" }) : "—";

export const hace = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 5) return "ahora";
  if (s < 60) return `hace ${Math.round(s)} s`;
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${(s / 3600).toFixed(1)} h`;
  return `hace ${(s / 86400).toFixed(1)} d`;
};

export const duracion = (seg: number) => {
  const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
};
