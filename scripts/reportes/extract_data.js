// Extrae del Sheet real (vía la lógica real del dashboard, sin reimplementarla)
// los datos que necesita build_report.py para el mes más reciente cargado.
//
// Corre el <script> de index.html directamente en Node (sin navegador): evita
// el problema de que Chromium no confía en el certificado del proxy de este
// entorno, cosa que curl/fetch de Node sí resuelven vía NODE_EXTRA_CA_CERTS.
//
// Uso:
//   NODE_USE_ENV_PROXY=1 node extract_data.js [ruta/a/index.html] > real_data.json
//
// Requiere que el entorno tenga docs.google.com habilitado en Network access
// (si no, ST.meses queda vacío y el script lo avisa en vez de fallar en silencio).
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const indexPath = process.argv[2] || path.join(__dirname, '..', '..', 'index.html');
const outPath = process.argv[3] || path.join(__dirname, 'real_data.json');

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
  const mesActual = meses[meses.length - 1];
  const mesAnterior = meses.length > 1 ? meses[meses.length - 2] : null;
  // Todos los meses cargados -- el Sheet tiene una hoja por mes del año en
  // curso (Enero..mesActual), así que esto ya es "desde principio de año".
  const mesesTrend = meses;

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
  // nada, y división por cero de uno que desapareció).
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
      .filter(r => r.anterior > 0 && r.actual > 0)
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
  // empleados promedio por área -- con Gastos Totales del mes más
  // reciente). No reimplementa nada que no esté ya en el sheet: solo arma
  // los cocientes. No incluye operaciones/comitente: el dato de
  // "Operaciones promedio" de Mesa en la Matriz no es confiable todavía.
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
    const factPromRow = matrizAuxRow('facturación promedio');
    const d = ST.mesData[mesActual];
    if (d && comitentesRow && empleadosRow && factPromRow) {
      const gastosTotales = d.gastosTotalesRow;
      unitEconomics = {
        mes: mesActual,
        porArea: AREAS_.map(a => ({
          area: a,
          comitentes: matrizAuxVal(comitentesRow, a),
          empleados: matrizAuxVal(empleadosRow, a),
          facturacionPromedio: matrizAuxVal(factPromRow, a),
          gastoTotal: gastosTotales ? getAreaVal(gastosTotales, a) : 0,
        })),
      };
    }
  }

  // Excepciones / no recurrentes: la hoja no tiene un flag propio, se infiere
  // de la nota de la cuenta. Lista a mano (ver README de este directorio) --
  // agregar acá cualquier palabra/frase nueva que corresponda a un gasto
  // puntual (viajes, trámites puntuales, obras), no estructural.
  const EXCEPCION_KEYWORDS = [/ushuaia/i, /banco santa fe/i, /obra.*mant.*oficina/i, /mant.*oficina.*obra/i];
  const excepciones = [];
  ST.meses.forEach(m => {
    const d = ST.mesData[m];
    if (!d) return;
    d.annotated.forEach(row => {
      if (row._kind !== 'account' && row._kind !== 'subaccount') return;
      const nota = (row._allNotes || row._note || '').trim();
      if (!nota) return;
      if (!EXCEPCION_KEYWORDS.some(re => re.test(nota))) return;
      const monto = AREAS_.reduce((s, a) => s + getAreaVal(row, a), 0);
      if (!monto) return;
      excepciones.push({ mes: m, cuenta: row._nom, nota, monto });
    });
  });

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
    rubrosVariacion,
    proveedores,
    unitEconomics,
    excepciones,
  };
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  console.error(`OK. Mes actual: ${mesActual}${mesAnterior ? ', anterior: ' + mesAnterior : ' (sin mes anterior -- es el primero cargado)'}. Guardado en ${outPath}`);
})().catch(e => { console.error('FATAL:', e); process.exit(1); });
