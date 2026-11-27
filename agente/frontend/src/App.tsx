import { useEffect, useState } from "react";
import { activoSel, ErrorApi, llamar, registrarNoAutorizado, sesion, useConsulta } from "./api";
import { EstadoChip } from "./componentes/Ui";
import { hace } from "./formato";
import Auditoria from "./pestanas/Auditoria";
import Escaner from "./pestanas/Escaner";
import Estrategia from "./pestanas/Estrategia";
import Mercado from "./pestanas/Mercado";
import Operaciones from "./pestanas/Operaciones";
import Senales from "./pestanas/Senales";
import Resumen from "./pestanas/Resumen";
import Sistema from "./pestanas/Sistema";
import { fijarEstrategia, senalDe, type Estado, type Evento, type ListaActivos, type Modo } from "./tipos";

// v2.0: laboratorio de señales (sin saldos). v2.1: la pestaña «PnL simulado» vuelve a mostrar operaciones y PnL de la
// simulación interna, marcados como evaluación de la señal (no son compras reales ni saldos de una cuenta).
const PESTANAS = ["Señales", "PnL simulado", "Resumen", "Mercado", "Escáner", "Estrategia", "Auditoría", "Sistema"] as const;
type Pestana = (typeof PESTANAS)[number];

function Acceso({ alEntrar }: { alEntrar: () => void }) {
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const entrar = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await llamar("/api/estado", {}, clave);
      sesion.guardar(clave);
      alEntrar();
    } catch (err) {
      setError(err instanceof ErrorApi && err.estado === 401 ? "Clave incorrecta." : (err as Error).message);
    }
  };
  return (
    <div className="acceso">
      <form className="tarjeta" onSubmit={entrar}>
        <div className="marca" style={{ fontSize: 18 }}>Laboratorio <span>DL</span> · señales</div>
        <p className="tenue chico">Laboratorio de señales: no compra ni maneja saldos; avisa por correo. Escribe la clave del backend (BACKEND_API_KEY de agente/.env).
          No se guarda en el código: solo en esta pestaña del navegador mientras esté abierta.</p>
        <input type="password" autoFocus value={clave} onChange={(e) => setClave(e.target.value)} placeholder="Clave de API" />
        {error && <div className="aviso rojo">{error}</div>}
        <button className="boton azul" style={{ width: "100%" }} disabled={!clave}>Entrar</button>
      </form>
    </div>
  );
}

export default function App() {
  const [dentro, setDentro] = useState(!!sesion.clave());
  const [pestana, setPestana] = useState<Pestana>("Señales");
  const [modo, setModo] = useState<Modo>("vivo");
  const [activo, setActivo] = useState(activoSel.obtener());

  useEffect(() => registrarNoAutorizado(() => { sesion.cerrar(); setDentro(false); }), []);

  const lista = useConsulta<ListaActivos>(dentro ? `/api/activos?modo=${modo}` : null, 15000);
  useEffect(() => {   // primera vez, o si el activo guardado ya no está configurado (p. ej. XRP, retirado en la v1.4): el principal
    if (lista.datos && (!activo || !lista.datos.activos.some((x) => x.simbolo === activo))) elegir(lista.datos.principal);
  }, [lista.datos]); // eslint-disable-line react-hooks/exhaustive-deps
  const elegir = (s: string) => { activoSel.fijar(s); setActivo(s); };

  const sufijo = activo ? `&simbolo=${activo}` : "";
  const estado = useConsulta<Estado>(dentro ? `/api/estado?modo=${modo}${sufijo}` : null, 5000);
  const errores = useConsulta<Evento[]>(dentro ? `/api/eventos?nivel=error&limite=50${sufijo}` : null, 15000);

  if (!dentro) return <Acceso alEntrar={() => setDentro(true)} />;

  const e = estado.datos && (!activo || estado.datos.activo === activo) ? estado.datos : null;
  if (e) fijarEstrategia(e.estrategia);
  const ciclo = e?.ultimo_ciclo;
  const errores24h = (errores.datos ?? []).filter((x) => Date.now() - new Date(x.ts_utc).getTime() < 86_400_000).length;
  const insignias: Partial<Record<Pestana, React.ReactNode>> = {
    Resumen: ciclo ? <span className="insignia azul">{ciclo.fecha_vela.slice(5)}</span> : null,
    Mercado: ciclo ? <span className={`insignia ${senalDe(ciclo.observacion) === "comprar" ? "azul" : ""}`}>{senalDe(ciclo.observacion)}</span> : null,
    Auditoría: errores24h ? <span className="insignia rojo">{errores24h}</span> : null,
  };

  return (
    <>
      <header className="barra">
        <span className="marca">Laboratorio <span>DL</span></span>
        <span className="selector" title="Activo: cada uno tiene su propio modelo y control">
          {(lista.datos?.activos ?? []).map((a) => (
            <button key={a.simbolo} className={activo === a.simbolo ? "activo" : ""} onClick={() => elegir(a.simbolo)}>
              <span className={`punto-estado ${a.estado.estado}`} />{a.activo_base}
            </button>
          ))}
        </span>
        {e?.version && <span className="chip azul">v{e.version}</span>}
        <span className="chip violeta">LABORATORIO</span>
        <span className="chip rojo">sin órdenes · avisos por correo</span>
        <EstadoChip estado={e?.agente.estado} />
        {ciclo && <span className="chip">última vela <b className="mono">{ciclo.fecha_vela}</b> · {hace(ciclo.fin_utc)}</span>}
        <span className="separa" />
        <span className="selector">
          {(["vivo", "replay"] as Modo[]).map((m) => (
            <button key={m} className={modo === m ? "activo" : ""} onClick={() => setModo(m)}>{m === "vivo" ? "En vivo (MEXC)" : "Replay histórico"}</button>
          ))}
        </span>
        <span className={`chip ${estado.error ? "rojo" : "verde"}`}><span className="punto" />{estado.error ? "sin conexión" : "conectado"}</span>
      </header>
      <nav className="pestanas">
        {PESTANAS.map((p) => (
          <button key={p} className={`pestana ${pestana === p ? "activa" : ""}`} onClick={() => setPestana(p)}>{p}{insignias[p]}</button>
        ))}
      </nav>
      <main className="contenido" key={`${activo}-${modo}`}>
        {e?.demostracion && <div className="aviso rojo"><b>INSTANCIA DE DEMOSTRACIÓN — escenario "{e.demostracion.escenario}"</b>: {e.demostracion.descripcion}
          {" "}Usa una base de datos aparte; los ciclos en vivo no se tocan.</div>}
        {modo === "replay" && <div className="aviso azul">Modo <b>replay</b>: repetición de velas históricas de MEXC. Estos resultados se reportan separados de la conexión en vivo.</div>}
        {estado.error && <div className="aviso rojo">{estado.error}</div>}
        {pestana === "Resumen" && <Resumen estado={e} modo={modo} recargar={() => { estado.recargar(); lista.recargar(); }}
          activos={lista.datos} alElegir={elegir} />}
        {pestana === "Mercado" && <Mercado modo={modo} estado={e} />}
        {pestana === "Escáner" && <Escaner />}
        {pestana === "Señales" && <Senales estado={e} />}
        {pestana === "PnL simulado" && <Operaciones modo={modo} estado={e} />}
        {pestana === "Estrategia" && <Estrategia modo={modo} estado={e} />}
        {pestana === "Auditoría" && <Auditoria modo={modo} estado={e} />}
        {pestana === "Sistema" && <Sistema modo={modo} estado={e} alSalir={() => { sesion.cerrar(); setDentro(false); }} />}
      </main>
    </>
  );
}
