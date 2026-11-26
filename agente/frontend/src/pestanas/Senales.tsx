/** v2.0 · Laboratorio de señales: qué dice hoy el modelo de cada activo y qué avisos (correo) se enviaron.
 *  Sin saldos: el laboratorio no compra. Las compras son manuales y opcionales, en MEXC, a criterio del usuario. */
import { useState } from "react";
import { enviar, useConsulta } from "../api";
import { Acc, EstadoChip, Kpi, MensajeError, Tarjeta } from "../componentes/Ui";
import { hace, horaLocal, pct } from "../formato";

interface Alerta { tipo: string; estado: string; ts_utc: string }
interface FilaSenal {
  simbolo: string; estado: string; estrategia: string; delta: number; decimales: number;
  fecha_vela?: string; cierre?: number; pronostico?: number; senal?: string; cierre_sobre_sma20?: boolean; dist_sma20?: number;
  accion?: string; motivos?: string[]; senal_activa?: boolean; precio_entrada?: number | null; stop?: number | null; alerta?: Alerta | null;
}
interface EstadoAvisos { estado: string; canal?: string; proveedor?: string; destino?: string | null; avisar_ventas?: boolean; disparador?: string;
  formato?: string; secretos_requeridos?: string[] }
interface RespSenales { senales: FilaSenal[]; avisos: EstadoAvisos; proximo_ciclo_utc: string }
interface FilaAlerta { simbolo: string; fecha_vela: string; tipo: string; estado: string; intentos: number; detalle: string | null; ts_utc: string; texto: string }

const p = (v: number | null | undefined, dec: number) =>
  v == null ? "—" : v.toLocaleString("es-MX", { minimumFractionDigits: dec, maximumFractionDigits: dec });

const CLASE_ESTADO: Record<string, string> = { enviada: "verde", fallida: "rojo", sin_configurar: "ambar", deshabilitado: "", activo: "verde" };
const TEXTO_ESTADO: Record<string, string> = {
  activo: "activas", sin_configurar: "sin configurar", deshabilitado: "deshabilitadas", enviada: "enviada", fallida: "falló",
};

function ChipAlerta({ a }: { a?: Alerta | null }) {
  if (!a) return <span className="tenue">—</span>;
  return <span className={`chip ${CLASE_ESTADO[a.estado] ?? ""}`} title={a.ts_utc}>{a.tipo} · {TEXTO_ESTADO[a.estado] ?? a.estado}</span>;
}

export default function Senales() {
  const s = useConsulta<RespSenales>("/api/senales", 15_000);
  const h = useConsulta<{ alertas: FilaAlerta[] }>("/api/notificaciones?limite=50", 30_000);
  const [ocupado, setOcupado] = useState(false);
  const [mensaje, setMensaje] = useState<{ texto: string; tipo: "azul" | "rojo" } | null>(null);

  const probar = async () => {
    setOcupado(true);
    try {
      const r = await enviar<{ enviado: boolean; detalle: string }>("/api/notificaciones/prueba");
      setMensaje(r.enviado ? { texto: `Aviso de prueba enviado. Revisa tu ${canal}.`, tipo: "azul" }
        : { texto: `No se pudo enviar: ${r.detalle}`, tipo: "rojo" });
    } catch (e) {
      setMensaje({ texto: (e as Error).message, tipo: "rojo" });
    } finally {
      setOcupado(false);
    }
  };

  const filas = s.datos?.senales ?? [];
  const wa = s.datos?.avisos;
  const canal = wa?.canal === "correo" || !wa?.canal ? "correo" : "WhatsApp";
  const compras = filas.filter((f) => f.accion === "COMPRAR");
  const ventas = filas.filter((f) => f.accion === "VENDER");
  const activas = filas.filter((f) => f.senal_activa);
  const velas = filas.map((f) => f.fecha_vela).filter(Boolean).sort();
  const ultimaVela = velas[velas.length - 1];

  return (
    <>
      <MensajeError mensaje={s.error} />
      <div className="aviso azul">
        <b>Laboratorio de señales.</b> El sistema no compra ni maneja saldos: cada día analiza los {filas.length || 15} pares de MEXC
        y, cuando el modelo da señal de compra (o de venta) y pasa los controles de riesgo, te avisa por {canal}.
        La compra es manual y opcional, en MEXC. La simulación interna se conserva solo para evaluar la estrategia en el informe.
      </div>

      <div className="rejilla r4">
        <Kpi valor={<span className={compras.length ? "positivo" : ""}>{compras.length}</span>} etiqueta="Señales de compra hoy"
          sub={compras.length ? compras.map((f) => f.simbolo.replace("USDT", "")).join(", ") : `vela ${ultimaVela ?? "—"}`} />
        <Kpi valor={ventas.length} etiqueta="Señales de venta hoy" sub={ventas.length ? ventas.map((f) => f.simbolo.replace("USDT", "")).join(", ") : "ninguna"} />
        <Kpi valor={activas.length} etiqueta="Señales activas" sub="compra avisada y aún sin señal de salida" />
        <Kpi valor={<span className={`chip ${CLASE_ESTADO[wa?.estado ?? ""] ?? ""}`}>{TEXTO_ESTADO[wa?.estado ?? ""] ?? "—"}</span>}
          etiqueta={`Avisos por ${canal}`} sub={wa?.destino ? `a ${wa.destino}` : `faltan los datos de ${canal} en .env`} />
      </div>

      <Tarjeta titulo={`Avisos por ${canal}`} estilo={{ marginTop: 14 }} extra={
        <button className="boton azul" disabled={ocupado || wa?.estado !== "activo"} onClick={probar}>Enviar aviso de prueba</button>}>
        <div className="chico">
          Proveedor: {wa?.proveedor ?? "—"}{wa?.formato ? ` · formato: ${wa.formato}` : ""} · disparador: {wa?.disparador ?? "estrategia del modelo tras el motor de riesgo"}
          {wa?.avisar_ventas ? " · también avisa las señales de venta" : ""} · próximo análisis: <span className="mono">{horaLocal(s.datos?.proximo_ciclo_utc)}</span>
        </div>
        {wa?.estado === "sin_configurar" && <div className="aviso" style={{ marginTop: 10, marginBottom: 0 }}>
          Falta configurar los avisos: escribe <span className="mono">{(wa.secretos_requeridos ?? []).join(", ")}</span> en
          {" "}<span className="mono">agente/.env</span> (instrucciones en <span className="mono">agente/README.md</span>) y reinicia el backend.</div>}
        {mensaje && <div className={`aviso ${mensaje.tipo}`} style={{ marginTop: 10, marginBottom: 0 }}>{mensaje.texto}</div>}
      </Tarjeta>

      <div className="seccion">Señal del modelo por activo · último análisis</div>
      <Tarjeta>
        <table className="tabla">
          <thead><tr><th>Activo</th><th>Estado</th><th>Vela</th><th className="der">Cierre</th><th className="der">Pronóstico</th><th className="der">δ</th>
            <th>Tendencia</th><th>Acción de hoy</th><th>Entrada de la señal activa</th><th className="der">Stop sugerido</th><th>Aviso</th></tr></thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.simbolo} className={f.accion === "COMPRAR" ? "senal-compra" : ""}>
                <td className="mono"><b>{f.simbolo}</b> <span className="tenue chico">{f.estrategia}</span></td>
                <td><EstadoChip estado={f.estado} /></td>
                <td className="mono">{f.fecha_vela ?? <span className="tenue">sin análisis</span>}</td>
                <td className="der mono">{p(f.cierre, f.decimales)}</td>
                <td className={`der mono ${f.pronostico != null && f.pronostico > f.delta ? "positivo" : ""}`}>{pct(f.pronostico, 3)}</td>
                <td className="der mono tenue">{pct(f.delta, 3, false)}</td>
                <td className="chico">{f.cierre_sobre_sma20 == null ? "—" : f.cierre_sobre_sma20 ? "sobre SMA20" : `bajo SMA20 (${pct(f.dist_sma20, 1)})`}</td>
                <td>{f.accion ? <Acc a={f.accion} /> : <span className="tenue">—</span>}</td>
                <td className="mono chico">{f.senal_activa ? p(f.precio_entrada, f.decimales) : <span className="tenue">—</span>}</td>
                <td className="der mono">{f.senal_activa ? p(f.stop, f.decimales) : <span className="tenue">—</span>}</td>
                <td><ChipAlerta a={f.alerta} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="tenue chico" style={{ marginTop: 8 }}>
          COMPRAR = el modelo supera su umbral δ (y, en la estrategia D, el cierre está sobre la SMA20) y el riesgo lo permite. Una señal activa sigue
          hasta que el modelo o el stop móvil indiquen salida; entonces llega el aviso de venta. El LLM no dispara avisos.
        </div>
      </Tarjeta>

      <div className="seccion">Historial de avisos</div>
      <Tarjeta>
        <MensajeError mensaje={h.error} />
        {(h.datos?.alertas ?? []).length ? (
          <table className="tabla">
            <thead><tr><th>Enviado</th><th>Activo</th><th>Vela</th><th>Tipo</th><th>Estado</th><th className="der">Intentos</th><th>Detalle</th></tr></thead>
            <tbody>
              {h.datos!.alertas.map((a) => (
                <tr key={`${a.simbolo}-${a.fecha_vela}-${a.tipo}`} title={a.texto}>
                  <td className="mono chico">{hace(a.ts_utc)}</td><td className="mono">{a.simbolo}</td><td className="mono">{a.fecha_vela}</td>
                  <td>{a.tipo}</td><td><span className={`chip ${CLASE_ESTADO[a.estado] ?? ""}`}>{TEXTO_ESTADO[a.estado] ?? a.estado}</span></td>
                  <td className="der mono">{a.intentos}</td><td className="chico tenue">{a.detalle ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="tenue">Todavía no hay avisos. Llegarán después del análisis diario (cierre de 00:00 UTC + 5 min) cuando algún modelo dé señal.</div>}
      </Tarjeta>
    </>
  );
}
