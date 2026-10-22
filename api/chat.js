// Asistente de controlling de Neix S.A. -- usa function calling de Claude
// (Anthropic): en vez de mandarle de antemano "todo lo que parece
// relevante" (lo que hacía la primera versión, y por eso siempre
// terminaba faltando algún dato), el modelo pide la herramienta puntual
// que necesita y el dashboard la ejecuta del lado del cliente (ver
// ejecutarHerramientaChatIA en index.html) -- los datos viven en el
// browser, esta función nunca los toca directamente, solo hace de
// puente hacia la API de Claude.
const SYSTEM_PROMPT =
  "Sos un asistente de controlling de Neix S.A. Respondés en español rioplatense, de forma directa y concisa. " +
  "Contestás preguntas sobre los datos del dashboard de centro de costos y rentabilidad. " +
  "Si no tenés el dato, decilo; no inventes números. " +
  "Tenés herramientas para consultar datos puntuales (KPIs de un mes, evolución mensual, ranking de rubros, " +
  "gastos por proveedor, Capital N): usalas siempre que la pregunta lo requiera, en vez de responder de memoria.";

const MODELO = "claude-sonnet-5-5";

// Cada herramienta se declara acá (nombre + parámetros, para que Claude
// sepa cuándo y cómo pedirla) pero se EJECUTA del lado del dashboard
// (ejecutarHerramientaChatIA en index.html) -- esta función solo reenvía
// el pedido y la respuesta entre el frontend y Claude.
const TOOLS = [
  {
    name: "obtener_kpis_mes",
    description:
      "Ingresos, egresos y resultado de un mes puntual, sumando las áreas visibles para este usuario. " +
      "Para el total de todos los meses cargados, usar mes=\"__consolidado__\".",
    input_schema: {
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
    input_schema: { type: "object", properties: {} },
  },
  {
    name: "obtener_ranking_rubros",
    description:
      "Ranking de rubros de gasto de toda la compañía en un mes puntual, de mayor a menor monto. " +
      "No disponible para líderes de área.",
    input_schema: {
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
    input_schema: {
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
    input_schema: {
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

// Convierte el historial de turnos (provider-agnóstico, lo arma el
// frontend) al formato de `messages` de Claude. Un tool_use de Claude
// lleva un `id` propio que hay que reenviar tal cual en el tool_result
// correspondiente -- el frontend lo guarda en el turno (ver
// enviarMensajeChatIA) y acá se reutiliza como tool_use_id.
function turnosAClaude(turnos) {
  return turnos
    .map((t) => {
      if (t.role === "user" && typeof t.text === "string") return { role: "user", content: t.text };
      if (t.role === "assistant" && typeof t.text === "string") return { role: "assistant", content: t.text };
      if (t.role === "functionCall" && t.name) {
        return {
          role: "assistant",
          content: [{ type: "tool_use", id: t.id, name: t.name, input: t.args || {} }],
        };
      }
      if (t.role === "functionResponse" && t.name) {
        return {
          role: "user",
          content: [{ type: "tool_result", tool_use_id: t.id, content: JSON.stringify(t.response) }],
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

  const messages = turnosAClaude(turnos);
  const tools = herramientasPermitidas(rol);

  // Tope de tiempo -- sin esto, una respuesta lenta puede quedar
  // colgando hasta que Vercel mata la función entera
  // (FUNCTION_INVOCATION_TIMEOUT) en vez de devolver un error legible.
  const TIMEOUT_MS = 20000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let r, data;
  try {
    r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": process.env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: MODELO,
        max_tokens: 1024,
        system: SYSTEM_PROMPT,
        messages,
        tools,
      }),
      signal: controller.signal,
    });
    data = await r.json();
  } catch (e) {
    console.error("chat.js: timeout/excepción", e.message);
    return res.status(504).json({ error: `Timeout o error de red: ${e.message}` });
  } finally {
    clearTimeout(timeoutId);
  }

  if (!r.ok) {
    console.error(`chat.js: Claude devolvió ${r.status}`, JSON.stringify(data));
    return res.status(r.status).json({ error: data });
  }

  const toolUse = (data.content || []).find((b) => b.type === "tool_use");
  if (toolUse) {
    return res.status(200).json({
      functionCall: { name: toolUse.name, args: toolUse.input || {}, id: toolUse.id },
      modelo: MODELO,
    });
  }
  const textBlock = (data.content || []).find((b) => b.type === "text");
  return res.status(200).json({ text: textBlock?.text ?? "", modelo: MODELO });
}
