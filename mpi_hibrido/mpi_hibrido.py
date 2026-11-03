"""Resuelve los tableros de seeds.txt combinando dos repartos: los tableros se reparten entre
grupos de procesos y, dentro de cada grupo, las ramas del tablero asignado se reparten entre
sus miembros. Varios grupos trabajan a la vez, cada uno en un tablero distinto."""

import argparse
import sys
from collections import deque
from pathlib import Path

from mpi4py import MPI

# Los archivos del profesor viven en la carpeta superior (/app dentro del contenedor).
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
PROFUNDIDAD = 4     # casillas vacías cuyas opciones válidas se fijan para crear las ramas
TAMANO_GRUPO = 4    # trabajadores por grupo (los trabajadores son los procesos 1..size-1)
PASOS_ENTRE_AVISOS = 1000  # cada cuántas casillas colocadas se consulta si hay aviso de parada


class Cancelado(Exception):
    """La búsqueda se interrumpe porque otro proceso ya halló la solución del tablero."""


# ------------------------------------------------------- ramas y validación (rango 0)

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


# ------------------------------------------------------------------ coordinador (rango 0)

class Grupo:
    """Estado de un grupo de trabajadores y del tablero que está resolviendo."""

    def __init__(self, indice, trabajadores):
        self.indice = indice
        self.trabajadores = trabajadores
        self.libres = list(reversed(trabajadores))
        self.ocupados = set()
        self.activo = False
        self.ronda = None
        self.id_tablero = None
        self.original = None
        self.ramas = deque()
        self.total_ramas = 0
        self.lanzadas = 0
        self.solucion = None
        self.inicio = 0.0

    def empezar(self, ronda, id_tablero, original, profundidad):
        """Le asigna un tablero nuevo: genera sus ramas y reinicia el estado."""
        self.activo = True
        self.ronda = ronda
        self.id_tablero = id_tablero
        self.original = original
        self.inicio = MPI.Wtime()
        self.ramas = deque(generar_ramas(original, profundidad))
        self.total_ramas = len(self.ramas)
        self.lanzadas = 0
        self.solucion = None

    def repartir(self):
        """Da una rama a cada trabajador libre mientras queden y no haya solución."""
        while self.libres and self.ramas and self.solucion is None:
            destino = self.libres.pop()
            comm.send((self.ronda, self.ramas.popleft()), dest=destino, tag=TAG_TAREA)
            self.ocupados.add(destino)
            self.lanzadas += 1


def coordinador(seleccion, profundidad, tamano_grupo):
    """Reparte los tableros entre grupos, recoge los resultados y muestra el tiempo de pared."""
    trabajadores = list(range(1, size))

    # Se parten los trabajadores en trozos de `tamano_grupo`; cada trozo es un grupo.
    grupos = []
    for inicio in range(0, len(trabajadores), tamano_grupo):
        miembros = trabajadores[inicio:inicio + tamano_grupo]
        grupos.append(Grupo(inicio // tamano_grupo, miembros))

    # A qué grupo pertenece cada trabajador (para saber de quién es una respuesta).
    grupo_de = {}
    for grupo in grupos:
        for miembro in grupo.trabajadores:
            grupo_de[miembro] = grupo

    pendientes = deque(enumerate(seleccion))
    resueltos = 0

    def terminar(grupo):
        """Imprime el resultado del tablero que acaba de terminar el grupo."""
        nonlocal resueltos
        segundos = MPI.Wtime() - grupo.inicio
        if grupo.solucion is None:
            estado = "Sin solución"
        elif es_solucion_valida(grupo.solucion, grupo.original):
            estado = "Resuelto"
            resueltos += 1
        else:
            estado = "SOLUCIÓN INVÁLIDA"
        print(f"ID {grupo.id_tablero}: {estado} ({segundos:.6f} s, grupo {grupo.indice}, "
              f"{grupo.total_ramas} ramas, {grupo.lanzadas} lanzadas)", flush=True)

    def avanzar(grupo):
        """Reparte ramas; si el tablero del grupo terminó, lo registra y le da el siguiente."""
        while True:
            if grupo.activo:
                grupo.repartir()
                if grupo.ocupados:
                    return
                terminar(grupo)
                grupo.activo = False
            if not pendientes:
                return
            ronda, (id_tablero, original) = pendientes.popleft()
            grupo.empezar(ronda, id_tablero, original, profundidad)

    def alguno_ocupado():
        """True si algún grupo todavía tiene un trabajador con una rama en curso."""
        for grupo in grupos:
            if grupo.ocupados:
                return True
        return False

    inicio_total = MPI.Wtime()
    for grupo in grupos:
        avanzar(grupo)

    while alguno_ocupado():
        estado = MPI.Status()
        resuelto, tablero_resuelto = comm.recv(source=MPI.ANY_SOURCE, tag=TAG_RESULTADO, status=estado)
        origen = estado.Get_source()
        grupo = grupo_de[origen]
        grupo.ocupados.discard(origen)
        grupo.libres.append(origen)
        if resuelto and grupo.solucion is None:
            grupo.solucion = tablero_resuelto
            for otro in grupo.ocupados:
                comm.send(grupo.ronda, dest=otro, tag=TAG_PARAR)
        avanzar(grupo)
    total = MPI.Wtime() - inicio_total

    for destino in trabajadores:
        comm.send(None, dest=destino, tag=TAG_TAREA)

    print(f"\nGrupos: {len(grupos)} (tamaño {tamano_grupo}); profundidad de ramas: {profundidad}")
    print(f"IDs resueltos: {resueltos} de {len(seleccion)}")
    print(f"Tiempo total (pared): {total:.6f} segundos")


# ------------------------------------------------------------- búsqueda (trabajadores)

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


# ------------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Sudoku híbrido (tableros y ramas) con MPI.")
    parser.add_argument("--archivo", type=Path, default=RAIZ / "seeds.txt",
                        help="archivo de seeds (por defecto: seeds.txt de la carpeta superior)")
    parser.add_argument("--profundidad", type=int, default=PROFUNDIDAD,
                        help=f"casillas vacías que se fijan para crear ramas (por defecto: {PROFUNDIDAD})")
    parser.add_argument("--tamano-grupo", type=int, default=TAMANO_GRUPO,
                        help=f"trabajadores por grupo (por defecto: {TAMANO_GRUPO})")
    seleccion_cli = parser.add_mutually_exclusive_group()
    seleccion_cli.add_argument("--id", dest="id", help="resolver solo el tablero con este ID")
    seleccion_cli.add_argument("--all", action="store_true",
                               help="resolver todos los tableros (por defecto)")
    args = parser.parse_args()

    if size < 2:
        if rank == 0:
            print("Hacen falta al menos 2 procesos: uno coordina y el resto busca (-n 2 o más).")
        sys.exit(1)
    if args.tamano_grupo < 1:
        parser.error("--tamano-grupo debe ser al menos 1")

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
        coordinador(seleccion, args.profundidad, args.tamano_grupo)
    else:
        trabajador()


if __name__ == "__main__":
    main()
