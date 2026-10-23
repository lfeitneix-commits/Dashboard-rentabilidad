// Genera el reporte consolidado Y los 4 reportes de área del mes
// pendiente, los valida, y los registra en index.html -- todo en un solo
// paso para que el Action no tenga que ir pasando datos sueltos (mes/nn/
// slug/rutas) de step a step en YAML. Pensado para correr DESPUÉS de
// mes_pendiente.js (si no hay mes pendiente, no se llama a este script).
//
// Uso: node generar_reportes.js <pendiente.json> <real_data.json> <index.html>
//   pendiente.json: lo que imprime mes_pendiente.js -- {mes, nn, slug}
//
// Imprime, en stdout, la lista de archivos tocados (uno por línea) para
// que el workflow haga "git add" con eso.
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const [, , pendienteArg, dataPath, indexPath] = process.argv;
if (!pendienteArg || !dataPath || !indexPath) {
  console.error('Uso: node generar_reportes.js <pendiente.json> <real_data.json> <index.html>');
  process.exit(1);
}
const pendiente = JSON.parse(pendienteArg);
const { mes, nn, slug } = pendiente;
const mesLabel = `${mes} 2026`;
const AREAS = ['Mesa', 'FAs', 'Banca Corporativa', 'Banca Privada'];
const SCRIPT_DIR = __dirname;
const REPO_ROOT = path.join(SCRIPT_DIR, '..', '..');
const fecha = new Date().toISOString().slice(0, 10);
// dataPath/indexPath llegan como argumentos, relativos al cwd de donde se
// invoca este script (mismo criterio que extract_data.js/mes_pendiente.js:
// el workflow corre "cd scripts/reportes" antes) -- se resuelven contra
// process.cwd(), NO contra REPO_ROOT (que es distinto del cwd acá).
const dataPathAbs = path.resolve(dataPath);
const indexPathAbs = path.resolve(indexPath);

function chequearPDF(outRel) {
  const outAbs = path.resolve(REPO_ROOT, outRel);
  if (!fs.existsSync(outAbs) || fs.statSync(outAbs).size === 0) {
    throw new Error(`El PDF no se generó o quedó vacío (${outRel}).`);
  }
  const contenido = fs.readFileSync(outAbs, 'latin1');
  if (contenido.includes('Completar a mano')) {
    throw new Error(`El PDF quedó con un placeholder sin completar, no se sube (${outRel}).`);
  }
}

const archivosTocados = [];

// ── Consolidado ──
const outConsolidado = `reportes/2026-${nn}-reporte-${slug}.pdf`;
execFileSync('python3', [
  'build_report.py', '--data', dataPathAbs, '--out', path.resolve(REPO_ROOT, outConsolidado), '--mes-label', mesLabel,
], { cwd: SCRIPT_DIR, stdio: 'inherit' });
chequearPDF(outConsolidado);
archivosTocados.push(outConsolidado);

// ── Por área ──
const outsPorArea = {};
AREAS.forEach((area) => {
  const areaSlug = area.toLowerCase().replace(/\s+/g, '-');
  const outArea = `reportes/area/2026-${nn}-reporte-${slug}-${areaSlug}.pdf`;
  execFileSync('python3', [
    'build_report_area.py', '--data', dataPathAbs, '--area', area, '--out', path.resolve(REPO_ROOT, outArea), '--mes-label', mesLabel,
  ], { cwd: SCRIPT_DIR, stdio: 'inherit' });
  chequearPDF(outArea);
  outsPorArea[area] = outArea;
  archivosTocados.push(outArea);
});

// ── Registrar todo en index.html (REPORTES_MENSUALES + REPORTES_MENSUALES_AREA) ──
let html = fs.readFileSync(indexPathAbs, 'utf-8');

const filaConsolidado = `  {mes:'${mesLabel}',archivo:'${outConsolidado}',generado:'${fecha}'},\n`;
html = html.replace(/(const REPORTES_MENSUALES=\[[\s\S]*?)(\];)/, (_, cuerpo, cierre) => cuerpo + filaConsolidado + cierre);

AREAS.forEach((area) => {
  const outArea = outsPorArea[area];
  const fila = `    {mes:'${mesLabel}',archivo:'${outArea}',generado:'${fecha}'},\n`;
  // Inserta al final del array de ESTA área puntual dentro de
  // REPORTES_MENSUALES_AREA -- busca el bloque "'Area':[ ... ]," (la coma
  // final del área, no la del objeto REPORTES_MENSUALES_AREA entero) y le
  // agrega la fila antes del cierre "]".
  const areaKeyEsc = area.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`('${areaKeyEsc}':\\[[\\s\\S]*?)(\\],)`);
  if (!re.test(html)) {
    throw new Error(`No se encontró el bloque de REPORTES_MENSUALES_AREA para "${area}" en index.html.`);
  }
  html = html.replace(re, (_, cuerpo, cierre) => cuerpo + fila + cierre);
});

fs.writeFileSync(indexPathAbs, html);
// El workflow hace "git add" desde la raíz del repo -- siempre registramos
// la ruta real de index.html relativa a esa raíz, sin importar cómo haya
// llegado el argumento (relativo al cwd, o absoluto).
archivosTocados.push(path.relative(REPO_ROOT, indexPathAbs));

archivosTocados.forEach((f) => console.log(f));
