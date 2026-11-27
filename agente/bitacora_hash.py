"""v2.3 · Bitácora con hash encadenado (solo biblioteca estándar).

Encadena con SHA-256 cada fila de la bitácora exportada (`registros/ciclos.csv`, `decisiones.csv`, `ordenes.csv` y `eventos.csv`):
    h_0 = SHA-256("laboratorio-dl"),   h_i = SHA-256(h_{i-1} + fila_i en JSON canónico)
Si alguien cambia, borra o reordena una sola fila, todos los hashes posteriores cambian y la verificación falla.

    python agente/bitacora_hash.py generar      # escribe registros/cadena_hash.csv y registros/cadena_hash_final.txt
    python agente/bitacora_hash.py verificar    # recalcula y compara; termina con código 1 si algo no coincide

Se corre después de `exportar_registros.py`. No toca las bases SQLite ni el agente.
"""
import csv
import hashlib
import json
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(RAIZ, "registros")
TABLAS = ("ciclos", "decisiones", "ordenes", "eventos")
SEMILLA = hashlib.sha256(b"laboratorio-dl").hexdigest()
csv.field_size_limit(10_000_000)


def filas():
    for t in TABLAS:
        with open(os.path.join(REG, f"{t}.csv"), newline="", encoding="utf-8") as f:
            for i, fila in enumerate(csv.DictReader(f)):
                yield t, i, fila


def cadena():
    h = SEMILLA
    for t, i, fila in filas():
        h = hashlib.sha256((h + json.dumps(fila, ensure_ascii=False, sort_keys=True)).encode("utf-8")).hexdigest()
        yield t, i, fila.get("simbolo", ""), fila.get("id", ""), h


def generar():
    n, h = 0, SEMILLA
    with open(os.path.join(REG, "cadena_hash.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["n", "tabla", "fila", "simbolo", "id", "hash"])
        for n, (t, i, s, id_, h) in enumerate(cadena(), 1):
            w.writerow([n, t, i, s, id_, h])
    with open(os.path.join(REG, "cadena_hash_final.txt"), "w", encoding="utf-8") as f:
        f.write(f"{h}\n{n} filas encadenadas ({', '.join(TABLAS)})\n")
    print(f"{n} filas encadenadas. Hash final: {h}")


def verificar():
    with open(os.path.join(REG, "cadena_hash.csv"), newline="", encoding="utf-8") as f:
        guardada = list(csv.DictReader(f))
    calculada = list(cadena())
    if len(guardada) != len(calculada):
        print(f"FALLA: la cadena guardada tiene {len(guardada)} filas y la bitácora {len(calculada)}.")
        return 1
    for g, (t, i, _, _, h) in zip(guardada, calculada):
        if g["hash"] != h:
            print(f"FALLA en {t}.csv, fila {i + 1}: la bitácora fue modificada desde ahí.")
            return 1
    print(f"OK: {len(calculada)} filas verificadas. Hash final: {calculada[-1][4]}")
    return 0


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "verificar"
    sys.exit(generar() if accion == "generar" else verificar())
