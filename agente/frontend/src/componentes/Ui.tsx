import { enviar } from "../api";
import { ReactNode, useState } from "react";
import type { Accion } from "../tipos";

export function Tarjeta({ titulo, extra, children, estilo }: { titulo?: ReactNode; extra?: ReactNode; children: ReactNode; estilo?: React.CSSProperties }) {
  return (
    <div className="tarjeta" style={estilo}>
      {titulo && <h3>{titulo}<span className="separa" />{extra}</h3>}
      {children}
    </div>
  );
}

export function Kpi({ valor, etiqueta, sub, clase }: { valor: ReactNode; etiqueta: ReactNode; sub?: ReactNode; clase?: string }) {
  return (
    <div className="tarjeta kpi">
      <div className={`valor ${clase ?? ""}`}>{valor}</div>
      <div className="etiqueta">{etiqueta}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export const Acc = ({ a }: { a: Accion | string }) => <span className={`accion ${a}`}>{a}</span>;

export function MensajeError({ mensaje }: { mensaje: string | null }) {
  return mensaje ? <div className="aviso rojo">{mensaje}</div> : null;
}

/** Botón con confirmación en línea (sin diálogos del navegador). */
export function BotonConfirmar({ texto, clase, pregunta, alConfirmar, deshabilitado }: {
  texto: string; clase?: string; pregunta: string; alConfirmar: () => void; deshabilitado?: boolean;
}) {
  const [confirmando, setConfirmando] = useState(false);
  if (confirmando)
    return (
      <span className="chip ambar" style={{ padding: "4px 6px 4px 12px" }}>
        {pregunta}
        <button className="boton rojo" style={{ padding: "3px 10px" }} onClick={() => { setConfirmando(false); alConfirmar(); }}>Sí</button>
        <button className="boton" style={{ padding: "3px 10px" }} onClick={() => setConfirmando(false)}>No</button>
      </span>
    );
  return <button className={`boton ${clase ?? ""}`} disabled={deshabilitado} onClick={() => setConfirmando(true)}>{texto}</button>;
}

export function EstadoChip({ estado }: { estado?: string }) {
  const clase = estado === "corriendo" ? "verde" : estado === "pausado" ? "ambar" : "rojo";
  return <span className={`chip ${clase}`}><span className="punto" />{estado ?? "—"}</span>;
}

/** v1.9: rearma con una sola acción todos los activos con el control de pérdida diaria activo. */
export function BotonRearmarTodos({ bloqueados, alTerminar }: { bloqueados?: string[]; alTerminar?: () => void }) {
  const [ocupado, setOcupado] = useState(false);
  const [mensaje, setMensaje] = useState<{ texto: string; tipo: "azul" | "rojo" } | null>(null);
  const n = bloqueados?.length;
  const ejecutar = async () => {
    setOcupado(true);
    try {
      const r = await enviar<{ rearmados: string[] }>("/api/riesgo/rearmar_todos");
      setMensaje(r.rearmados.length
        ? { texto: `Rearmados ${r.rearmados.length}: ${r.rearmados.join(", ")}. Quedó un evento de control en cada uno.`, tipo: "azul" }
        : { texto: "Ningún activo tenía el bloqueo activo: no se cambió nada.", tipo: "azul" });
    } catch (e) {
      setMensaje({ texto: (e as Error).message, tipo: "rojo" });
    } finally {
      setOcupado(false);
      alTerminar?.();
    }
  };
  return (
    <>
      <BotonConfirmar texto={`Rearmar todos los bloqueados${n != null ? ` (${n})` : ""}`} clase="ambar" deshabilitado={ocupado || n === 0}
        pregunta={`¿Quitar el bloqueo de compras por pérdida diaria${n ? ` en ${n} activos` : " en todos los activos bloqueados"}?`} alConfirmar={ejecutar} />
      {mensaje && <div className={`aviso ${mensaje.tipo}`} style={{ marginTop: 10, marginBottom: 0, width: "100%" }}>{mensaje.texto}</div>}
    </>
  );
}
