// Asistente de controlling de Neix S.A. -- usa function calling de Gemini:
// en vez de mandarle de antemano "todo lo que parece relevante" (lo que
// hacía la versión anterior, y por eso siempre terminaba faltando algún
// dato), el modelo pide la herramienta puntual que necesita y el
// dashboard la ejecuta del lado del cliente (ver ejecutarHerramientaChatIA
// en index.html) -- los datos viven en el browser, esta función nunca los
// toca directamente, solo hace de puente hacia Gemini.
const SYSTEM_PROMPT =
  "Sos un asistente de controlling de Neix S.A. Respondés en español rioplatense, de forma directa y concisa. " +
  "Contestás preguntas sobre los datos del dashboard de centro de costos y rentabilidad. " +
  "Si no tenés el dato, decilo; no inventes números. " +
  "Tenés herramientas para consultar datos puntuales (KPIs de un mes, evolución mensual, ranking de rubros, " +
  "gastos por proveedor, Capital N): usalas siempre que la pregunta lo requiera, en vez de responder de memoria.";

// Cada herramienta se declara acá (nombre + parámetros, para que Gemini
// sepa cuándo y cómo pedirla) pero se EJECUTA del lado del dashboard
// (ejecutarHerramientaChatIA en index.html) -- esta función solo reenvía
// el pedido y la respuesta entre el frontend y Gemini.
const TOOLS = [
  {
    name: "obtener_kpis_mes",
    description:
      "Ingresos, egresos y resultado de un mes puntual, sumando las áreas visibles para este usuario. " +
      "Para el total de todos los meses cargados, usar mes=\"__consolidado__\".",
    parameters: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Nombre del mes en español (ej. \"Agosto\") o \"__consolidado__\"" },
      },
      required: ["mes"],
    },
  },
  {
    name: "obtener_evolucion_mensual",
    description:
      "Serie mensual completa (ingresos, egresos, resultado) de todos los meses cargados, sumando las áreas " +
      "visibles para este usuario. Útil para ver tendencias a lo largo del tiempo.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "obtener_ranking_rubros",
    description:
      "Ranking de rubros de gasto de toda la compañía en un mes puntual, de mayor a menor monto. " +
      "No disponible para líderes de área.",
    parameters: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Mes en español o \"__consolidado__\"" },
      },
      required: ["mes"],
    },
  },
  {
    name: "buscar_gasto_por_proveedor",
    description:
      "Busca cuánto se le pagó, mes a mes, a un proveedor o cuenta puntual (ej. \"Tanoira\", \"Edenor\", " +
      "\"Santangelo\"). No disponible para líderes de área.",
    parameters: {
      type: "object",
      properties: {
        nombre: { type: "string", description: "Nombre o parte del nombre del proveedor/cuenta a buscar" },
        anio: {
          type: "string",
          enum: ["actual", "2025"],
          description: "Año a buscar: \"actual\" (año en curso) o \"2025\" (cerrado). Default \"actual\".",
        },
      },
      required: ["nombre"],
    },
  },
  {
    name: "obtener_capital_n",
    description:
      "Ingresos/egresos/resultado de Capital N. Si se pasa un mes puntual devuelve ese mes; si no, la " +
      "evolución completa. Solo disponible para acceso completo o Banca Privada.",
    parameters: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Mes en español, o vacío para traer la evolución completa" },
      },
    },
  },
];

function herramientasPermitidas(rol) {
  const esArea = !!(rol && rol.esArea);
  const area = rol && rol.area;
  return TOOLS.filter((t) => {
    if (t.name === "obtener_ranking_rubros" || t.name === "buscar_gasto_por_proveedor") return !esArea;
    if (t.name === "obtener_capital_n") return !esArea || area === "Banca Privada";
    return true;
  });
}

function turnosAGemini(turnos) {
  return turnos
    .map((t) => {
      if (t.role === "user" && typeof t.text === "string") return { role: "user", parts: [{ text: t.text }] };
      if (t.role === "assistant" && typeof t.text === "string") return { role: "model", parts: [{ text: t.text }] };
      if (t.role === "functionCall" && t.name) {
        return { role: "model", parts: [{ functionCall: { name: t.name, args: t.args || {} } }] };
      }
      if (t.role === "functionResponse" && t.name) {
        return {
          role: "function",
          parts: [{ functionResponse: { name: t.name, response: { name: t.name, content: t.response } } }],
        };
      }
      return null;
    })
    .filter(Boolean);
}

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();

  const { turnos, rol } = req.body || {};
  if (!Array.isArray(turnos) || turnos.length === 0) {
    return res.status(400).json({ error: "Falta 'turnos' (array de turnos de la conversación)." });
  }

  const contents = turnosAGemini(turnos);
  const tools = herramientasPermitidas(rol);

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
          systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
          tools: [{ functionDeclarations: tools }],
        }),
      }
    );
    const data = await r.json();
    if (r.ok) {
      const part = data.candidates?.[0]?.content?.parts?.[0];
      if (part?.functionCall) {
        return res
          .status(200)
          .json({ functionCall: { name: part.functionCall.name, args: part.functionCall.args || {} }, modelo });
      }
      return res.status(200).json({ text: part?.text ?? "", modelo });
    }
    ultimoError = { status: r.status, data };
    if (r.status !== 503 && r.status !== 429) break;
  }
  res.status(ultimoError.status).json({ error: ultimoError.data });
}
