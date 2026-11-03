/**
 * Google Apps Script Web App que registra y lee los accesos al Dashboard
 * de Rentabilidad (pestaña "Accesos" del dashboard, index.html).
 *
 * CÓMO DESPLEGARLO:
 * 1. Andá a https://sheets.new y creá una hoja de Google en blanco
 *    (dedicada a esto, no hace falta que sea la del dashboard).
 * 2. Extensiones -> Apps Script.
 * 3. Borrá el contenido de Code.gs y pegá este archivo completo.
 * 4. Guardar (Ctrl+S / ícono de disquete).
 * 5. Implementar -> Nueva implementación -> ícono de engranaje -> "Aplicación
 *    web".
 *    - Ejecutar como: Yo (tu cuenta)
 *    - Quién tiene acceso: Cualquier usuario
 * 6. Implementar. Google va a pedir autorizar permisos (es tu propia hoja).
 * 7. Copiá la URL que termina en "/exec" y pegala en index.html, en la
 *    constante ACCESOS_WEBHOOK_URL (buscar "ACCESOS_WEBHOOK_URL=''").
 * 8. Cada vez que cambies este código en Apps Script hace falta un
 *    "Nueva implementación" de nuevo para que el cambio tome efecto (o
 *    "Administrar implementaciones" -> editar -> nueva versión).
 *
 * La hoja "Accesos" se crea sola la primera vez que alguien hace login.
 */

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const sheet = getOrCreateSheet_();
    sheet.appendRow([new Date(), data.area || 'Acceso completo']);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  try {
    const sheet = getOrCreateSheet_();
    const rows = sheet.getDataRange().getValues();
    const out = [];
    // Fila 0 es el header (Fecha, Area) -- se arranca desde la fila 1.
    for (let i = 1; i < rows.length; i++) {
      const [fecha, area] = rows[i];
      if (!fecha) continue;
      out.push({ fecha: new Date(fecha).toISOString(), area: String(area) });
    }
    return ContentService.createTextOutput(JSON.stringify(out))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function getOrCreateSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName('Accesos');
  if (!sheet) {
    sheet = ss.insertSheet('Accesos');
    sheet.appendRow(['Fecha', 'Area']);
  }
  return sheet;
}
