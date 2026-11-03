"""Resuelve los tableros de seeds.txt uno después de otro, repartiendo las ramas de cada
tablero entre los procesos MPI (tableros en serie, ramas en paralelo)."""

import argparse
import sys
from collections import deque
from pathlib import Path

from mpi4py import MPI

# Los archivos de apoyo viven en la carpeta superior (/app dentro del contenedor).
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from baseline_secuencial import leer_seeds  
from sudoku import puede_colocar  

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()

TAG_TAREA = 1       # 0 -> trabajador: (ronda, tablero parcial); None = ya no hay más tableros
TAG_RESULTADO = 2   # trabajador -> 0: (resuelto, tablero resuelto o None)
TAG_PARAR = 3       # 0 -> trabajador: número de ronda cuya búsqueda hay que cancelar
PROFUNDIDAD = 4     # casillas vacías cuyas opciones válidas se fijan para crear las ramas (la mejor medida: ver bitacora\log.md)
PASOS_ENTRE_AVISOS = 1000  # cada cuántas casillas colocadas se consulta si hay aviso de parada


class Cancelado(Exception):
    """La búsqueda se interrumpe porque otro proceso ya halló la solución del tablero."""



def primera_vacia(tablero):
    """Devuelve (fila, columna) de la primera casilla vacía, o None si no hay."""
    for fila in range(9):
        for columna in range(9):
            if tablero[fila][columna] == 0:
                return fila, columna
    return None


def generar_ramas(tablero, profundidad):
    """Fija las opciones válidas de las primeras `profundidad` casillas vacías.

    Devuelve una lista de tableros parciales (copias): cada uno es una rama independiente.
    """
    ramas = []

    def fijar(actual, nivel):
        casilla = primera_vacia(actual)
        if nivel == profundidad or casilla is None:
            ramas.append(actual)
            return
        fila, columna = casilla
        for valor in range(1, 10):
            if puede_colocar(actual, fila, columna, valor):
                siguiente = [f[:] for f in actual]
                siguiente[fila][columna] = valor
                fijar(siguiente, nivel + 1)

    fijar([f[:] for f in tablero], 0)
    return ramas


def es_solucion_valida(tablero, original):
    """Comprueba filas, columnas y bloques completos y que respeta las casillas del original."""
    digitos = set(range(1, 10))

    # Cada fila debe tener exactamente los dígitos del 1 al 9.
    for fila in range(9):
        if set(tablero[fila]) != digitos:
            return False

    # Cada columna, igual.
    for columna in range(9):
        valores = set()
        for fila in range(9):
            valores.add(tablero[fila][columna])
        if valores != digitos:
            return False

    # Cada bloque de 3x3, igual. (inicio_fila, inicio_columna) es la esquina superior izquierda.
    for inicio_fila in (0, 3, 6):
        for inicio_columna in (0, 3, 6):
            valores = set()
            for f in range(3):
                for c in range(3):
                    valores.add(tablero[inicio_fila + f][inicio_columna + c])
            if valores != digitos:
                return False

    # Las casillas que venían con número en el original no pueden haber cambiado.
    for fila in range(9):
        for columna in range(9):
            if original[fila][columna] != 0 and original[fila][columna] != tablero[fila][columna]:
                return False

    return True


def resolver_tablero(tablero, ronda, profundidad):
    """Reparte las ramas de un tablero y espera hasta tenerlo resuelto y a todos libres.

    Devuelve (solucion o None, ramas generadas, ramas lanzadas). Las ramas se entregan a
    medida que los trabajadores se liberan; al hallar la solución se deja de repartir y se
    avisa a los ocupados. No se vuelve hasta recibir la respuesta de cada rama lanzada.
    """
    ramas = deque(generar_ramas(tablero, profundidad))
    total_ramas = len(ramas)
    libres = list(range(size - 1, 0, -1))
    ocupados = set()
    solucion = None
    lanzadas = 0

    while True:
        while libres and ramas and solucion is None:
            destino = libres.pop()
            comm.send((ronda, ramas.popleft()), dest=destino, tag=TAG_TAREA)
            ocupados.add(destino)
            lanzadas += 1
        if not ocupados:
            break

        estado = MPI.Status()
        resuelto, tablero_resuelto = comm.recv(source=MPI.ANY_SOURCE, tag=TAG_RESULTADO, status=estado)
        origen = estado.Get_source()
        ocupados.discard(origen)
        libres.append(origen)
        if resuelto and solucion is None:
            solucion = tablero_resuelto
            for otro in ocupados:
                comm.send(ronda, dest=otro, tag=TAG_PARAR)

    return solucion, total_ramas, lanzadas


def coordinador(seleccion, profundidad):
    """Recorre los tableros en orden, imprime el estado de cada uno y el tiempo total de pared."""
    inicio_total = MPI.Wtime()
    resueltos = 0
    for ronda, (id_tablero, original) in enumerate(seleccion):
        inicio = MPI.Wtime()
        solucion, ramas, lanzadas = resolver_tablero(original, ronda, profundidad)
        segundos = MPI.Wtime() - inicio

        if solucion is None:
            estado = "Sin solución"
        elif es_solucion_valida(solucion, original):
            estado = "Resuelto"
            resueltos += 1
        else:
            estado = "SOLUCIÓN INVÁLIDA"
        print(f"ID {id_tablero}: {estado} ({segundos:.6f} s, {ramas} ramas, {lanzadas} lanzadas)",
              flush=True)
    total = MPI.Wtime() - inicio_total

    for destino in range(1, size):
        comm.send(None, dest=destino, tag=TAG_TAREA)

    print(f"\nIDs resueltos: {resueltos} de {len(seleccion)}")
    print(f"Tiempo total (pared): {total:.6f} segundos")



def hay_aviso(ronda):
    """True si el 0 pidió cancelar esta ronda. Descarta avisos de rondas anteriores."""
    while comm.Iprobe(source=0, tag=TAG_PARAR):
        if comm.recv(source=0, tag=TAG_PARAR) == ronda:
            return True
    return False


def buscar(tablero, ronda, contador):
    """Backtracking como sudoku.resolver, pero consulta cada cierto tiempo si debe parar."""
    for fila in range(9):
        for columna in range(9):
            if tablero[fila][columna] != 0:
                continue
            for valor in range(1, 10):
                if puede_colocar(tablero, fila, columna, valor):
                    tablero[fila][columna] = valor
                    contador[0] += 1
                    if contador[0] % PASOS_ENTRE_AVISOS == 0 and hay_aviso(ronda):
                        raise Cancelado
                    if buscar(tablero, ronda, contador):
                        return True
                    tablero[fila][columna] = 0
            return False
    return True


def trabajador():
    """Recibe ramas hasta que el 0 avisa que no hay más; responde una vez por cada rama."""
    while True:
        tarea = comm.recv(source=0, tag=TAG_TAREA)
        if tarea is None:
            return
        ronda, tablero = tarea
        try:
            resuelto = buscar(tablero, ronda, [0])
        except Cancelado:
            resuelto = False
        comm.send((resuelto, tablero if resuelto else None), dest=0, tag=TAG_RESULTADO)



def main():
    parser = argparse.ArgumentParser(description="Sudoku por ramas con MPI.")
    parser.add_argument("--archivo", type=Path, default=RAIZ / "seeds.txt",
                        help="archivo de seeds (por defecto: seeds.txt de la carpeta superior)")
    parser.add_argument("--profundidad", type=int, default=PROFUNDIDAD,
                        help=f"casillas vacías que se fijan para crear ramas (por defecto: {PROFUNDIDAD})")
    seleccion_cli = parser.add_mutually_exclusive_group()
    seleccion_cli.add_argument("--id", dest="id", help="resolver solo el tablero con este ID")
    seleccion_cli.add_argument("--all", action="store_true",
                               help="resolver todos los tableros en orden (por defecto)")
    args = parser.parse_args()

    if size < 2:
        if rank == 0:
            print("Hacen falta al menos 2 procesos: uno coordina y el resto busca (-n 2 o más).")
        sys.exit(1)

    seleccion = []
    error = None
    if rank == 0:
        try:
            seeds = leer_seeds(args.archivo)
            if args.id and args.id not in seeds:
                error = f"ID '{args.id}' no existe. Disponibles: {', '.join(seeds)}"
            elif args.id:
                seleccion = [(args.id, seeds[args.id])]
            else:
                seleccion = list(seeds.items())
        except OSError as problema:
            error = f"No se pudo leer {args.archivo}: {problema}"
    error = comm.bcast(error, root=0)
    if error:
        if rank == 0:
            print(error)
        sys.exit(1)

    if rank == 0:
        coordinador(seleccion, args.profundidad)
    else:
        trabajador()


if __name__ == "__main__":
    main()
