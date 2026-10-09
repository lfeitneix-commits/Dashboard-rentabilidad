// Extrae del Sheet real (vía la lógica real del dashboard, sin reimplementarla)
// los datos que necesita build_report.py para el mes más reciente cargado.
//
// Corre el <script> de index.html directamente en Node (sin navegador): evita
// el problema de que Chromium no confía en el certificado del proxy de este
// entorno, cosa que curl/fetch de Node sí resuelven vía NODE_EXTRA_CA_CERTS.
//
// Uso:
//   NODE_USE_ENV_PROXY=1 node extract_data.js [ruta/a/index.html] [salida.json] [Mes]
//
// El tercer argumento (opcional) elige qué mes cargado es "mesActual" --
// por defecto es el último mes del Sheet. Sirve para generar el reporte de
// un mes pasado (ej. "Marzo") en vez del más reciente. "Evolución" y
// "Excepciones" quedan acotados a Enero..ese mes, no al año completo --
// cada reporte es una foto de lo que se sabía hasta ese momento.
//
// Requiere que el entorno tenga docs.google.com habilitado en Network access
// (si no, ST.meses queda vacío y el script lo avisa en vez de fallar en silencio).
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const indexPath = process.argv[2] || path.join(__dirname, '..', '..', 'index.html');
const outPath = process.argv[3] || path.join(__dirname, 'real_data.json');
const mesOverride = process.argv[4] || null;

function makeFakeEl() {
  const el = {
    style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {}, appendChild() {}, insertBefore() {}, remove() {},
    querySelector() { return makeFakeEl(); }, querySelectorAll() { return []; },
    focus() {}, getContext() { return {}; },
    set innerHTML(v) {}, get innerHTML() { return ''; },
    set textContent(v) {}, get textContent() { return ''; },
    children: [], offsetHeight: 0, scrollTop: 0,
  };
  return el;
}
const fakeDocument = {
  getElementById() { return makeFakeEl(); }, querySelectorAll() { return []; },
  querySelector() { return makeFakeEl(); }, createElement() { return makeFakeEl(); },
  addEventListener() {}, body: makeFakeEl(),
};
class ChartStub {
  constructor(ctx, config) { this.config = config; this.data = config.data; }
  destroy() {} static getChart() { return null; }
}
ChartStub.defaults = { font: {}, plugins: { legend: { labels: {} } } };
ChartStub.register = () => {};

const sandbox = {
  document: fakeDocument, window: {}, location: { reload() {} }, Chart: ChartStub, XLSX: {},
  fetch, AbortController, console, setTimeout, clearTimeout, Intl, TextDecoder, Promise, Set, Map,
  Math, JSON, Date, Object, Array, String, Number, RegExp, parseFloat, parseInt, isNaN, URLSearchParams,
};
sandbox.globalThis = sandbox;
sandbox.window = sandbox;

function extractScript(htmlPath) {
  const html = fs.readFileSync(htmlPath, 'utf-8');
  const m = /<script>([\s\S]*)<\/script>/.exec(html);
  if (!m) throw new Error('No se encontró el <script> principal en ' + htmlPath);
  return m[1];
}

let code = extractScript(indexPath);
// vm.runInContext no expone const/let de nivel superior como propiedades del
// contexto (a diferencia de var/function) -- se exportan explícito al final,
// en el mismo scope léxico, para poder usarlos después desde Node.
code += `
this.__APP__ = {
  ST, AREAS, getAreaVal, getClasifRubrosRanking, loadData, loadGastosFijosDetalleLazy, parseNum,
  BASE, SHEETS, parseCSV,
};`;
const context = vm.createContext(sandbox);
vm.runInContext(code, context, { filename: 'index.html#script' });
const APP = context.__APP__;

(async () => {
  await APP.loadData();
  if (!APP.ST.meses.length) {
    console.error('SIN DATOS -- revisar que este entorno pueda llegar a docs.google.com (Network access) y que las hojas tengan contenido.');
    process.exit(1);
  }
  await APP.loadGastosFijosDetalleLazy();

  const ST = APP.ST;
  const AREAS_ = APP.AREAS;
  const getAreaVal = APP.getAreaVal;
  const meses = ST.meses;
  const idxActual = mesOverride ? meses.indexOf(mesOverride) : meses.length - 1;
  if (idxActual < 0) {
    console.error(`"${mesOverride}" no está entre los meses cargados (${meses.join(', ')}).`);
    process.exit(1);
  }
  const mesActual = meses[idxActual];
  const mesAnterior = idxActual > 0 ? meses[idxActual - 1] : null;
  // Enero..mesActual -- no el año completo: el reporte de un mes es una
  // foto de lo que se sabía hasta ese momento, no debería adelantar meses
  // que todavía no habían pasado.
  const mesesTrend = meses.slice(0, idxActual + 1);

  const kpiFor = (mes) => {
    const d = ST.mesData[mes];
    if (!d) return null;
    const tI = AREAS_.reduce((s, a) => s + d.agg[a].ingresos, 0);
    const tE = AREAS_.reduce((s, a) => s + d.agg[a].egresos, 0);
    const tR = AREAS_.reduce((s, a) => s + d.agg[a].resultado, 0);
    return { ingresos: tI, egresos: tE, resultado: tR };
  };
  const areaVals = (mes, rowKey) => {
    const d = ST.mesData[mes];
    if (!d || !d[rowKey]) return null;
    const row = d[rowKey];
    return Object.fromEntries(AREAS_.map(a => [a, getAreaVal(row, a)]));
  };
  const ingresosPorArea = (mes) => {
    const d = ST.mesData[mes];
    if (!d) return null;
    return Object.fromEntries(AREAS_.map(a => [a, d.agg[a].ingresos]));
  };

  // Ranking de rubros (Fijo+Variable), mes actual vs anterior -- para "Top
  // rubros que más subieron". Se filtra a rubros con monto > 0 en AMBOS
  // meses (evita el artefacto de "+infinito%" de un rubro que apareció de la
  // nada, y división por cero de uno que desapareció) y, como en
  // proveedores, a montos de este mes > USD 500 -- si no, un rubro casi en
  // cero (ej. "Gastos Bancarios Exentos" de 6 a 382) puede salir como "el
  // que más subió" con un % absurdo sin que importe en términos absolutos.
  const RUBRO_MONTO_MIN = 500;
  let rubrosVariacion = [];
  if (mesAnterior) {
    const rankActual = APP.getClasifRubrosRanking(mesActual);
    const rankAnterior = APP.getClasifRubrosRanking(mesAnterior);
    const byNombreAnterior = Object.fromEntries(rankAnterior.map(r => [r.nombre, r.monto]));
    rubrosVariacion = rankActual
      .map(r => {
        const prev = byNombreAnterior[r.nombre] || 0;
        return { nombre: r.nombre, cat: r.cat, anterior: prev, actual: r.monto, deltaPct: prev ? (r.monto - prev) / prev * 100 : null };
      })
      .filter(r => r.anterior > 0 && r.actual > 0 && r.actual > RUBRO_MONTO_MIN)
      .sort((a, b) => b.deltaPct - a.deltaPct);
  }

  // Proveedores (Gastos Fijos Detalle) que más variaron mes contra mes --
  // ordenado por |variación %|, no por monto absoluto, para que salten a la
  // vista los cambios bruscos aunque el proveedor no sea de los más caros.
  // Se filtra a pares con monto > 0 en AMBOS meses (mismo criterio que
  // rubrosVariacion, evita el artefacto de "+infinito%" de un proveedor que
  // apareció de la nada o uno que bajó a cero) y, además, a montos de este
  // mes > USD 500 -- por debajo de eso el % puede ser enorme (ej. Slack de
  // 9 a 24) sin que importe en términos absolutos.
  const PROVEEDOR_MONTO_MIN = 500;
  let proveedores = [];
  const gfd = ST.gastosFijosDetalle;
  if (gfd && mesAnterior) {
    const idxActual = gfd.valCols.indexOf(mesActual);
    const idxAnterior = gfd.valCols.indexOf(mesAnterior);
    if (idxActual >= 0 && idxAnterior >= 0) {
      gfd.cuentas.forEach(cuenta => {
        cuenta.providers.forEach(p => {
          proveedores.push({ nombre: p.nombre, cuenta: cuenta.nombre, anterior: p.vals[idxAnterior], actual: p.vals[idxActual] });
        });
      });
      proveedores = proveedores
        .filter(p => p.anterior > 0 && p.actual > 0 && p.actual > PROVEEDOR_MONTO_MIN)
        .map(p => ({ ...p, deltaPct: (p.actual - p.anterior) / p.anterior * 100 }))
        .sort((a, b) => Math.abs(b.deltaPct) - Math.abs(a.deltaPct));
    }
  }

  // Unit economics (cruza "CÁLCULOS AUX" de la Matriz -- comitentes y
  // empleados por área, que no tienen desglose mensual en el Sheet -- con
  // Facturación y Gastos Totales de mesActual). No reimplementa nada que
  // no esté ya en el sheet: solo arma los cocientes. No incluye
  // operaciones/comitente: el dato de "Operaciones promedio" de Mesa en
  // la Matriz no es confiable todavía.
  //
  // Antes "Facturación/comitente" usaba la "Facturación promedio (Ene-Jul)"
  // de la Matriz -- un promedio fijo, no el dato real de mesActual. Eso
  // hacía que, en un mes con facturación negativa (Mesa en Agosto), la
  // tabla siguiera mostrando un número positivo (el promedio histórico),
  // que no refleja lo que pasó ese mes. Ahora usa la facturación real de
  // mesActual por área (mismo dato que "Facturación por área").
  const parseNum = APP.parseNum;
  function matrizAuxRow(labelSubstr) {
    if (!ST.matrizData) return null;
    const needle = labelSubstr.toLowerCase();
    return ST.matrizData.find(r => {
      const nom = String(Object.values(r)[0] || Object.values(r)[1] || '').trim().toLowerCase();
      return nom.startsWith(needle);
    }) || null;
  }
  function matrizAuxVal(row, area) {
    if (!row) return 0;
    const col = area === 'FAs' ? 'FAs + Mza' : area;
    const key = Object.keys(row).find(k => k.trim() === col) || col;
    return parseNum(row[key]);
  }
  let unitEconomics = null;
  {
    const comitentesRow = matrizAuxRow('comitentes totales');
    const empleadosRow = matrizAuxRow('empleados');
    const d = ST.mesData[mesActual];
    if (d && comitentesRow && empleadosRow) {
      const gastosTotales = d.gastosTotalesRow;
      const ingresosMes = ingresosPorArea(mesActual) || {};
      // FAs factura bruto, pero una parte de eso (via "Comisiones
      // Productores", que en el Sheet está cargado como un gasto directo
      // de FAs) se la queda el productor externo, no FAs -- para Unit
      // Economics (facturación "propia" por comitente/empleado) se usa la
      // neta de esa comisión. Solo afecta a FAs: esa cuenta da 0 en las
      // demás áreas.
      const comisionesRow = (d.annotated || []).find(r => r._nom && /^Comisiones\s+Productores$/i.test(r._nom.trim()));
      const comisionesProductoresFAs = comisionesRow ? getAreaVal(comisionesRow, 'FAs') : 0;
      unitEconomics = {
        mes: mesActual,
        porArea: AREAS_.map(a => ({
          area: a,
          comitentes: matrizAuxVal(comitentesRow, a),
          empleados: matrizAuxVal(empleadosRow, a),
          facturacionMes: (ingresosMes[a] || 0) - (a === 'FAs' ? comisionesProductoresFAs : 0),
          // gastoTotal = GASTOS TOTALES del Sheet = Directos + Indirectos
          // prorrateados (no solo el costo directo del área) -- mismo
          // criterio que "Gastos Totales + Impuestos por área".
          gastoTotal: gastosTotales ? getAreaVal(gastosTotales, a) : 0,
        })),
      };
    }
  }

  // Gastos directos vs indirectos por área -- el ratio Gastos/Facturación
  // de "Ratios por área" mezcla costo propio del área (directos) con el
  // prorrateo de la estructura común (indirectos, repartido según la
  // Matriz), y esa mezcla puede ser la mayor parte del ratio en áreas
  // chicas (BC, BP). d.subtotalRow/d.indirectosRow ya existen en ST (son
  // las mismas filas "SUBTOTAL DIRECTOS"/"GASTOS INDIRECTOS" que usa el
  // dashboard), así que esto no reimplementa nada. OJO: Mesa descuenta sus
  // costos de mercado directo de la facturación bruta (ver nota de esa
  // fila en el Sheet) -- su SUBTOTAL DIRECTOS puede dar negativo ese mes
  // por eso, no es un error de esta extracción.
  const directosIndirectosPorArea = (mes) => {
    const d = ST.mesData[mes];
    if (!d || !d.subtotalRow || !d.indirectosRow) return null;
    return Object.fromEntries(AREAS_.map(a => [a, {
      directos: getAreaVal(d.subtotalRow, a),
      indirectos: getAreaVal(d.indirectosRow, a),
    }]));
  };
  const directosIndirectosActual = directosIndirectosPorArea(mesActual);

  // Tipo de cambio (MEP) del mes -- fila "DÓLAR AL <fecha>", que el loader
  // del dashboard corta a propósito (todo lo que sigue a "GASTOS TOTALES"
  // en la hoja es contable/de caja, no entra a ST.mesData). Se vuelve a
  // pedir la hoja cruda de este mes nomás para sacar ese único valor.
  let dolarMEP = null;
  {
    const sheetInfo = APP.SHEETS.find(s => s.mes === mesActual);
    if (sheetInfo) {
      try {
        const res = await fetch(APP.BASE + sheetInfo.gid);
        const text = await res.text();
        const { rows } = APP.parseCSV(text);
        const dolarRow = rows.find(r => /^D[OÓ]LAR/i.test(String(Object.values(r)[0] || '').trim()));
        if (dolarRow) dolarMEP = parseNum(Object.values(dolarRow)[1]);
      } catch (e) {
        console.error('No se pudo obtener el tipo de cambio (no bloqueante):', e.message);
      }
    }
  }

  // Excepciones / no recurrentes DEL MES ACTUAL -- la hoja no tiene un flag
  // propio, se infiere de la nota de la cuenta. Solo el mes que se está
  // reportando, no el historial completo (el reporte de Agosto no debería
  // mostrar un viaje de Junio que ya salió en el reporte de Junio). Lista
  // de palabras clave a mano (ver README de este directorio) -- agregar
  // acá cualquier frase nueva que corresponda a un gasto puntual (viajes,
  // trámites puntuales, obras), no estructural.
  const EXCEPCION_KEYWORDS = [/ushuaia/i, /banco santa fe/i, /obra.*mant.*oficina/i, /mant.*oficina.*obra/i];
  const excepciones = [];
  {
    const d = ST.mesData[mesActual];
    (d ? d.annotated : []).forEach(row => {
      if (row._kind !== 'account' && row._kind !== 'subaccount') return;
      const nota = (row._allNotes || row._note || '').trim();
      if (!nota) return;
      if (!EXCEPCION_KEYWORDS.some(re => re.test(nota))) return;
      const monto = AREAS_.reduce((s, a) => s + getAreaVal(row, a), 0);
      if (!monto) return;
      excepciones.push({ mes: mesActual, cuenta: row._nom, nota, monto });
    });
  }

  const out = {
    mesActual,
    mesAnterior,
    mesesTrend,
    kpiActual: kpiFor(mesActual),
    kpiAnterior: mesAnterior ? kpiFor(mesAnterior) : null,
    kpiTrend: mesesTrend.map(m => ({ mes: m, ...kpiFor(m) })),
    gastosTotalesActual: areaVals(mesActual, 'gastosTotalesRow'),
    gastosTotalesAnterior: mesAnterior ? areaVals(mesAnterior, 'gastosTotalesRow') : null,
    impuestosActual: areaVals(mesActual, 'impuestosRow'),
    ingresosPorAreaActual: ingresosPorArea(mesActual),
    directosIndirectosActual,
    dolarMEP,
    rubrosVariacion,
    proveedores,
    unitEconomics,
    excepciones,
  };
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  console.error(`OK. Mes actual: ${mesActual}${mesAnterior ? ', anterior: ' + mesAnterior : ' (sin mes anterior -- es el primero cargado)'}. Guardado en ${outPath}`);
})().catch(e => { console.error('FATAL:', e); process.exit(1); });
