// El botón "Generar Reporte" del dashboard necesita disparar el workflow
// de GitHub Actions (.github/workflows/generar-reporte.yml) via la API de
// "workflow dispatch". Llamando a api.github.com directo desde el browser
// esto siempre fallaba por CORS (GitHub no habilita ese origen para
// fetch desde el navegador) y el botón caía siempre al plan B de copiar
// el pedido al portapapeles. Esta función hace el mismo pedido del lado
// del servidor, donde CORS no aplica.
const GH_ACTIONS_TOKEN = "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";
const GH_OWNER = "lfeitneix-commits";
const GH_REPO = "Dashboard-rentabilidad";
const GH_WORKFLOW = "generar-reporte.yml";

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();

  const r = await fetch(
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

  if (r.ok) return res.status(204).end();
  const text = await r.text().catch(() => "");
  console.error(`generar-reporte.js: GitHub devolvió ${r.status}`, text);
  return res.status(r.status).json({ error: text });
}
