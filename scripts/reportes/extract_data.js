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
  const kpiForArea = (mes, area) => {
    const d = ST.mesData[mes];
    if (!d) return null;
    const { ingresos, egresos, resultado } = d.agg[area];
    return { ingresos, egresos, resultado };
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
  const resultadoPorArea = (mes) => {
    const d = ST.mesData[mes];
    if (!d) return null;
    return Object.fromEntries(AREAS_.map(a => [a, d.agg[a].resultado]));
  };

  // Notas manuales para explicar variaciones puntuales de una cuenta,
  // proveedor o rubro en un mes específico -- a mano, mismo criterio que
  // EXCEPCION_KEYWORDS/PROVEEDOR_MANUAL_2026 en el dashboard: la hoja no
  // tiene un campo de "motivo" para esto, así que se carga una vez acá y
  // de ahí en más el reporte lo explica solo cada vez que ese nombre
  // aparezca en el top de variación (ya sea porque ese fue el mes alto, o
  // porque el mes de comparación lo fue). Agregar una entrada nueva cada
  // vez que haya un "por qué" real que valga la pena que el reporte
  // mencione en vez de dejarlo en el número pelado.
  const NOTAS_CUENTAS = {
    'Gtos Mant de Oficina': {
      Julio: 'hubo una obra de mantenimiento en la oficina ese mes, que no se repitió después',
    },
  };
  function notaParaCuenta(nombre) {
    const porMes = NOTAS_CUENTAS[nombre];
    if (!porMes) return null;
    if (porMes[mesActual]) return { mes: mesActual, texto: porMes[mesActual] };
    if (mesAnterior && porMes[mesAnterior]) return { mes: mesAnterior, texto: porMes[mesAnterior] };
    return null;
  }

  // Ranking de rubros (Fijo+Variable), mes actual vs anterior -- para "Top
  // rubros que más subieron". Se filtra a rubros con monto > 0 en AMBOS
  // meses (evita el artefacto de "+infinito%" de un rubro que apareció de la
  // nada, y división por cero de uno que desapareció) y, como en
  // proveedores, a que AMBOS meses superen USD 500 -- si no, un rubro casi
  // en cero en el mes base (ej. "IVA No Computable" de 78 a 61.513, un
  // +78.833%) puede salir como "el que más subió" con un % descomunal que
  // no es comparable con el resto de la tabla, aunque el monto actual sí
  // importe en términos absolutos (antes el piso era solo sobre el monto
  // actual, y un caso así pasaba el filtro).
  const RUBRO_MONTO_MIN = 500;

  // Promedio histórico de un rubro (Clasificación de gastos) en los meses
  // PREVIOS a mesActual -- para distinguir "el rubro que más subió en %"
  // de uno que además es un salto atípico en términos absolutos. Un rubro
  // puede dar +292% y aun así estar perfectamente en línea con su propio
  // promedio si el mes base fue inusualmente bajo (caso real: "IVA No
  // Computable" en Agosto 2026 dio +292,7% vs Julio, pero Agosto estaba en
  // línea con el promedio de los 8 meses -- Julio fue el mes atípico, no
  // Agosto). Antes esto se chequeaba a mano para escribir el bullet de
  // "Análisis del mes" vía --bullet; ahora se calcula solo y se suma al
  // bullet automático del rubro que más subió, sin reemplazar NOTAS_CUENTAS
  // (esto es "¿es raro vs su propia historia?", no "por qué pasó").
  const MESES_MIN_HISTORIAL = 3;
  const UMBRAL_DESVIO_HISTORICO = 0.5; // más de 50% por encima/debajo del promedio
  const mesesHistoria = mesesTrend.slice(0, -1); // antes de mesActual
  const rankPorMesHistoria = mesesHistoria.map(m => {
    const porNombre = {};
    APP.getClasifRubrosRanking(m).forEach(r => { porNombre[r.nombre] = r.monto; });
    return porNombre;
  });
  function historialRubro(nombre, actual) {
    if (rankPorMesHistoria.length < MESES_MIN_HISTORIAL) return {};
    const montos = rankPorMesHistoria.map(porNombre => porNombre[nombre] || 0);
    const promedio = montos.reduce((s, v) => s + v, 0) / montos.length;
    if (!promedio) return { historicoMesesCount: montos.length };
    const ratio = actual / promedio;
    const esAtipico = Math.abs(ratio - 1) > UMBRAL_DESVIO_HISTORICO;
    return { promedioHistorico: promedio, ratioVsHistorico: ratio, esAtipico, historicoMesesCount: montos.length };
  }

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
      .filter(r => r.anterior > RUBRO_MONTO_MIN && r.actual > RUBRO_MONTO_MIN)
      .sort((a, b) => b.deltaPct - a.deltaPct)
      .map(r => {
        const nota = notaParaCuenta(r.nombre);
        const conNota = nota ? { ...r, notaManual: nota.texto, notaMes: nota.mes } : r;
        return { ...conNota, ...historialRubro(r.nombre, r.actual) };
      });
  }

  // Mismo ranking que arriba, pero aperturado por área -- "Clasificación de
  // gastos" (la fuente de rubrosVariacion) es un total de TODA la empresa,
  // sin desglose por área, así que esto sale de otra fuente: las filas de
  // ST.mesData[mes].annotated, que sí tienen una columna por área
  // (getAreaVal). Mismo criterio que rubrosVariacion (AMBOS meses por
  // encima de USD 500, no solo el actual) para no listar ruido.
  //
  // Ojo: se usan solo las filas de la sección "GASTOS DIRECTOS" (entre el
  // marcador _kind 'section' con ese nombre y el marcador _kind
  // 'subtotal_dir'), no todo d.annotated. Los "Gastos Indirectos" (y los
  // Impuestos) se reparten entre áreas con un % FIJO por rubro (hoja
  // Matriz, bloque "Cuentas") -- un rubro indirecto que sube/baja en la
  // empresa sube/baja ese mismo % en las 4 áreas a la vez, porque es el
  // mismo número total multiplicado por una proporción constante. Esa
  // variación "aparece" en cada área pero no es específica de ninguna --
  // es un movimiento de la empresa entera, prorrateado. Solo las filas de
  // "GASTOS DIRECTOS" (el costo propio de cada área, no un prorrateo) dan
  // una variación genuinamente distinta por área, que es lo que esta
  // apertura necesita mostrar. Se excluye además el padre de un grupo
  // (_parentId sin _child, ej. "Sueldos y CS Directos", que ya es la suma
  // de "Sueldos y CS Mesa" + "... BC" + "... FAs" + "... BP") para no
  // contar cada rubro agrupado dos veces.
  const RUBRO_AREA_MONTO_MIN = 500;
  function directosLeafRows(mes) {
    const d = ST.mesData[mes];
    if (!d) return [];
    const rows = d.annotated || [];
    const idxDirectos = rows.findIndex(r => r._kind === 'section' && /^GASTOS\s+DIRECTOS$/i.test((r._nom || '').trim()));
    const idxSubtotal = rows.findIndex(r => r._kind === 'subtotal_dir');
    if (idxDirectos < 0 || idxSubtotal < 0) return [];
    return rows.slice(idxDirectos + 1, idxSubtotal).filter(r =>
      (r._kind === 'account' || r._kind === 'subaccount') && (!r._parentId || r._child));
  }
  let rubrosVariacionPorArea = {};
  if (mesAnterior) {
    const leafActual = directosLeafRows(mesActual);
    const leafAnterior = directosLeafRows(mesAnterior);
    AREAS_.forEach(area => {
      const montoActual = {};
      leafActual.forEach(r => { montoActual[r._nom] = (montoActual[r._nom] || 0) + getAreaVal(r, area); });
      const montoAnterior = {};
      leafAnterior.forEach(r => { montoAnterior[r._nom] = (montoAnterior[r._nom] || 0) + getAreaVal(r, area); });
      const nombres = new Set([...Object.keys(montoActual), ...Object.keys(montoAnterior)]);
      const lista = [];
      nombres.forEach(nombre => {
        const anterior = montoAnterior[nombre] || 0;
        const actual = montoActual[nombre] || 0;
        if (anterior > RUBRO_AREA_MONTO_MIN && actual > RUBRO_AREA_MONTO_MIN) {
          lista.push({ nombre, anterior, actual, deltaPct: (actual - anterior) / anterior * 100 });
        }
      });
      lista.sort((a, b) => b.deltaPct - a.deltaPct);
      rubrosVariacionPorArea[area] = lista;
    });
  }

  // Proveedores (Gastos Fijos Detalle) que más variaron mes contra mes --
  // ordenado por |variación %|, no por monto absoluto, para que salten a la
  // vista los cambios bruscos aunque el proveedor no sea de los más caros.
  // Se filtra a que AMBOS meses superen USD 500 -- no solo el actual: por
  // debajo de eso el % puede ser enorme (ej. Slack de 9 a 24) sin que
  // importe en términos absolutos, y un proveedor con un mes base casi en
  // cero da el mismo % descomunal aunque el monto actual sí sea grande.
  //
  // EXCEPCIÓN a ese piso: un proveedor que tenía gasto real (> el piso) el
  // mes anterior y cayó a CERO este mes -- ej. Refinitiv/Bloomberg/NYSE en
  // Agosto 2026, de ~USD 11-14k/mes a 0 -- es justo el caso contrario al
  // que el piso quiere evitar (no es ruido de una base chica, es una baja
  // real y grande), pero el piso lo tapaba igual porque el monto actual
  // (0) nunca supera USD 500. Sin esta excepción, una cancelación de
  // proveedor queda invisible en esta tabla -- solo se ve, si acaso, muy
  // enterrada en el Anexo (y solo si la cuenta llegó a aparecer en "Top
  // rubros" por otro motivo). Acá el % no se calcula con la fórmula
  // normal (dividir por el anterior) -- es, por definición, -100%.
  const PROVEEDOR_MONTO_MIN = 500;
  let proveedores = [];
  // Detalle COMPLETO por cuenta (sin el piso de USD 500 ni el filtro de
  // "ambos meses > 0" de arriba) -- para el "Anexo" del reporte: cuando un
  // rubro de "Top rubros" (general o por área) coincide por nombre con una
  // cuenta de Gastos Fijos Detalle (ej. "Honorarios Profesionales"), el
  // reporte puede mostrar de qué proveedores/conceptos se compone ese
  // monto, no solo el número agregado -- qué se puede mostrar así depende
  // de qué cuentas tengan desglose por proveedor cargado en el Sheet (no
  // todos los rubros de "Clasificación de gastos" lo tienen: por ejemplo
  // "Honorarios por Servicios" y "Honorarios Profesionales" son cuentas
  // DISTINTAS, y solo la segunda tiene este detalle). Se decide qué cuenta
  // mostrar en build_report.py (ahí vive la lista de qué rubros "llamaron
  // la atención" este mes), no acá -- por eso se exporta todo.
  let gastosFijosDetalleCuentas = {};
  const gfd = ST.gastosFijosDetalle;
  if (gfd && mesAnterior) {
    const idxActual = gfd.valCols.indexOf(mesActual);
    const idxAnterior = gfd.valCols.indexOf(mesAnterior);
    if (idxActual >= 0 && idxAnterior >= 0) {
      gfd.cuentas.forEach(cuenta => {
        const detalle = [];
        cuenta.providers.forEach(p => {
          const anterior = p.vals[idxAnterior];
          const actual = p.vals[idxActual];
          proveedores.push({ nombre: p.nombre, cuenta: cuenta.nombre, anterior, actual });
          if (anterior > 0 || actual > 0) detalle.push({ nombre: p.nombre, anterior, actual });
        });
        gastosFijosDetalleCuentas[cuenta.nombre] = detalle.sort((a, b) => b.actual - a.actual);
      });
      proveedores = proveedores
        .filter(p => (p.anterior > PROVEEDOR_MONTO_MIN && p.actual > PROVEEDOR_MONTO_MIN) ||
                     (p.anterior > PROVEEDOR_MONTO_MIN && p.actual <= 0))
        .map(p => ({ ...p, deltaPct: p.actual > 0 ? (p.actual - p.anterior) / p.anterior * 100 : -100 }))
        // Desempate por monto (p.anterior, lo que se dejó de gastar) --
        // un mes con más de una baja a cero empata todas en -100%, y sin
        // esto el orden entre ellas queda a la suerte de en qué orden
        // aparecen en la hoja (no de cuál achicó más plata). Con el
        // desempate, Bloomberg (USD 14k) sale antes que una donación de
        // USD 658 aunque las dos den el mismo -100%.
        .sort((a, b) => Math.abs(b.deltaPct) - Math.abs(a.deltaPct) || b.anterior - a.anterior)
        .map(p => {
          const nota = notaParaCuenta(p.nombre);
          return nota ? { ...p, notaManual: nota.texto, notaMes: nota.mes } : p;
        });
    }
  }

  // Unit economics (cruza la Matriz -- comitentes y empleados por área --
  // con Facturación y Gastos Totales de mesActual). No reimplementa nada
  // que no esté ya en el sheet: solo arma los cocientes. No incluye
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
  // "CUENTAS ABIERTAS" (bloque de la Matriz, debajo de "CÁLCULOS AUX") trae
  // comitentes por MES y por área -- a diferencia de "Comitentes totales"
  // (en CÁLCULOS AUX), que es un único número fijo sin desglose mensual.
  // Se busca la fila de ese mes DESPUÉS del encabezado "CUENTAS ABIERTAS"
  // (no en toda la hoja) para no confundirla con alguna otra fila que por
  // casualidad arranque con el mismo nombre de mes en otro bloque.
  function comitentesPorMes(mes) {
    if (!ST.matrizData) return null;
    const idxHeader = ST.matrizData.findIndex(r => String(Object.values(r)[0] || '').trim() === 'CUENTAS ABIERTAS');
    if (idxHeader < 0) return null;
    for (let i = idxHeader + 1; i < ST.matrizData.length; i++) {
      if (String(Object.values(ST.matrizData[i])[0] || '').trim() === mes) return ST.matrizData[i];
    }
    return null;
  }
  // "Comitentes totales" (CÁLCULOS AUX) queda como respaldo fijo por si
  // "CUENTAS ABIERTAS" todavía no está cargado para ese mes puntual.
  const comitentesFijoRow = matrizAuxRow('comitentes totales');
  const empleadosRow = matrizAuxRow('empleados');
  function unitEconomicsFor(mes) {
    const d = ST.mesData[mes];
    const comitentesRowMes = comitentesPorMes(mes) || comitentesFijoRow;
    if (!d || !comitentesRowMes || !empleadosRow) return null;
    const gastosTotales = d.gastosTotalesRow;
    const ingresosMes = ingresosPorArea(mes) || {};
    // FAs factura bruto, pero una parte de eso (vía "Comisiones
    // Productores", que en el Sheet está cargado como un gasto directo de
    // FAs) se la queda el productor externo, no FAs -- para Unit Economics
    // (facturación "propia" por comitente/empleado) se usa la neta de esa
    // comisión. Solo afecta a FAs: esa cuenta da 0 en las demás áreas.
    const comisionesRow = (d.annotated || []).find(r => r._nom && /^Comisiones\s+Productores$/i.test(r._nom.trim()));
    const comisionesProductoresFAs = comisionesRow ? getAreaVal(comisionesRow, 'FAs') : 0;
    return {
      mes,
      porArea: AREAS_.map(a => ({
        area: a,
        comitentes: matrizAuxVal(comitentesRowMes, a),
        empleados: matrizAuxVal(empleadosRow, a),
        facturacionMes: (ingresosMes[a] || 0) - (a === 'FAs' ? comisionesProductoresFAs : 0),
        // gastoTotal = GASTOS TOTALES del Sheet = Directos + Indirectos
        // prorrateados (no solo el costo directo del área) -- mismo
        // criterio que "Gastos Totales + Impuestos por área".
        gastoTotal: gastosTotales ? getAreaVal(gastosTotales, a) : 0,
      })),
    };
  }
  const unitEconomics = unitEconomicsFor(mesActual);
  // Mismo cálculo mes a mes (Enero..mesActual) para poder comparar la
  // evolución de Unit Economics, igual que ya se hace con Facturación/
  // Gastos/Resultado en "Evolución últimos meses".
  const unitEconomicsTrend = mesesTrend.map(m => unitEconomicsFor(m)).filter(Boolean);

  // Gastos directos vs indirectos por área -- el ratio Gastos/Facturación
  // de "Ratios por área" mezcla costo propio del área (directos) con el
  // prorrateo de la estructura común (indirectos, repartido según la
  // Matriz), y esa mezcla puede ser la mayor parte del ratio en áreas
  // chicas (BC, BP).
  //
  // OJO -- esto NO es d.subtotalRow ("SUBTOTAL DIRECTOS"): esa fila es
  // Facturación Bruta MENOS Gastos Directos (o sea, contribución
  // marginal, no un costo), verificado numéricamente contra las 4 áreas
  // de Agosto. Usarla acá como si fuera "el gasto directo" daba negativo
  // en Mesa (porque su facturación fue negativa ese mes, no por ningún
  // costo) y confundía más de lo que explicaba. El costo directo real es
  // la fila "GASTOS DIRECTOS" (el encabezado de esa sección, _kind
  // 'section' en d.annotated) -- eso sí es un monto de gasto, no un
  // margen, y no debería dar negativo salvo un dato realmente atípico.
  const directosIndirectosPorArea = (mes) => {
    const d = ST.mesData[mes];
    if (!d || !d.indirectosRow) return null;
    const gastosDirectosRow = (d.annotated || []).find(r => r._nom && /^GASTOS\s+DIRECTOS$/i.test(r._nom.trim()));
    if (!gastosDirectosRow) return null;
    return Object.fromEntries(AREAS_.map(a => [a, {
      directos: getAreaVal(gastosDirectosRow, a),
      indirectos: getAreaVal(d.indirectosRow, a),
    }]));
  };
  const directosIndirectosActual = directosIndirectosPorArea(mesActual);

  // Tipo de cambio (MEP) de un mes -- fila "DÓLAR AL <fecha>", que el loader
  // del dashboard corta a propósito (todo lo que sigue a "GASTOS TOTALES"
  // en la hoja es contable/de caja, no entra a ST.mesData). Se vuelve a
  // pedir la hoja cruda de ese mes nomás para sacar ese único valor.
  async function mepDe(mes) {
    const sheetInfo = APP.SHEETS.find(s => s.mes === mes);
    if (!sheetInfo) return null;
    try {
      const res = await fetch(APP.BASE + sheetInfo.gid);
      const text = await res.text();
      const { rows } = APP.parseCSV(text);
      const dolarRow = rows.find(r => /^D[OÓ]LAR/i.test(String(Object.values(r)[0] || '').trim()));
      return dolarRow ? parseNum(Object.values(dolarRow)[1]) : null;
    } catch (e) {
      console.error(`No se pudo obtener el tipo de cambio de ${mes} (no bloqueante):`, e.message);
      return null;
    }
  }
  const dolarMEP = await mepDe(mesActual);

  // Mayor contable detallado (hojas "Gastos MM.26", una por mes -- gid fijo
  // por mes, no cambia) -- fuente más granular que "Gastos Fijos Detalle"
  // (que es una vista curada, por proveedor, de un subconjunto de cuentas
  // "fijas"). Para un rubro que no está en Gastos Fijos Detalle (ej.
  // "Honorarios por Servicios"), este es el único lugar del Sheet donde
  // realmente se puede ver de qué se compone: movimiento por movimiento,
  // con fecha y concepto -- no una tabla de "cuánto es cada mes" (eso ya
  // está en la fila de "Top rubros").
  //
  // Se usa SOLO cuando el nombre de una cuenta del mayor coincide EXACTO
  // (case-insensitive) con un rubro de "Top rubros" -- no se intenta sumar
  // varias cuentas del mayor para "armar" un rubro agregado (ej.
  // "Impuestos" es la suma de varias cuentas del mayor -- Impuesto Ley
  // 25413, IVA No Computable, Impuestos a los Sellos -- adivinar esa
  // agregación acá sería mucho más frágil que simplemente no mostrar
  // nada; igual para rubros con desglose por área en el mayor, ej.
  // "Capacitacion y Cursos" = "Capacit. y Cursos Mesa" + "... BC" + "...
  // Neix", tampoco se agregan). Los montos del mayor están en ARS -- se
  // convierten a USD con el MEP del mes correspondiente; si no se pudo
  // obtener ese tipo de cambio, se omite esta sección para ese mes (no
  // se adivina un monto en USD sin saber el tipo de cambio real). El
  // monto de cada movimiento sale de la diferencia de SALDO entre filas
  // (no de sumar DEBE/HABER a mano): es exactamente lo que ya calculó la
  // hoja, con cualquier convención de signo que use.
  //
  // Se trae mesActual Y mesAnterior (antes solo mesActual) -- para que
  // una cuenta "ledger" (sin fila propia en Gastos Fijos Detalle, ej.
  // "Honorarios por Servicios"/"Gastos Bancarios") pueda mostrar la
  // misma comparación de dos meses que ya tienen las cuentas "providers"
  // en el Anexo, en vez de solo el detalle de mesActual sin nada con qué
  // compararlo.
  const GASTOS_LEDGER_GID = {
    Enero: '504407038', Febrero: '1383245355', Marzo: '460907963', Abril: '617795229',
    Mayo: '1112341850', Junio: '1053178830', Julio: '937435377', Agosto: '373585666',
  };
  async function ledgerDe(mes, mep) {
    const detalle = {};
    if (!mep) return detalle;
    const ledgerGid = GASTOS_LEDGER_GID[mes];
    if (!ledgerGid) return detalle;
    try {
      const res = await fetch(APP.BASE + ledgerGid);
      const text = await res.text();
      const { rows } = APP.parseCSV(text);
      let cuentaActual = null;
      let saldoPrevio = 0;
      rows.forEach(r => {
        const v = Object.values(r);
        const col0 = String(v[0] || '').trim();
        const concepto = String(v[3] || '').trim();
        const mCta = /^Cta:\s*[\d.]+\s+(.+)$/.exec(col0);
        if (mCta) {
          cuentaActual = mCta[1].trim();
          if (!detalle[cuentaActual]) detalle[cuentaActual] = [];
          saldoPrevio = parseNum(v[6]);
          return;
        }
        if (!cuentaActual) return;
        if (!concepto || concepto === 'TOTALES DEL PERIODO') {
          cuentaActual = null;
          return;
        }
        const saldo = parseNum(v[6]);
        const montoArs = saldo - saldoPrevio;
        saldoPrevio = saldo;
        if (montoArs !== 0) {
          detalle[cuentaActual].push({
            fecha: String(v[1] || '').trim(),
            concepto,
            montoUSD: montoArs / mep,
          });
        }
      });
    } catch (e) {
      console.error(`No se pudo obtener el mayor contable de ${mes} (no bloqueante):`, e.message);
    }
    return detalle;
  }
  const gastosLedgerDetalle = await ledgerDe(mesActual, dolarMEP);
  const gastosLedgerDetalleAnterior = mesAnterior ? await ledgerDe(mesAnterior, await mepDe(mesAnterior)) : {};

  // Agrupado por proveedor/concepto -- el mayor contable trae un
  // movimiento por línea (ej. una fila por día para un mismo débito
  // bancario recurrente, cada una con su propio número de comprobante en
  // el CONCEPTO), lo que separaba en decenas de filas algo que es
  // conceptualmente el mismo proveedor pagado varias veces en el mes. Acá
  // se agrupa por un nombre "canónico" (sacando el número de
  // comprobante/factura y cualquier sufijo "TC: NNNN") y se suma el monto
  // de cada mes, para que el Anexo compare "Banco de Valores" (un total
  // por mes) contra sí mismo, igual que ya hace con los proveedores de
  // Gastos Fijos Detalle -- no 15 filas sueltas por 15 días distintos.
  function proveedorCanonico(concepto) {
    const m = /^(COMPRAS|PAGOS)\s+(.+?)\s+\d{1,6}-\d{2,8}\b/i.exec(concepto);
    if (m) return m[2].trim();
    return concepto.replace(/\s*TC:\s*\d+.*$/i, '').trim() || concepto;
  }
  function agruparPorProveedor(itemsAnterior, itemsActual, keyFn = proveedorCanonico) {
    const sumar = items => {
      const m = {};
      (items || []).forEach(it => {
        const key = keyFn(it.concepto);
        m[key] = (m[key] || 0) + it.montoUSD;
      });
      return m;
    };
    const sumAnt = sumar(itemsAnterior);
    const sumAct = sumar(itemsActual);
    const nombres = new Set([...Object.keys(sumAnt), ...Object.keys(sumAct)]);
    return [...nombres]
      .map(nombre => ({ nombre, anterior: sumAnt[nombre] || 0, actual: sumAct[nombre] || 0 }))
      .sort((a, b) => Math.abs(b.actual) - Math.abs(a.actual));
  }
  const cuentasLedger = new Set([...Object.keys(gastosLedgerDetalle), ...Object.keys(gastosLedgerDetalleAnterior)]);
  const gastosLedgerAgrupado = {};
  cuentasLedger.forEach(cuenta => {
    gastosLedgerAgrupado[cuenta] = agruparPorProveedor(gastosLedgerDetalleAnterior[cuenta], gastosLedgerDetalle[cuenta]);
  });

  // Algunos rubros de "Clasificación de gastos" no tienen una cuenta
  // propia en el mayor contable -- están repartidos en una cuenta POR
  // ÁREA, y encima con sufijos que ni siquiera son consistentes de un mes
  // a otro (ej. "Capacit. y Cursos BC" un mes, "Capacit. y Cursos Mesa"
  // otro). Sin esto esos rubros no tenían NINGÚN desglose en el Anexo.
  // Acá se juntan los movimientos de TODAS las cuentas de un mismo rubro
  // (sea cual sea el área/mes) bajo el nombre canónico del rubro, y se
  // agrupan por PROVEEDOR real (mismo criterio que cualquier otra cuenta
  // del Anexo) -- no por área: el Sheet no identifica acá un "proveedor"
  // por área, así que agrupar por a quién se le pagó es lo que explica
  // "en qué se gastó", no solo "en qué área se gastó" (eso ya se ve,
  // aparte, en "Top rubros · por área").
  //
  // "Gastos de Representación" queda afuera a propósito (decisión del
  // usuario): su cuenta "Eventos Empresariales" es demasiado ruidosa para
  // un desglose automático (eventos puntuales, notas truncadas por el
  // Sheet, reversiones/correcciones posteadas con otra nota) -- para ese
  // rubro se muestra solo el total del mes, igual que Impuestos/Sueldos y
  // CS/Comisiones Productores.
  const RUBRO_LEDGER_PREFIJOS = {
    'Capacitacion y Cursos': { re: /^Capacit\.?\s*y\s*Cursos\b/i },
  };
  Object.entries(RUBRO_LEDGER_PREFIJOS).forEach(([canonico, { re, keyFn }]) => {
    const cuentasMatch = [...cuentasLedger].filter(c => re.test(c));
    if (!cuentasMatch.length) return;
    const itemsAnt = cuentasMatch.flatMap(c => gastosLedgerDetalleAnterior[c] || []);
    const itemsAct = cuentasMatch.flatMap(c => gastosLedgerDetalle[c] || []);
    if (!itemsAct.length && !itemsAnt.length) return;
    gastosLedgerAgrupado[canonico] = agruparPorProveedor(itemsAnt, itemsAct, keyFn);
    // Solo para que build_report.py detecte que el rubro SÍ tiene Anexo
    // (ver ledger_por_nombre ahí) -- lo que se muestra es lo de arriba.
    gastosLedgerDetalle[canonico] = itemsAct;
  });

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
    // Mismo kpiTrend pero por área -- para los reportes por área (uno por
    // área y por mes, ver build_report_area.py). Clave = nombre del área,
    // mismo formato que kpiTrend (lista de {mes, ingresos, egresos, resultado}).
    kpiTrendPorArea: Object.fromEntries(AREAS_.map(a => [a, mesesTrend.map(m => ({ mes: m, ...kpiForArea(m, a) }))])),
    gastosTotalesActual: areaVals(mesActual, 'gastosTotalesRow'),
    gastosTotalesAnterior: mesAnterior ? areaVals(mesAnterior, 'gastosTotalesRow') : null,
    impuestosActual: areaVals(mesActual, 'impuestosRow'),
    ingresosPorAreaActual: ingresosPorArea(mesActual),
    resultadoPorAreaActual: resultadoPorArea(mesActual),
    // Solo para detectar un área que PASA a margen negativo este mes (ver
    // "ALERTAS DEL MES" en build_report.py) -- un área chica como Banca
    // Corporativa o Banca Privada corre con margen negativo casi todos los
    // meses por el prorrateo de indirectos, así que marcar "margen
    // negativo" sin más repetiría lo mismo cada reporte. Comparando contra
    // el mes anterior, la alerta solo dispara cuando es un cambio real.
    ingresosPorAreaAnterior: mesAnterior ? ingresosPorArea(mesAnterior) : null,
    resultadoPorAreaAnterior: mesAnterior ? resultadoPorArea(mesAnterior) : null,
    directosIndirectosActual,
    dolarMEP,
    rubrosVariacion,
    rubrosVariacionPorArea,
    proveedores,
    gastosFijosDetalleCuentas,
    gastosLedgerDetalle,
    gastosLedgerDetalleAnterior,
    gastosLedgerAgrupado,
    unitEconomics,
    unitEconomicsTrend,
    excepciones,
  };
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  console.error(`OK. Mes actual: ${mesActual}${mesAnterior ? ', anterior: ' + mesAnterior : ' (sin mes anterior -- es el primero cargado)'}. Guardado en ${outPath}`);
})().catch(e => { console.error('FATAL:', e); process.exit(1); });
