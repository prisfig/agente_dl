export type Modo = "vivo" | "replay";
export type Accion = "COMPRAR" | "MANTENER" | "VENDER";

export interface EstadoAgente {
  estado: "corriendo" | "pausado" | "detenido";
  motivo: string;
  errores_consecutivos: number;
  actualizado_utc: string;
}

export interface Observacion {
  fecha_vela: string;
  cierre: number;
  rezagos: number[];
  sma20: number;
  cierre_sobre_sma20: boolean;
  dist_sma20: number;
  vol20: number;
  pronostico: number;
  delta: number;
  estrategia?: string;   // desde la v1.3
  senal?: string;        // desde la v1.3
  senal_d?: string;      // nombre anterior (ciclos de BTC v1.0–v1.2)
  antiguedad_horas?: number;
  modo: Modo;
}

export interface Ciclo {
  id: number;
  modo: Modo;
  fecha_vela: string;
  inicio_utc: string;
  fin_utc: string;
  observacion: Observacion;
  latencia_llm_s: number;
  latencia_total_s: number;
  modelo_llm: string;
  config_sha256: string;
}

export interface Cartera {
  nombre: string;
  efectivo: number;
  btc: number;
  precio_entrada: number | null;
  stop: number | null;
  patrimonio_previo: number | null;
  bloqueo_perdida: boolean;
  en_posicion: boolean;
  patrimonio: number;
}

export interface Decision {
  id?: number;
  fecha_vela?: string;
  cartera: string;
  propuesta: Accion;
  accion_final: Accion;
  aprobada: number | boolean;
  motivos: string[];
  justificacion: string;
  detalle_llm?: { crudo: string; latencia_s: number; intentos: number; herramientas: { herramienta: string; permitida: boolean }[]; avisos: string[] } | null;
  latencia_llm_s?: number;
}

export interface Estado {
  version: string;
  demostracion?: { escenario: string; descripcion: string } | null;
  agente: EstadoAgente;
  modo: Modo;
  activo: string;
  activo_base: string;
  estrategia: string;
  activos: string[];
  base_datos: string;
  ultimo_ciclo: Ciclo | null;
  decisiones: Decision[];
  carteras: Record<string, Cartera>;
  riesgo: { exposicion_maxima: number; perdida_diaria_maxima: number; stop_movil_k_vol: number; antiguedad_maxima_horas: number; nota: string };
  paper: { capital_inicial: number; costo_compra: number; costo_venta: number; deslizamiento: number; supuesto_ejecucion: string };
  reglas_par: { paso_cantidad: string; monto_minimo: string; fuente: string };
  proximo_ciclo_utc: string;
  modelo: { modelo: string; semillas: number[]; estrategia: string; regla_estrategia?: string; delta: number; neuronas?: number; parametros?: number;
    huellas_verificadas?: boolean; ultimo_objetivo_TE?: string | null; checkpoints: Record<string, string>; keras?: string };
  llm: { modelo: string; gateway: string };
  config_sha256: string;
  replay: { en_curso?: boolean; desde?: string; hasta?: string; procesados?: number; error?: { mensaje?: string } | null };
}

export interface Evento {
  id: number;
  ts_utc: string;
  modo: Modo | null;
  nivel: "info" | "aviso" | "error";
  tipo: string;
  mensaje: string;
  detalle: Record<string, unknown> | null;
}

export interface Orden {
  id: number;
  fecha_vela: string;
  cartera: string;
  lado: "COMPRAR" | "VENDER";
  estado: "ejecutada" | "rechazada";
  cantidad: number;
  precio: number;
  monto: number;
  costo: number;
  motivo: string;
  ts_utc: string;
}

export interface Vela {
  fecha: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  close_time: number;
}

export interface MetricasCartera {
  ciclos: number;
  patrimonio_final: number;
  rendimiento_neto: number;
  max_drawdown: number;
  operaciones: number;
  operaciones_cerradas: number;
  win_rate: number | null;
  acciones_rechazadas: number;
  ordenes_rechazadas: number;
  motivos_rechazo: Record<string, number>;
}

export interface Metricas {
  modo: Modo;
  periodo: { desde: string | null; hasta: string | null; ciclos: number };
  latencia_llm_s: { media: number | null; maxima: number | null };
  capital_inicial: number;
  carteras: Record<string, MetricasCartera>;
}

export interface ResumenActivo {
  simbolo: string;
  activo_base: string;
  estado: EstadoAgente;
  estrategia: string;
  regla_estrategia: string;
  neuronas: number;
  delta: number;
  ultima_vela: string | null;
  senal: string | null;
  pronostico: number | null;
  cierre: number | null;
  ciclos: number;
  carteras: Record<string, number>;
}

export interface ListaActivos { principal: string; capital_inicial: number; activos: ResumenActivo[] }

export const senalDe = (o: Pick<Observacion, "senal" | "senal_d">) => o.senal ?? o.senal_d ?? "";

export const REGLAS: Record<string, string> = {
  C: "pronóstico > δ (sin filtro de tendencia)",
  D: "pronóstico > δ y cierre > SMA20",
};

export const NOMBRES_CARTERA: Record<string, string> = {
  sin_llm: "Sin LLM · estrategia D",
  con_llm: "Con LLM · agente",
  comprar_y_mantener: "Comprar y mantener",
};

/** La cartera sin LLM sigue la estrategia del activo seleccionado (C o D). */
export function fijarEstrategia(estrategia: string) {
  NOMBRES_CARTERA.sin_llm = `Sin LLM · estrategia ${estrategia}`;
}

export const COLOR_CARTERA: Record<string, string> = {
  sin_llm: "var(--azul)",
  con_llm: "var(--violeta)",
  comprar_y_mantener: "var(--gris)",
};
