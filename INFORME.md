# Informe de resultados

Completa este informe después de implementar las tres tareas MPI. Ejecuta las comparaciones con el mismo archivo `seeds.txt`, en el mismo equipo y con el contenedor del taller.

## Entorno

- Equipo: Intel Core Ultra 9 285H, 16 núcleos y 16 hilos, 31,4 GB de RAM, Windows 11, Docker 29.1.5
- Versión del contenedor: augustosalazar/slim-mpi:2
- Cantidad de repeticiones por medición: 3
- Valor común de `N` elegido: 13

## Comparación final con el mismo `N`

Repite tres veces cada ejecución y registra la mediana. Mantén fijo el `N` elegido en todas las filas MPI. Incluye `--allow-run-as-root --use-hwthread-cpus --oversubscribe` en `mpiexec`, igual que en la calibración, para permitir valores de `N` mayores que los slots detectados.

| Implementación  | Caso                                | Procesos | Mediana del tiempo total (s) | Aceleración frente a secuencial |
| ---------------- | ----------------------------------- | -------: | ---------------------------: | -------------------------------: |
| Secuencial       | Todos los IDs                       |        1 |                    50,188901 |                             1,00 |
| MPI por tableros | Todos los IDs                       |       13 |                     8,810660 |                             5,70 |
| MPI por ramas    | Todos los IDs, uno después de otro |       13 |                     7,543428 |                             6,65 |
| MPI híbrido     | Todos los IDs                       |       13 |                     7,572877 |                             6,63 |

Calcula la aceleración como `tiempo secuencial / tiempo MPI`. Mide el tiempo MPI desde el inicio del reparto hasta recibir todos los resultados necesarios.

Tiempos de cada repetición (s): secuencial 50,244431 / 48,037392 / 50,188901; por tableros 8,832892 / 8,810660 / 8,681434; por ramas (profundidad 4) 7,543428 / 7,570248 / 7,506786; híbrido (grupos de 4, profundidad 4) 7,414420 / 7,779544 / 7,572877.

## Conclusiones

**¿Qué estrategia obtuvo el menor tiempo para los 30 tableros? ¿Cuánto mejoró respecto a la versión secuencial?**

La estrategia por ramas obtuvo la mediana más baja, 7,54 s, y el híbrido quedó en 7,57 s. La diferencia de 0,03 s es mínima, así que los dos resultados se consideran equivalentes y con estas mediciones ninguno se puede declarar mejor. Ambos bajan el tiempo de 50,19 s a unos 7,5 s, una aceleración de 6,6 veces, que equivale a una reducción de cerca del 85 %. La versión por tableros quedó en 8,81 s (aceleración 5,70), unos 1,3 s (17 %) más lenta que las otras dos. Entre ramas e híbrido se recomienda la de ramas para esta cantidad de sudokus: logra el mismo tiempo con menos piezas, porque no hay que decidir el tamaño de los grupos.

**¿Cómo afectaron la comunicación y las diferencias de duración entre tableros?**

Los tableros tardan entre 1 y 4 s cada uno en este equipo. El reparto por tableros entrega casi la misma cantidad de tableros a cada proceso (seis procesos reciben tres tableros y los otros seis reciben dos) sin considerar cuánto cuesta cada uno, y por eso la carga queda desigual. En la ejecución de comprobación, el proceso más cargado acumuló 9,04 s de búsqueda y el menos cargado 3,03 s, y el tiempo total (9,04 s) coincidió con el del más cargado, porque el coordinador debe esperar al último. Con una carga igual en todos, el tiempo habría estado cerca del promedio, unos 5,3 s. Las versiones por ramas e híbrida reducen este efecto porque entregan trabajo al proceso que se libera.

En comunicación, la versión por tableros intercambia 24 mensajes en total (12 de ida y 12 de vuelta). Las versiones por ramas envían una rama por mensaje, con su respuesta, y aun así fueron más rápidas. En este equipo, el costo de comunicar fue pequeño frente a lo que se gana al balancear la carga. El costo sí se nota cuando se exagera: en la versión por ramas, la profundidad 5 (ramas más pequeñas y más mensajes) tardó 12,96 s frente a 10,02 s de la profundidad 4, y las profundidades 1 y 2 (pocas ramas, trabajadores sin tarea) tardaron 33,69 s y 19,55 s.

**¿Cómo se comparó repartir tableros con resolverlos en orden y repartir las ramas de cada uno?**

Repartir tableros sincroniza una sola vez, al final, y no desperdicia trabajo, pero el tiempo total depende de lo desigual que quede la carga. Resolver los tableros en orden y repartir sus ramas paga una generación de ramas y una espera por cada uno de los 30 tableros, y desperdicia el trabajo de las ramas lanzadas que no contenían la solución. A cambio, los trabajadores atacan todos el mismo tablero: un tablero difícil se reparte entre todos y ningún proceso concentra la carga. En este conjunto de tableros, el costo de esa espera y del trabajo perdido fue menor que el del desbalance: 7,54 s frente a 8,81 s.

El híbrido reparte los tableros entre grupos y las ramas dentro de cada grupo. El tamaño se eligió con un barrido de grupos de 1, 2, 3, 4, 6 y 12 trabajadores. En la repetición intercalada de los candidatos, las medianas fueron 11,93 s, 10,49 s, 10,54 s, 9,42 s y 9,94 s para los tamaños 1, 2, 3, 4 y 6, y el tamaño 12 fue el más lento en la primera pasada. Se eligió 4 (tres grupos). Su tiempo final quedó igual al de por ramas. Una explicación posible es que con 12 trabajadores y, en promedio, más de 100 ramas por tablero ya hay trabajo para todos con un solo tablero a la vez, por lo que tener varios tableros en curso no añade una ventaja medible.
