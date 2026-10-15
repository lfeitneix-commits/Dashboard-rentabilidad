// Dice cuál es el mes que falta reportar, comparando el último mes cargado
// en el Sheet (mesActual de real_data.json, ver extract_data.js) contra
// REPORTES_MENSUALES en index.html. Si ya está generado, no imprime nada
// (stdout vacío) y sale con código 0 -- "nada pendiente" no es un error.
//
// Uso: node mes_pendiente.js real_data.json ../../index.html
const fs = require('fs');
const path = require('path');

const dataPath = process.argv[2] || 'real_data.json';
const indexPath = process.argv[3] || path.join(__dirname, '..', '..', 'index.html');

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
  'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

const data = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));
const html = fs.readFileSync(indexPath, 'utf-8');
const m = /const REPORTES_MENSUALES=(\[[\s\S]*?\]);/.exec(html);
if (!m) throw new Error('No se encontró REPORTES_MENSUALES en ' + indexPath);
const arr = (new Function('return ' + m[1]))();

const generados = new Set(arr.map(r => r.mes.split(' ')[0].toLowerCase()));
const mes = data.mesActual;
if (generados.has(String(mes).toLowerCase())) process.exit(0);

const idx = MESES.indexOf(String(mes).toLowerCase());
if (idx < 0) throw new Error(`Mes "${mes}" no reconocido`);
console.log(JSON.stringify({ mes, nn: String(idx + 1).padStart(2, '0'), slug: mes.toLowerCase() }));
