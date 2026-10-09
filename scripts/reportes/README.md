# Reporte Mensual con IA

Genera el PDF que aparece en la pestaña "Reportes Mensuales" del dashboard.

## Cómo correrlo (manual o desde la Routine mensual)

```bash
cd scripts/reportes

# 1) Traer los datos reales del Sheet (requiere que el entorno tenga
#    docs.google.com habilitado en Network access -- si no, ST.meses
#    queda vacío y el script avisa en vez de fallar en silencio)
NODE_USE_ENV_PROXY=1 node extract_data.js ../../index.html real_data.json

# 2) Armar el PDF (--bullet es opcional, repetible, ver paso 1 de abajo)
python3 build_report.py --data real_data.json --out reporte.pdf \
  --mes-label "Agosto 2026" \
  --bullet "Por qué pasó lo más llamativo del mes, en 1-2 líneas." \
  --bullet "Otra cosa que valga la pena explicar, si la hay."
```

Dependencias de Python: `reportlab`, `svglib` (`pip install reportlab svglib`).

## Antes de publicarlo

1. Mirá la sección "ANÁLISIS DEL MES · {mes}" (el título lleva el mes que
   pasaste en `--mes-label`): arranca con 1 bullet generado solo (el mayor
   rubro que subió), más un bullet automático por cada rubro/proveedor del
   top 3/5 que tenga una nota cargada en `NOTAS_CUENTAS` (extract_data.js)
   -- ver punto 2. Si no le pasaste `--bullet`, el PDF sale con un
   placeholder `[Completar a mano: ...]` -- antes de publicar, volvé a
   correr `build_report.py` con 1-3 `--bullet` que expliquen el *por qué*
   de lo más llamativo del mes (revisando la nota de la fila en el Sheet,
   el desglose de un rubro, lo que haga falta). No alcanza con repetir los
   números que ya están en las tablas. Si citás un monto puntual (ej. "el
   rubro X subió a $Y"), sumale el promedio de ese mismo concepto en todos
   los meses cargados -- sin esa referencia no se puede distinguir un
   valor atípico de uno normal (ver el caso real de Agosto 2026 en el
   historial de git: "IVA No Computable" parecía un salto, pero estaba en
   línea con el promedio -- Julio había sido el mes atípico, no Agosto).
2. `NOTAS_CUENTAS` (en `extract_data.js`) es una lista a mano de "por qué"
   reales para una cuenta/proveedor/rubro en un mes puntual (ej. "Gtos
   Mant de Oficina" bajó de Julio a Agosto porque en Julio hubo una obra
   de mantenimiento que no se repitió). Cuando esa cuenta aparece en el
   top de "Top rubros" o "Cuentas / Proveedores con mayor variación" --
   en cualquiera de los dos meses de la comparación -- el bullet de
   "Análisis del mes" lo explica solo, en vez de quedarse en el número
   pelado. Agregá una entrada nueva la primera vez que alguien te cuente
   el motivo real de un movimiento raro -- después se va a seguir usando
   solo en cualquier mes futuro donde ese mismo nombre vuelva a aparecer
   en el top (ej. si en Septiembre "Gtos Mant de Oficina" vuelve a
   compararse contra Julio por algún motivo).
2. Revisá "Proveedores con mayor variación": la lista sale ordenada por
   |variación %| (no por monto), filtrada a pares con monto > 0 en ambos
   meses. Si hay algo raro (un proveedor que debería estar y no está, un
   monto que no cierra), es más fácil que sea un dato real atípico que un
   bug de este script.
3. Fijate en los "N/D" (ratios con facturación <= 0 ese mes): son así a
   propósito (ver el docstring de `build_report.py`), no un error.
4. "Unit economics": "Comitentes" y "Empleados" son fijos en la hoja
   Matriz (el mismo número en el reporte de cualquier mes -- no hay
   desglose mensual para eso en el Sheet), **no** son del mes de ese
   reporte. "Facturación" y "Costo" sí son de mesActual. El subtítulo de
   la tabla lo aclara; no lo cambies a algo tipo "Datos de {mes}" sin
   especificar qué es fijo y qué no, porque da a entender que todo es de
   ese mes. (Antes "Facturación/comitente" usaba la "Facturación promedio
   (Ene-Jul)" de la Matriz -- un promedio histórico fijo -- en vez de la
   facturación real del mes; eso hacía que, en un mes con facturación
   negativa, la tabla siguiera mostrando un número positivo que no
   reflejaba lo que había pasado ese mes puntual.) No incluye
   operaciones/comitente: el dato de "Operaciones promedio" de Mesa en la
   Matriz no es confiable todavía. La "Facturación" de FAs en esta sección
   es neta de "Comisiones Productores" (un gasto directo de FAs en el
   Sheet, pero conceptualmente es plata que se queda el productor externo,
   no FAs) -- solo para estas métricas, no para el resto del reporte
   ("Facturación por área" sigue siendo la bruta del Sheet). "Costo" es el
   GASTOS TOTALES del Sheet (Directos + Indirectos prorrateados), no solo
   el costo directo del área -- por eso la tabla dice "Costo total", para
   no dar a entender que es solo lo propio (ver "Gastos Directos vs
   Indirectos por área" para esa distinción).
5. "Excepciones / no recurrentes" solo mira el mes que se está
   reportando, no el historial completo -- el reporte de Agosto no repite
   un viaje que ya salió en el de Junio o Julio. Si no hubo ninguna
   excepción ese mes, la sección directamente no aparece en el PDF (no es
   un bug).
6. Las 3 KPI cards (Facturación Bruta, Gastos Totales, Resultado) siempre
   muestran la variación como %, incluso si la base del mes anterior era
   negativa o el valor cruzó el cero -- `pct_or_delta` (en
   `build_report.py`) calcula el % sobre el valor ABSOLUTO de la base,
   no la base con signo, para que el signo del % siempre coincida con si
   mejoró o empeoró (antes se reemplazaba por el delta en USD en esos
   casos, porque la fórmula estándar divide por un número negativo e
   invierte el signo -- ver el comentario de la función). Solo se
   muestra el delta en USD cuando la base es exactamente 0.
7. "Gastos Directos vs Indirectos por área": separa cuánto del costo de
   cada área es propio (Directos) de cuánto es prorrateo de la estructura
   común (Indirectos, repartido según la Matriz) -- en áreas chicas (BC,
   BP) el prorrateo puede ser la mayor parte del ratio "Gastos /
   Facturación" de la sección siguiente, y sin este desglose no se nota.
   "Directos" es la fila "GASTOS DIRECTOS" del Sheet (un gasto real) --
   **no** `d.subtotalRow` ("SUBTOTAL DIRECTOS"), que es Facturación Bruta
   MENOS Gastos Directos (contribución marginal, no un costo). Usar esa
   otra fila fue un bug real de la primera versión de esta sección: daba
   negativo en Mesa porque su facturación fue negativa ese mes, no por
   ningún gasto, y la "explicación" que el reporte mostraba entonces
   (sobre el descuento de costos de mercado de la facturación) estaba mal
   enfocada -- verificá cualquier cambio futuro acá contra las 4 áreas
   (fact - GASTOS_DIRECTOS == SUBTOTAL_DIRECTOS, con datos reales) antes
   de confiar en qué fila es cuál. Con la fila correcta, "Directos" no
   debería dar negativo nunca -- si pasa, es señal de revisar el Sheet
   (ya no hay un caso "esperado" para ninguna área, ni para Mesa).
8. "Cuentas / Proveedores con mayor variación" (antes solo "Proveedores"):
   Gastos Fijos Detalle no siempre tiene un proveedor con nombre propio
   en cada fila -- a veces es una cuenta genérica (ej. "Gtos Mant de
   Oficina"). El título y la columna dicen "Cuenta / Proveedor" a
   propósito, para no prometer algo más específico de lo que hay.
9. "Notas de metodología" (al final del PDF) trae el tipo de cambio (MEP)
   usado ese mes -- se re-pide la hoja cruda de ese mes nomás para leer la
   fila "DÓLAR AL ...", que el loader del dashboard corta a propósito
   (todo lo que sigue a "GASTOS TOTALES" en la hoja es contable/de caja,
   no entra a `ST.mesData`).
10. "Resultado acumulado {primer mes} - {mes actual}" (debajo de las 3 KPI
    cards) suma el mismo "resultado" por mes que ya arma `kpiTrend` para
    el gráfico de Evolución -- no reimplementa el cálculo. Se omite en el
    primer mes del año (ahí sería el mismo número que el KPI "Resultado").
11. "Margen por área" (Resultado/Facturación) es la contracara de "Ratios
    por área" (Gastos/Facturación): una mira costo, la otra rentabilidad.
    Usa `margen_cell`, no `ratio_cell` -- son conceptualmente distintos:
    en un ratio de costo "bueno" es estar por debajo de un umbral, en un
    margen "bueno" es ser positivo sin importar cuánto. Reusar
    `ratio_cell` acá (o en el card de "Margen neto" de la compañía, que
    tenía este mismo bug con `good_below=100` antes de esta corrección)
    pinta de verde una pérdida grande con tal de que el % no pase ese
    umbral -- no hagas eso de nuevo.
12. "Top rubros que más subieron" filtra a `deltaPct > 0` antes de tomar
    los primeros 10 -- no es un `[:10]` plano sobre la lista ordenada por
    variación. Un mes con menos de 10 rubros que efectivamente subieron
    (ej. Agosto 2026 con 9) muestra menos de 10 filas; eso es correcto,
    no un bug -- lo contrario (completar el cupo con rubros que bajaron,
    bajo un título que dice "que más subieron") fue el bug real al pasar
    de top 3 a top 10. `rubros_suben` se calcula una sola vez cerca del
    inicio de `build()` y se reusa tanto acá como en el escaneo de notas
    automáticas de "Análisis del mes".
13. "Evolución Unit Economics" (dos gráficos, debajo de las tablas de
    Unit Economics): igual que "Evolución últimos meses" pero para
    Costo total/comitente y Facturación/comitente, una línea por área,
    con los mismos colores de `AREA_COLOR`. Sale de `unitEconomicsTrend`
    (un `unitEconomicsFor(mes)` por cada mes de `mesesTrend`, en
    `extract_data.js`) dividido por el comitente fijo de cada área. Usa
    `trend_chart(..., fmt_axis=...)` con un formateador propio (`usd2`,
    sin compactar a "k") en vez del default -- los montos por comitente
    son mucho más chicos que Facturación/Gastos/Resultado totales, y el
    formateador por defecto (compacta a miles) repetía la misma etiqueta
    ("1k", "1k", "0k") en el eje. Si se agrega un gráfico de otra métrica
    a escala chica, pasarle también un `fmt_axis` en vez de dejar el
    default.

## Subirlo al dashboard

```bash
cp reporte.pdf ../../reportes/<AAAA>-<MM>-reporte-<mes>.pdf
```

Y en `index.html`, agregar una entrada al array `REPORTES_MENSUALES`
(buscá `const REPORTES_MENSUALES=`) con `{mes, archivo, generado}`. Comiteá
todo junto (PDF + el cambio en `index.html`), empujá a un branch nuevo y
abrí/mergeá el PR como cualquier otro cambio de este repo.

## Archivos de este directorio

- `extract_data.js` -- corre el `<script>` real de `index.html` dentro de
  Node (sin navegador, para evitar el problema de que Chromium no confía en
  el certificado del proxy de este entorno) y vuelca a JSON lo que necesita
  `build_report.py`: KPIs del mes actual y anterior, últimos hasta 6 meses
  para el gráfico de evolución, ranking de rubros, y el detalle de
  proveedores (Gastos Fijos Detalle).
- `build_report.py` -- arma el PDF a partir de ese JSON. Tiene varias
  guardas para datos reales "raros" (facturación negativa, bases <= 0 para
  un %) -- **leé el docstring del módulo** antes de tocarlo.
- `fonts/`, `neix_logo.svg`, `tri_*.png` -- assets de marca (misma
  tipografía DM Sans/DM Mono que el dashboard, logo real, íconos de
  flecha).
