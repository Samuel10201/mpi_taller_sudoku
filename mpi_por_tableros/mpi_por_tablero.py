"""Resuelve los tableros de seeds.txt repartiendo los IDs entre procesos MPI."""

import argparse
import sys
from pathlib import Path

from mpi4py import MPI

# Los archivos de apoyo viven en la carpeta superior (/app dentro del contenedor).
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from baseline_secuencial import leer_seeds  
from sudoku import resolver_con_tiempo  

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()

def por_tableros(seeds):
    """El 0 reparte los tableros y reúne los resultados; los demás resuelven su porción.

    En el 0 devuelve una lista con los resultados de cada trabajador (ordenada por rank);
    los trabajadores devuelven None. Solo el 0 necesita seeds.
    """
    if rank == 0:
        cociente, procesos_extra = divmod(len(seeds), size-1)
        fin = 0
        for i in range(size-1):
            if i < procesos_extra:
                ids = list(seeds.keys())[fin:fin+cociente+1]
                fin += cociente+1
            else:
                ids = list(seeds.keys())[fin:fin+cociente]
                fin += cociente
            porcion = {k: seeds[k] for k in ids}
            comm.send(porcion, dest=i+1)

        resultados = []
        for i in range(size-1):
            resultados.append(comm.recv(source=i+1))
        return resultados
    else:
        porcion = comm.recv(source=0)
        resultados_locales = []
        for id_tablero, tablero in porcion.items():
            resuelto, segundos = resolver_con_tiempo(tablero)
            resultados_locales.append((id_tablero, resuelto, segundos))
        comm.send(resultados_locales, dest=0)


def informar(seeds, resultados, total):
    """Imprime el estado de cada ID, la carga por proceso y el tiempo total de pared."""
    por_id = {}
    for trabajador, lista in enumerate(resultados, start=1):
        for id_tablero, resuelto, segundos in lista:
            por_id[id_tablero] = (resuelto, segundos, trabajador)

    for id_tablero in seeds:
        if id_tablero in por_id:
            resuelto, segundos, trabajador = por_id[id_tablero]
            estado = "Resuelto" if resuelto else "Sin solución"
            print(f"ID {id_tablero}: {estado} ({segundos:.6f} s, proceso {trabajador})")

    print("\nCarga por proceso (suma de los tiempos de búsqueda de sus tableros):")
    for trabajador, lista in enumerate(resultados, start=1):
        suma = sum(segundos for _, _, segundos in lista)
        print(f"  proceso {trabajador}: {len(lista)} tableros, {suma:.6f} s")

    faltan = [id_tablero for id_tablero in seeds if id_tablero not in por_id]
    print(f"\nIDs procesados: {len(por_id)} de {len(seeds)}")
    if faltan:
        print(f"FALTAN: {', '.join(faltan)}")
    print(f"Tiempo total (pared): {total:.6f} segundos")


def main():
    parser = argparse.ArgumentParser(description="Sudoku por tableros con MPI.")
    parser.add_argument("--archivo", type=Path, default=RAIZ / "seeds.txt",
                        help="archivo de seeds (por defecto: seeds.txt de la carpeta superior)")
    parser.add_argument("--all", action="store_true",
                        help="resolver todos los tableros (esta versión siempre lo hace)")
    args = parser.parse_args()

    if size < 2:
        if rank == 0:
            print("Hacen falta al menos 2 procesos: uno coordina y el resto resuelve (-n 2 o más).")
        sys.exit(1)

    seeds = None
    if rank == 0:
        try:
            seeds = leer_seeds(args.archivo)
        except OSError as error:
            print(f"No se pudo leer {args.archivo}: {error}")
            comm.Abort(1)

    inicio = MPI.Wtime()  # el tiempo de pared empieza al repartir, no al leer el archivo
    resultados = por_tableros(seeds)
    total = MPI.Wtime() - inicio

    if rank == 0:
        informar(seeds, resultados, total)


if __name__ == "__main__":
    main()
