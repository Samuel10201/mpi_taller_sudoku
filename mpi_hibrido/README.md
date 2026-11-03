# Tarea 3: combinar tableros y ramas

Implementa una versión MPI en esta carpeta. Reparte los IDs entre grupos de procesos y permite que los procesos de cada grupo exploren ramas distintas del tablero asignado.

Registra el tiempo total de los 30 IDs y explica cómo elegiste el tamaño de los grupos. Añade aquí el comando para ejecutar tu implementación con el contenedor. Incluye `--allow-run-as-root --use-hwthread-cpus --oversubscribe` en `mpiexec`, como en la calibración.

---

## Cómo ejecutarlo

Desde la carpeta raíz del repositorio (la que contiene `sudoku.py` y `seeds.txt`), con `N = 13`.

Windows (PowerShell):

```powershell
docker run --rm -v "${PWD}:/app" augustosalazar/slim-mpi:2 mpiexec --allow-run-as-root --use-hwthread-cpus --oversubscribe -n 13 python /app/mpi_hibrido/mpi_hibrido.py --all
```

macOS / Linux:

```bash
docker run --rm -v "$(pwd):/app" augustosalazar/slim-mpi:2 mpiexec --allow-run-as-root --use-hwthread-cpus --oversubscribe -n 13 python /app/mpi_hibrido/mpi_hibrido.py --all
```

Opciones: `--all` (por defecto), `--id <ID>`, `--archivo <ruta>`, `--profundidad <k>` (por defecto 4) y `--tamano-grupo <g>` (trabajadores por grupo; por defecto 4). Hacen falta al menos 2 procesos.

## Qué hace

- Los 12 trabajadores (procesos 1 a 12) se dividen en **grupos** de `g` trabajadores; con `g = 4` hay 3 grupos. El proceso 0 coordina y mantiene el estado de cada grupo (tablero actual, ramas pendientes, trabajadores ocupados y solución).
- **Primer reparto, los IDs:** el 0 entrega un tablero a cada grupo y, cuando un grupo termina el suyo, le entrega el siguiente ID de la lista. Varios tableros se resuelven a la vez, uno por grupo.
- **Segundo reparto, las ramas:** dentro de un grupo, el 0 reparte las ramas de su tablero entre los miembros libres (las primeras `k = 4` casillas vacías, como en `mpi_por_ramas`). Al hallarse la solución se avisa a los demás miembros del grupo para que dejen de buscar.
- Los trabajadores son los mismos que en `mpi_por_ramas` y no saben a qué grupo pertenecen: el 0 los maneja por grupos. No se usó `Comm.Split` porque el 0 ya se comunica directamente con cada trabajador. Las funciones comunes se copiaron de `mpi_por_ramas` para que esta carpeta se ejecute sola.
- Por cada ID se muestra el estado, el tiempo de pared, el grupo que lo resolvió y las ramas generadas y lanzadas. Los IDs aparecen en el orden en que terminan, no en el orden del archivo. Los tiempos por ID se solapan, por lo que su suma no es el total. El tiempo total es de pared en el 0, de principio a fin.

## Cómo se eligió el tamaño de los grupos

Los 12 trabajadores se pueden dividir en grupos de 1, 2, 3, 4, 6 o 12. Con `N = 13`, `--all` y profundidad 4, una primera pasada con una corrida por tamaño dio:

| Tamaño de grupo | Grupos | Tiempo total (s) |
|---|---|---|
| 1 | 12 | 7,17 |
| 2 | 6 | 6,43 |
| 3 | 4 | 8,28 |
| 4 | 3 | 8,17 |
| 6 | 2 | 8,64 |
| 12 | 1 | 10,26 |

Las diferencias entre corridas sueltas eran del tamaño de las diferencias entre tamaños, así que se repitieron los candidatos tres veces cada uno, intercalados para que la carga del equipo afectara a todos por igual:

| Tamaño de grupo | Corridas (s) | Mediana (s) |
|---|---|---|
| 1 | 8,96 / 12,43 / 11,93 | 11,93 |
| 2 | 9,24 / 10,49 / 10,52 | 10,49 |
| 3 | 9,43 / 10,59 / 10,54 | 10,54 |
| **4** | **8,92 / 9,42 / 9,91** | **9,42** |
| 6 | 9,44 / 9,94 / 10,04 | 9,94 |

Se eligió **4**, con la mediana más baja. Los extremos explican la forma de la curva: con grupos de 1 cada trabajador resuelve tableros enteros sin ayuda y queda expuesto al desbalance entre tableros; con un solo grupo de 12 se recupera la versión por ramas, que espera una respuesta de todos antes de cada tablero. Esta repetición se hizo con el equipo más cargado que en las mediciones finales, por eso los tiempos absolutos son más altos. La profundidad 4 también se comparó con la 3 en todos los tamaños y fue mejor en cada uno.

## Resultado

Tres ejecuciones con `N = 13`, grupos de 4 y profundidad 4: 7,414420 s, 7,779544 s y 7,572877 s. Mediana: **7,572877 s**. Aceleración frente a la versión secuencial (50,188901 s): **6,63**.
