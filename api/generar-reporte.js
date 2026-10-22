// El botón "Generar Reporte" del dashboard necesita disparar el workflow
// de GitHub Actions (.github/workflows/generar-reporte.yml) via la API de
// "workflow dispatch". Llamando a api.github.com directo desde el browser
// esto siempre fallaba por CORS (GitHub no habilita ese origen para
// fetch desde el navegador) y el botón caía siempre al plan B de copiar
// el pedido al portapapeles. Esta función hace el mismo pedido del lado
// del servidor, donde CORS no aplica.
//
// El token vive en la variable de entorno GH_ACTIONS_TOKEN (Vercel) --
// NO hardcodeado acá: con el token como literal en el código, Vercel
// devolvía 401 "Bad credentials" en cada intento aunque el mismo token
// probado directo contra la API de GitHub (fuera de Vercel) respondía
// 204 sin problema. Está acotado SOLO a "Actions: read and write" sobre
// este repo -- no puede leer ni escribir contenido del repo.
// .trim() -- un espacio o salto de línea de más al pegar el valor en
// Vercel (algo fácil de que pase sin querer) rompe el header HTTP y
// tira la función entera con FUNCTION_INVOCATION_FAILED en vez de un
// error legible.
const GH_ACTIONS_TOKEN = (process.env.GH_ACTIONS_TOKEN || "").trim();
const GH_OWNER = "lfeitneix-commits";
const GH_REPO = "Dashboard-rentabilidad";
const GH_WORKFLOW = "generar-reporte.yml";

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  if (!GH_ACTIONS_TOKEN) {
    return res.status(500).json({ error: "Falta la variable de entorno GH_ACTIONS_TOKEN en Vercel." });
  }
  // Diagnóstico temporal (no expone el token, solo su forma) -- sacar
  // apenas se entienda por qué el valor guardado no coincide con el
  // real. Ver generar-reporte.js en el historial de PRs.
  if (req.query && req.query.diag === "1") {
    return res.status(200).json({
      largo: GH_ACTIONS_TOKEN.length,
      primeros6: GH_ACTIONS_TOKEN.slice(0, 6),
      ultimos4: GH_ACTIONS_TOKEN.slice(-4),
      codigosRarosIdx: [...GH_ACTIONS_TOKEN]
        .map((c, i) => ({ i, code: c.codePointAt(0) }))
        .filter((x) => x.code > 126),
    });
  }

  let r;
  try {
    r = await fetch(
      `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/actions/workflows/${GH_WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${GH_ACTIONS_TOKEN}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    );
  } catch (e) {
    console.error("generar-reporte.js: excepción llamando a GitHub", e.message);
    return res.status(500).json({ error: `Excepción llamando a GitHub: ${e.message}` });
  }

  if (r.ok) return res.status(204).end();
  const text = await r.text().catch(() => "");
  console.error(`generar-reporte.js: GitHub devolvió ${r.status}`, text);
  return res.status(r.status).json({ error: text });
}
