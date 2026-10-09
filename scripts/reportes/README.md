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
   rubro que subió). Si no le pasaste `--bullet`, el PDF sale con un
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
6. Un % de variación no se muestra -- se reemplaza por el delta en USD --
   no solo cuando la base del mes anterior es <= 0, sino también cuando
   el valor cambia de signo entre los dos meses (ej. Facturación de
   positiva a negativa). Ambos casos hacen que el % no sea interpretable
   directamente (ver `pct_or_delta` en `build_report.py`).
7. "Gastos Directos vs Indirectos por área": separa cuánto del costo de
   cada área es propio (Directos) de cuánto es prorrateo de la estructura
   común (Indirectos, repartido según la Matriz) -- en áreas chicas (BC,
   BP) el prorrateo puede ser la mayor parte del ratio "Gastos /
   Facturación" de la sección siguiente, y sin este desglose no se nota.
   Si el "Directos" de un área da negativo, el % de esa fila sale "N/D"
   en vez de un número sin sentido (puede pasar >100%, o invertirse el
   signo) -- para Mesa hay una causa estructural conocida (ver nota en el
   PDF); para cualquier otra área, es una señal de revisar el Sheet.
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
