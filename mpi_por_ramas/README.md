# Tarea 2: repartir ramas de cada tablero

Implementa una versión MPI en esta carpeta. Con `--all`, el proceso coordinador lee los 30 IDs de `seeds.txt` en orden. Para cada tablero, crea tareas a partir de opciones válidas de las primeras casillas vacías y reparte esas ramas entre procesos. Espera a que termine ese tablero antes de comenzar el siguiente: **los tableros se procesan secuencialmente y las ramas de cada tablero en paralelo**.

Cada proceso explora su rama con backtracking y comunica el resultado. Cuando se encuentra una solución, los demás deben dejar de buscar ese tablero. Muestra el estado y el tiempo parcial de cada ID al terminarlo, además del tiempo total de los 30. Conserva la opción `--id` para resolver un solo tablero.

Añade aquí los comandos para ejecutar `--id` y `--all` con el contenedor. Incluye `--allow-run-as-root --use-hwthread-cpus --oversubscribe` en `mpiexec`, como en la calibración. Compara el tiempo total de `--all` con la versión secuencial y registra los resultados en `../INFORME.md`.

---

## Cómo ejecutarlo

Desde la carpeta raíz del repositorio (la que contiene `sudoku.py` y `seeds.txt`), con `N = 13`.

Todos los tableros, en Windows (PowerShell):

```powershell
docker run --rm -v "${PWD}:/app" augustosalazar/slim-mpi:2 mpiexec --allow-run-as-root --use-hwthread-cpus --oversubscribe -n 13 python /app/mpi_por_ramas/mpi_por_ramas.py --all
```

Un solo tablero (por ejemplo el 7):

```powershell
docker run --rm -v "${PWD}:/app" augustosalazar/slim-mpi:2 mpiexec --allow-run-as-root --use-hwthread-cpus --oversubscribe -n 13 python /app/mpi_por_ramas/mpi_por_ramas.py --id 7
```

En macOS / Linux se cambia `"${PWD}:/app"` por `"$(pwd):/app"`.

Opciones: `--all` (por defecto), `--id <ID>`, `--archivo <ruta>` y `--profundidad <k>` (casillas vacías que se fijan para crear ramas; por defecto 4). Hacen falta al menos 2 procesos.

## Qué hace

- El proceso 0 recorre los IDs en orden. Para cada tablero genera las **ramas**: fija las opciones válidas de las primeras `k` casillas vacías (`k = 4`), y cada combinación es un tablero parcial independiente de los demás.
- Reparte las ramas **a medida que los trabajadores se liberan**: entrega una a cada trabajador libre y, cuando uno responde, le asigna la siguiente. Así el número de ramas no tiene que coincidir con el de trabajadores.
- Cada trabajador explora su rama con backtracking (la misma lógica de `sudoku.resolver`) y responde siempre con un mensaje: resuelto o no.
- **Parada:** al recibir una solución, el 0 deja de repartir y avisa a los trabajadores ocupados. Cada trabajador consulta, cada 1000 casillas colocadas, si hay aviso (`Iprobe`, sin bloquearse). El aviso lleva el número de tablero, de modo que uno tardío no cancela el tablero siguiente.
- El 0 **espera la respuesta de todas las ramas lanzadas** antes de pasar al tablero siguiente, así ningún mensaje de un tablero llega durante el otro.
- La solución se valida antes de marcar el tablero como `Resuelto` (filas, columnas, bloques y casillas originales).
- Por cada ID se muestra el estado, el tiempo de pared, las ramas generadas y las ramas lanzadas (la diferencia son las que el corte temprano evitó repartir). Al final se muestra el tiempo total de pared.

## Cómo se eligió la profundidad

Con `N = 13` y `--all`, una corrida por valor salvo donde se indica:

| Profundidad | Tiempo total (s) |
|---|---|
| 1 | 33,69 |
| 2 | 19,55 |
| 3 | 10,02 / 13,45 / 13,44 (mediana 13,44) |
| **4** | **10,70 / 10,02 / 9,94 (mediana 10,02)** |
| 5 | 12,96 |

Con profundidad 1 salen pocas ramas y casi todos los trabajadores se quedan sin nada que hacer. Con profundidad 5 las ramas son muchas y pequeñas, y el costo de mandar mensajes empieza a pesar. Se eligió 4. Estas corridas sirvieron para elegir; las mediciones finales se repitieron después con el valor ya fijado.

## Resultado

Tres ejecuciones con `N = 13` y profundidad 4: 7,543428 s, 7,570248 s y 7,506786 s. Mediana: **7,543428 s**. Aceleración frente a la versión secuencial (50,188901 s): **6,65**.
