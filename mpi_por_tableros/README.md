# Tarea 1: repartir tableros

Implementa una versión MPI en esta carpeta. Al ejecutar todos los tableros, cada ID debe ser una tarea que pueda asignarse a un proceso. Reutiliza el resolvedor de `../sudoku.py` y reúne los estados en el proceso coordinador.

Registra el tiempo total de ejecución y confirma que se procesaron los 30 IDs. Añade aquí el comando para ejecutar tu implementación con el contenedor. Incluye `--allow-run-as-root --use-hwthread-cpus --oversubscribe` en `mpiexec`, como en la calibración.

---

## Cómo ejecutarlo

Desde la carpeta raíz del repositorio (la que contiene `sudoku.py` y `seeds.txt`), con `N = 13`, el valor que recomendó el calibrador en este equipo.

Windows (PowerShell):

```powershell
docker run --rm -v "${PWD}:/app" augustosalazar/slim-mpi:2 mpiexec --allow-run-as-root --use-hwthread-cpus --oversubscribe -n 13 python /app/mpi_por_tableros/mpi_por_tablero.py --all
```

macOS / Linux:

```bash
docker run --rm -v "$(pwd):/app" augustosalazar/slim-mpi:2 mpiexec --allow-run-as-root --use-hwthread-cpus --oversubscribe -n 13 python /app/mpi_por_tableros/mpi_por_tablero.py --all
```

Opciones: `--all` (resuelve los 30 tableros; es lo que hace siempre esta versión) y `--archivo <ruta>` para leer otro archivo de seeds. Hacen falta al menos 2 procesos.

## Qué hace

- El proceso 0 lee `seeds.txt` una sola vez y no resuelve tableros: con `N = 13` hay 12 trabajadores (procesos 1 a 12).
- Reparte los 30 IDs por bloques. Con 30 tableros y 12 trabajadores, seis trabajadores reciben 3 tableros y seis reciben 2. Cada trabajador recibe un diccionario `{id: tablero}` con solo los tableros de su bloque, de modo que ninguno necesita leer el archivo.
- Cada trabajador resuelve sus tableros uno tras otro con `resolver_con_tiempo` de `sudoku.py` y devuelve un único mensaje con una lista de `(id, resuelto, segundos)`.
- El proceso 0 recibe los 12 mensajes, comprueba que llegaron los 30 IDs y muestra el estado de cada uno, la carga de cada proceso (suma de los tiempos de búsqueda de sus tableros) y el tiempo total.
- El tiempo total es de reloj de pared (`MPI.Wtime()`) en el proceso 0, desde que empieza el reparto hasta que llega el último resultado. No incluye la lectura de `seeds.txt`, igual que la medición de la versión secuencial.

## Resultado

Tres ejecuciones con `N = 13`: 8,832892 s, 8,810660 s y 8,681434 s. Mediana: **8,810660 s**. Aceleración frente a la versión secuencial (50,188901 s): **5,70**.
