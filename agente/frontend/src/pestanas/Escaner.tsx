import { useConsulta } from "../api";
import { Sparkline } from "../componentes/Graficas";
import { MensajeError, Tarjeta } from "../componentes/Ui";
import { horaLocal, pct, usdt } from "../formato";

interface Par {
  simbolo: string; operable: boolean; cierre?: number; variacion_1d?: number; sma20?: number; cierre_sobre_sma20?: boolean;
  dist_sma20?: number; vol20?: number; ultima_vela?: string; velas?: number; antiguedad_h?: number; latencia_ms?: number;
  cierres?: number[]; error?: string;
}

export default function Escaner() {
  const { datos, error, cargando, recargar } = useConsulta<{ generado_utc: string; nota: string; pares: Par[] }>("/api/escaner", 300_000);
  if (error) return <MensajeError mensaje={error} />;
  if (!datos) return <div className="tenue">Escaneando pares en MEXC…</div>;
  const sobre = datos.pares.filter((p) => p.cierre_sobre_sma20).length;
  return (
    <>
      <div className="aviso azul">{datos.nota} El filtro de tendencia (cierre &gt; SMA20) se muestra solo como contexto de mercado.</div>
      <Tarjeta titulo="Feeds e integridad · MEXC spot 1d" extra={<span className="chip">{sobre}/{datos.pares.length} sobre SMA20 · actualizado {horaLocal(datos.generado_utc)}
        <button className="boton" style={{ padding: "1px 8px" }} disabled={cargando} onClick={recargar}>⟳</button></span>}>
        <table className="tabla">
          <thead><tr><th>Símbolo</th><th>Uso</th><th className="der">Cierre</th><th className="der">Var. 1d</th><th>Tendencia</th>
            <th className="der">Dist. SMA20</th><th className="der">Vol. 20d</th><th>30 días</th><th>Última vela</th><th className="der">Antigüedad</th><th className="der">Velas</th><th className="der">Latencia</th></tr></thead>
          <tbody>
            {datos.pares.map((p) => p.error ? (
              <tr key={p.simbolo}><td className="mono">{p.simbolo}</td><td colSpan={11} className="negativo">{p.error}</td></tr>
            ) : (
              <tr key={p.simbolo}>
                <td className="mono"><b>{p.simbolo}</b></td>
                <td>{p.operable ? <span className="chip verde">operado por el agente</span> : <span className="chip">solo contexto</span>}</td>
                <td className="der mono">{usdt(p.cierre, p.cierre! < 10 ? 4 : 2)}</td>
                <td className={`der mono ${(p.variacion_1d ?? 0) >= 0 ? "positivo" : "negativo"}`}>{pct(p.variacion_1d)}</td>
                <td>{p.cierre_sobre_sma20 ? <span className="accion COMPRAR">sobre SMA20</span> : <span className="accion VENDER">bajo SMA20</span>}</td>
                <td className="der mono">{pct(p.dist_sma20)}</td>
                <td className="der mono">{pct(p.vol20, 2, false)}</td>
                <td><Sparkline valores={p.cierres ?? []} color={p.cierre_sobre_sma20 ? "var(--verde)" : "var(--rojo)"} /></td>
                <td className="mono">{p.ultima_vela}</td>
                <td className={`der mono ${(p.antiguedad_h ?? 0) > 26 ? "negativo" : ""}`}>{p.antiguedad_h} h</td>
                <td className="der mono">{p.velas}</td>
                <td className="der mono">{p.latencia_ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Tarjeta>
    </>
  );
}
