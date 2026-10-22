const SYSTEM_PROMPT =
  "Sos un asistente de controlling de Neix S.A. Respondés en español rioplatense, de forma directa y concisa. " +
  "Contestás preguntas sobre los datos del dashboard de centro de costos y rentabilidad. " +
  "Si no tenés el dato, decilo; no inventes números.";

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();

  const { messages, context } = req.body || {};
  if (!Array.isArray(messages) || messages.length === 0) {
    return res.status(400).json({ error: "Falta 'messages' (array de {role, text})." });
  }

  const contents = messages
    .filter((m) => m && typeof m.text === "string" && m.text.trim())
    .map((m) => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.text }],
    }));

  let systemText = SYSTEM_PROMPT;
  if (context !== undefined) {
    let contextoTexto;
    try {
      contextoTexto = JSON.stringify(context);
    } catch {
      contextoTexto = String(context);
    }
    systemText += `\n\nDatos actuales cargados en el dashboard (JSON):\n${contextoTexto}`;
  }

  const modelos = ["gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-flash-lite-latest"];
  let ultimoError;
  for (const modelo of modelos) {
    const r = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${modelo}:generateContent`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": process.env.GEMINI_API_KEY,
        },
        body: JSON.stringify({
          contents,
          systemInstruction: { parts: [{ text: systemText }] },
        }),
      }
    );
    const data = await r.json();
    if (r.ok) {
      return res.status(200).json({ text: data.candidates?.[0]?.content?.parts?.[0]?.text ?? "", modelo });
    }
    ultimoError = { status: r.status, data };
    if (r.status !== 503 && r.status !== 429) break;
  }
  res.status(ultimoError.status).json({ error: ultimoError.data });
}
