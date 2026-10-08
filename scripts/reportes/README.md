# Reporte Mensual con IA

Genera el PDF que aparece en la pestaña "Reportes Mensuales" del dashboard.

## Cómo correrlo (manual o desde la Routine mensual)

```bash
cd scripts/reportes

# 1) Traer los datos reales del Sheet (requiere que el entorno tenga
#    docs.google.com habilitado en Network access -- si no, ST.meses
#    queda vacío y el script avisa en vez de fallar en silencio)
NODE_USE_ENV_PROXY=1 node extract_data.js ../../index.html real_data.json

# 2) Armar el PDF
python3 build_report.py --data real_data.json --out reporte.pdf \
  --mes-label "Agosto 2026"
```

Dependencias de Python: `reportlab`, `svglib` (`pip install reportlab svglib`).

## Antes de publicarlo

1. Abrí `reporte.pdf` y miralo entero -- la sección "ANÁLISIS DEL MES" sale
   con bullets mínimos generados a mano alzada (el mayor rubro que subió, y
   un aviso si la facturación total dio negativa) más un placeholder
   `[Completar a mano: ...]`. Reemplazá ese placeholder por 1-3 líneas que
   expliquen el *por qué* de lo más llamativo del mes -- no alcanza con
   repetir los números que ya están en las tablas.
2. Revisá "Proveedores recurrentes con mayor pago": la lista sale ordenada
   por monto sin filtrar, así que a veces trae renglones genéricos (ej.
   "Gtos Mant de Oficina") en vez de proveedores con nombre propio -- está
   bien dejarlos, pero si hay algo raro (un proveedor que debería estar y no
   está, un monto que no cierra), es más fácil que sea un dato real atípico
   que un bug de este script.
3. Fijate en los "N/D" (ratios con facturación <= 0 ese mes): son así a
   propósito (ver el docstring de `build_report.py`), no un error.

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
