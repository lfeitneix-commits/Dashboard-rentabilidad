// Asistente de controlling de Neix S.A. -- usa function calling de Claude
// (Anthropic): en vez de mandarle de antemano "todo lo que parece
// relevante" (lo que hacía la primera versión, y por eso siempre
// terminaba faltando algún dato), el modelo pide la herramienta puntual
// que necesita y el dashboard la ejecuta del lado del cliente (ver
// ejecutarHerramientaChatIA en index.html) -- los datos viven en el
// browser, esta función nunca los toca directamente, solo hace de
// puente hacia la API de Claude.
const SYSTEM_PROMPT = `Sos CELIA, la asistente de controlling de Neix S.A. Trabajás para el área de Finanzas / Controlling y te usan analistas y la gerencia para entender la rentabilidad del negocio y tomar decisiones de costos.

## Sobre Neix
Neix S.A. es una ALyC (Agente de Liquidación y Compensación) y ACyDI (Agente de Colocación y Distribución Integral) argentina, regulada por la CNV, que opera en el mercado de capitales argentino (BYMA, MAE). Sus ingresos vienen principalmente de aranceles y comisiones por operaciones de clientes (comitentes), fees por colocación de ON en licitaciones, operaciones de cartera propia y caución, FCI y servicios a clientes institucionales y corporativos. Las órdenes se cargan en Nexos, el sistema propio de Neix.

## Áreas comerciales (generan ingresos)
- Mesa: trading, cartera propia, caución y operaciones de mercado. Es el área con más facturación y la más volátil. Líder: Nacho.
- FAs + Mza: red de asesores financieros (productores) externos, incluida la oficina de Mendoza. Su principal costo directo son las Comisiones Productores que se les pagan a los asesores. Líder: Sole. El alquiler de la oficina de Mendoza es el proveedor "DEI S.A." dentro de la cuenta Alquileres y Expensas (no tiene fila propia en la hoja, va junto con el resto de Alquileres y Expensas de FAs).
- Banca Corporativa: empresas e institucionales.
- Banca Privada: clientes individuales de alto patrimonio. Líder: Nicanor.
Capital N tiene su propio estado de resultados (pestaña CAPITAL N), separado de Neix.

## Áreas de soporte (generan costos que se prorratean)
Headcount aproximado: Operaciones/Back Office 17, Mesa 21, Administración 5, RRHH 2, Banca Privada 4, Banca Corporativa 6, Middle Office 5, Tecnología/IT 9, General 2, Marketing 2, Performance 2.
Performance es un equipo de análisis de datos y desarrollo, no de performance de inversiones.

## Estructura del EERR por área (en USD, una pestaña por mes y una CONSOLIDADO)
1. FACTURACIÓN BRUTA: ingresos de cada área. La de Mesa ya viene neta de aranceles de mercado, intereses pagados (costo financiero de cauciones), alquileres de comitentes, servicios de corretaje, gastos de conversión de CEDEAR y Caja de Valores. Esos montos figuran como referencia en notas, pero no hay que restarlos de nuevo.
2. GASTOS DIRECTOS: costos asignados 100% a un área. Incluyen sueldos y cargas del área, servicios contratados propios (por ejemplo Bloomberg en Mesa), hardware, representación, gastos de trading y Comisiones Productores (FAs).
3. SUBTOTAL DIRECTOS: facturación menos gastos directos. Es el margen directo del área.
4. GASTOS INDIRECTOS: costos de soporte prorrateados entre las 4 áreas comerciales. Incluyen sueldos de Back, Administración, RRHH, IT, General, Marketing y Performance; alquileres y expensas; telefonía; gastos generales de oficina; tecnología y software; servicios contratados (asesor PLAFT, proveedores de sistemas, etc.); membresías/regulatorio (Cámara de agentes); administración/consultoría; gastos bancarios y de corresponsales del exterior; marketing; afters y eventos; donaciones; honorarios profesionales.
5. Egresos Varios.
6. RESULTADO antes de impuestos.
7. Impuestos: Ingresos Brutos, Ley 25.413 (impuesto a los débitos y créditos), Ganancias, IVA no computable, sellos, tasas municipales y otros. El IVA no computable suele ser el más grande.
8. RESULTADO después de impuestos.
Cada mes se convierte de ARS a USD con el dólar MEP del cierre de ese mes.

## Criterios de prorrateo de gastos indirectos
Destinos: Mesa, FAs + Mza, Banca Corporativa y Banca Privada.
- Headcount: criterio por defecto (RRHH, IT, Administración, General, alquileres, sueldos generales, servicios, seguros y gastos generales de oficina). Cuenta todas las áreas de Neix, no solo las comerciales.
- Ratio de comitentes activos: tasas CNV, membresías/regulatorio, gastos bancarios y financieros, intereses y multas impositivos, representación.
- Back Office: proporción de operaciones de cada área sobre el total.
- IT: se separa en IT Infraestructura e IT Sistemas.
- Performance: 75% por ratio de comitentes y 25% según los proyectos hechos para cada área.
- Marketing: 75% por ratio de comitentes y 25% al resto de Neix por headcount.
- Certificaciones y legalizaciones: 100% Banca Privada.
- Donaciones: no se prorratean.
Algunos criterios están en revisión. Si una conclusión depende mucho del criterio de asignación, aclaralo.

## Relación con contabilidad
La contabilidad oficial está en ARS y usa el plan de cuentas (ingresos en 4.1.x, gastos en 4.2.x). En los mayores contables, los ingresos aparecen con signo negativo (saldo acreedor). El CDC puede diferir de contabilidad por metodología de ingresos, por tipo de cambio y por cómo se netean los costos de Mesa. Si te preguntan por diferencias, mencioná estas causas como posibles.

## Indicadores (usá siempre estas fórmulas)
- Margen directo = Subtotal Directos / Facturación Bruta.
- Margen antes de impuestos = Resultado antes de impuestos / Facturación Bruta.
- Margen neto = Resultado después de impuestos / Facturación Bruta.
- Peso de indirectos = Gastos Indirectos / Facturación Bruta.
- Ratio de comisiones FAs = Comisiones Productores / Facturación Bruta de FAs.
- Participación de un área = Facturación del área / Facturación total.
- Variación mensual = mes actual vs. mes anterior. Acumulado (YTD) = suma de enero al último mes disponible.
- Para tendencias, compará contra el promedio de los últimos 3 meses además del mes anterior.
Si la facturación de un área es negativa o casi cero, no calcules márgenes porcentuales (no tienen sentido): mostrá solo valores absolutos y aclaralo.

## Contexto para analizar
- Argentina tiene inflación y tipo de cambio variable: una variación en USD puede deberse al MEP y no a un cambio real de actividad. Cuando una variación sea grande, considerá si puede ser efecto cambiario.
- La facturación de Mesa depende del mercado y puede ser negativa en un mes (por ejemplo, por resultados de cartera propia). No lo trates como error de datos; señalalo y analizá el impacto en el total.
- Los sueldos tienen picos estacionales: aguinaldo en junio y diciembre, y bonos en enero y julio. No los confundas con aumentos de estructura.
- Los ingresos de colocaciones dependen de las licitaciones del mes. Los costos de estructura (sueldos, alquiler, tecnología) son más fijos. No saques conclusiones de tendencia con un solo mes.
- Identificá gastos extraordinarios o no recurrentes y separalos del análisis de tendencia.
- Un área puede tener buen margen directo y mal resultado final por el peso de los indirectos. Distinguí siempre los dos cuando sea relevante.
- En FAs, mirá la relación entre Comisiones Productores y facturación: es el principal driver de su margen.
- Cuando algo no cierra (totales que no suman, saltos fuera de escala o una cuenta en cero que suele tener valor), marcalo como posible inconsistencia de carga, no como conclusión de negocio.

## Lo que hacés
- Respondés preguntas sobre los datos que recibís como contexto en cada consulta.
- Armás reportes y comparativos con el formato de abajo.
- Das sugerencias concretas: desvíos, costos que crecen más que los ingresos, áreas que mejoran o empeoran, gastos que convendría revisar y posibles inconsistencias en los datos. Presentalas como puntos a analizar, no como decisiones.

## Formato de reportes
Cuando te pidan un reporte de un área o de Neix:
1. Resumen: 2 o 3 líneas con lo más importante del período.
2. Números clave: tabla con Facturación, Gastos Directos, Margen Directo, Gastos Indirectos, Resultado antes y después de impuestos, con variación vs. período anterior (en USD y %).
3. Qué explica la variación: los 3 rubros que más movieron el resultado, con su monto.
4. Puntos a revisar: máximo 3, concretos.

## Formato de comparativos
- Entre áreas: tabla con una columna por área y una fila por línea del EERR, más una fila de margen directo % y margen neto %.
- Entre períodos: tabla con una columna por período, más variación absoluta y %.
- Debajo de la tabla, máximo 3 líneas de conclusión.

## Cómo respondés
- Por defecto sos BREVE: 1 a 4 líneas. Nada de preámbulo, nada de recordar contexto de negocio que no se pidió, nada de disclaimers salvo que sean el punto de la pregunta. Los 4 puntos de "Formato de reportes" y "Formato de comparativos" de arriba son SOLO para cuando te piden explícitamente un reporte, un análisis o una comparación -- no los uses de más ni "por las dudas".
- En español rioplatense, directo y conciso, sin introducciones ni relleno.
- Si la pregunta es puntual (un número, un dato), respondé solo eso en una línea, sin tabla ni contexto alrededor.
- Usá tablas cuando compares más de tres números Y te hayan pedido un reporte o comparativo -- no para una respuesta puntual.
- Formato numérico: coma para miles y punto para decimales (USD 1,250,000.50). En tablas y resúmenes redondeá a miles cuando sea más claro (USD 1,250k) y aclaralo. Porcentajes con un decimal.
- Siempre aclará la moneda y el período.
- Usá la terminología del negocio: comitentes, EERR, prorrateo, margen directo, resultado final, MEP.
- Si un dato no está en el contexto, decilo. Nunca inventes ni estimes números.
- Si falta el período, usá el más reciente disponible y aclaralo en una línea.
- Solo hablás de los datos que recibís. Si te preguntan por un área o información que no está en el contexto, decí que no tenés acceso a eso.
- No das recomendaciones de inversión ni opinás sobre personas: analizás números.

## Cómo conseguís los datos
No tenés los números de memoria: los pedís con las herramientas disponibles (KPIs de un mes o consolidado, evolución mensual, ranking de rubros, datos de un área puntual con sus sueldos/fijos/rubros directos, evolución de rubros, gastos y ranking por proveedor, Capital N y su volcado completo, Quant, matriz de prorrateo, tipo de cambio MEP). Para un reporte o comparativo llamalas las veces que haga falta (varios meses, varias áreas) antes de responder, en vez de contestar con lo primero que conseguiste. Nunca des un número sin haberlo consultado primero en esta misma conversación.
NUNCA le digas al usuario que no tenés un dato sin antes haber probado los volcados completos disponibles: obtener_eerr_completo (TODAS las filas del EERR de Neix de un mes, con sus notas), obtener_gastos_fijos_completo (si es sobre proveedores o gastos fijos), obtener_capital_n_completo (si es sobre Capital N), obtener_quant_completo (si es sobre Quant) u obtener_matriz_prorrateo (si es sobre cómo se reparte un gasto indirecto entre áreas). Son el respaldo para cualquier pregunta puntual que las demás herramientas no cubran. Solo si después de revisar esos volcados el dato realmente no está, decí que no está disponible.
Si piden el reporte/PDF/informe de un mes puntual (no un análisis armado por vos, sino EL ARCHIVO), usá obtener_reportes_disponibles y respondé con un link markdown [texto](archivo) al PDF real -- tu respuesta puede llevar links así, se muestran como un botón clickeable.
Si un monto agregado del EERR mezcla varias cosas y no podés separarlas con las otras herramientas (ej. una cuenta de gasto que junta dos viajes distintos, o cualquier "no sé exactamente cuánto es de X"), probá obtener_mayor_contable antes de darte por vencida: es el movimiento por movimiento de la contabilidad real, buscable por texto en el concepto (ej. "ushuaia"), mucho más granular que cualquier otra herramienta.
Una búsqueda por texto (concepto, proveedor, cuenta) que no encuentra nada NO es la respuesta final -- quien carga la contabilidad abrevia, saca tildes o corta nombres (ej. "Ushuaia" puede estar cargado como "Ush"; "Sofía" como "Sofia"; un proveedor largo, recortado). Antes de decir que no encontraste algo, reintentá vos mismo con variantes razonables (menos letras, sin tildes, una palabra en vez de la frase completa, sinónimos) -- probá 2 o 3 antes de rendirte. Esto aplica en especial a obtener_mayor_contable y buscar_gasto_por_proveedor.`;

const MODELO = "claude-sonnet-5-5";

// Cada herramienta se declara acá (nombre + parámetros, para que Claude
// sepa cuándo y cómo pedirla) pero se EJECUTA del lado del dashboard
// (ejecutarHerramientaChatIA en index.html) -- esta función solo reenvía
// el pedido y la respuesta entre el frontend y Claude.
const TOOLS = [
  {
    name: "obtener_kpis_mes",
    description:
      "De toda la compañía (sumando las áreas visibles para este usuario) en un mes puntual: ingresos " +
      "(Facturación Bruta), gastosDirectos, gastosIndirectos, egresos (Directos + Indirectos), impuestos, " +
      "resultadoAntesImpuestos y resultado (después de impuestos). Para el total de todos los meses cargados, " +
      "usar mes=\"__consolidado__\".",
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
      "Serie mensual completa (mismos campos que obtener_kpis_mes: ingresos, gastosDirectos, " +
      "gastosIndirectos, egresos, impuestos, resultadoAntesImpuestos, resultado) de todos los meses " +
      "cargados, sumando las áreas visibles para este usuario. Útil para ver tendencias a lo largo del tiempo.",
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
    name: "obtener_ranking_proveedores",
    description:
      "Ranking de proveedores por monto total acumulado del año (de mayor a menor), para responder 'a qué " +
      "proveedor le pagamos más'. Sale de 'Gastos Fijos - Proveedor x Mes', un subconjunto curado de cuentas " +
      "fijas -- NO incluye rubros que no se cargan por proveedor (Sueldos y CS, Comisiones Productores, " +
      "Impuestos). No disponible para líderes de área.",
    input_schema: {
      type: "object",
      properties: {
        anio: {
          type: "string",
          enum: ["actual", "2025"],
          description: "Año a buscar: \"actual\" (año en curso) o \"2025\" (cerrado). Default \"actual\".",
        },
      },
    },
  },
  {
    name: "obtener_evolucion_rubros",
    description:
      "Evolución mes a mes de TODOS los rubros de gasto de la compañía (uno al lado del otro, no uno por " +
      "uno) -- pensada para detectar tendencias y comparar varios rubros/meses de una sola llamada, por " +
      "ejemplo para sugerir dónde se podría ahorrar. No disponible para líderes de área.",
    input_schema: { type: "object", properties: {} },
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
  {
    name: "obtener_datos_area",
    description:
      "Datos de UNA sola área (Mesa, FAs, Banca Corporativa o Banca Privada) en un mes puntual o " +
      "\"__consolidado__\": ingresos (Facturación Bruta), gastosIndirectos, egresos, impuestos, " +
      "resultadoAntesImpuestos y resultado (después de impuestos) -- estos 6 YA incluyen el prorrateo de " +
      "gastos indirectos entre las 4 áreas -- más gastosDirectos, resultadoDirecto, fijos (costos fijos " +
      "directos), sueldosTotal (sueldos y CS directos) y topRubrosDirectos (ranking) -- estos 5 son SOLO lo " +
      "que esa área gasta directamente, sin ese prorrateo. Usar esta herramienta (no obtener_kpis_mes ni " +
      "obtener_ranking_rubros, que son de toda la compañía) para cualquier pregunta sobre sueldos, gastos, " +
      "impuestos o resultado de un área puntual. Para un líder de área, solo devuelve datos de su propia " +
      "área (si pide otra, da error).",
    input_schema: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Nombre del mes en español (ej. \"Agosto\") o \"__consolidado__\"" },
        area: { type: "string", enum: ["Mesa", "FAs", "Banca Corporativa", "Banca Privada"] },
      },
      required: ["mes", "area"],
    },
  },
  {
    name: "obtener_tipo_cambio",
    description:
      "Dólar MEP de cierre de un mes puntual, o de todos los meses cargados si se pasa \"__consolidado__\" -- " +
      "el tipo de cambio que usa el EERR para convertir de ARS a USD. Usar esta herramienta para cualquier " +
      "pregunta sobre qué tipo de cambio o cotización se usó en un mes.",
    input_schema: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Nombre del mes en español (ej. \"Septiembre\") o \"__consolidado__\"" },
      },
      required: ["mes"],
    },
  },
  {
    name: "obtener_eerr_completo",
    description:
      "Volcado COMPLETO de todas las filas del EERR de un mes puntual, en el mismo orden que la hoja -- " +
      "incluye absolutamente todo: secciones, cuentas, subcuentas, subtotales, impuestos, resultados, notas. " +
      "Usar esta herramienta cuando una pregunta puntual sobre un mes no esté cubierta por ninguna otra " +
      "herramienta más específica, en vez de responder que no tenés el dato. Sin \"area\" devuelve el " +
      "consolidado de la compañía (columna Total); un líder de área solo puede pedir su propia área.",
    input_schema: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Nombre del mes en español (ej. \"Septiembre\")" },
        area: { type: "string", enum: ["Mesa", "FAs", "Banca Corporativa", "Banca Privada"] },
      },
      required: ["mes"],
    },
  },
  {
    name: "obtener_gastos_fijos_completo",
    description:
      "Volcado COMPLETO de 'Gastos Fijos - Proveedor x Mes': todas las cuentas, con TODOS sus proveedores y " +
      "sus montos mes a mes (no solo un ranking o una búsqueda puntual). Usar cuando se necesite comparar o " +
      "listar varios proveedores a la vez, o cuando buscar_gasto_por_proveedor / obtener_ranking_proveedores " +
      "no alcancen. No disponible para líderes de área.",
    input_schema: {
      type: "object",
      properties: {
        anio: {
          type: "string",
          enum: ["actual", "2025"],
          description: "Año a traer: \"actual\" (año en curso) o \"2025\" (cerrado). Default \"actual\".",
        },
      },
    },
  },
  {
    name: "obtener_capital_n_completo",
    description:
      "Volcado COMPLETO de todas las filas del EERR de Capital N (Facturación, cada rubro de gasto, " +
      "Resultado) de un mes puntual o consolidado -- no solo el agregado de obtener_capital_n. Solo " +
      "disponible para acceso completo o Banca Privada.",
    input_schema: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Mes en español, o vacío/\"__consolidado__\" para el total" },
      },
    },
  },
  {
    name: "obtener_quant_completo",
    description:
      "Costos de Quant (centro de costo de trading cuantitativo, no factura): costo laboral, servicios de " +
      "infraestructura y hardware de un mes puntual o consolidado, más los gastos únicos (obra, FPGA, Codex) " +
      "que no se prorratean por mes. Solo disponible para acceso completo o líder de Mesa.",
    input_schema: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Mes en español, o vacío/\"__consolidado__\" para el total" },
      },
    },
  },
  {
    name: "obtener_matriz_prorrateo",
    description:
      "Matriz de prorrateo: el PORCENTAJE (no monto) con el que cada rubro de gasto indirecto de la " +
      "estructura común (Back Office, RRHH, IT, Administración, MKTG, Performance, Impuestos, etc.) se reparte " +
      "entre las 4 áreas comerciales. Usar para explicar POR QUÉ un área recibe tal proporción de un gasto " +
      "indirecto. No disponible para líderes de área.",
    input_schema: { type: "object", properties: {} },
  },
  {
    name: "obtener_reportes_disponibles",
    description:
      "Lista de reportes PDF YA GENERADOS y publicados (mes, fecha de generación, ruta del archivo) -- de la " +
      "compañía, de un área puntual o de Capital N. Usar esta herramienta y SOLO esta cuando piden 'el reporte', " +
      "'el PDF' o 'mandame/pasame el informe' de un mes: no generes un resumen con otras herramientas como si " +
      "fuera el reporte, respondé con un link al PDF real. Un líder de área solo puede pedir tipo='area' (y " +
      "siempre le trae la de su propia área, ignora cualquier otra que pida).",
    input_schema: {
      type: "object",
      properties: {
        tipo: {
          type: "string",
          enum: ["empresa", "area", "capital_n"],
          description: "'empresa' (consolidado, default para acceso completo), 'area' o 'capital_n'.",
        },
        area: { type: "string", enum: ["Mesa", "FAs", "Banca Corporativa", "Banca Privada"] },
      },
    },
  },
  {
    name: "obtener_mayor_contable",
    description:
      "Mayor contable: movimiento por movimiento (fecha, mes, concepto, monto en USD), la fuente MÁS granular " +
      "que hay -- más que el EERR o Gastos Fijos Detalle. Usar cuando un monto agregado del EERR mezcla varias " +
      "cosas y hay que separarlas (ej. 'cuánto de la cuenta Viajes es un viaje puntual'): buscá por texto en " +
      "'concepto' (ej. 'ushuaia') con o sin 'cuenta'. IMPORTANTE: para 'cuánto gastamos en X este año' o " +
      "cualquier pregunta que no sea de un mes puntual, usá mes='__consolidado__' UNA sola vez -- NUNCA la " +
      "llames mes por mes en un loop, se te acaban las vueltas de herramientas antes de poder responder. Sin " +
      "'cuenta' ni 'concepto', devuelve solo la lista de cuentas disponibles (para no traer todo el mayor de " +
      "una). No disponible para líderes de área.",
    input_schema: {
      type: "object",
      properties: {
        mes: { type: "string", description: "Nombre del mes en español (ej. \"Junio\"), o \"__consolidado__\" para buscar en todos los meses cargados a la vez" },
        cuenta: { type: "string", description: "Nombre (o parte) de una cuenta del mayor, ej. \"Gastos de Viajes Mesa\"" },
        concepto: { type: "string", description: "Texto a buscar dentro del concepto de cada movimiento, ej. \"ushuaia\"" },
      },
      required: ["mes"],
    },
  },
];

function herramientasPermitidas(rol) {
  const esArea = !!(rol && rol.esArea);
  const area = rol && rol.area;
  return TOOLS.filter((t) => {
    if (
      [
        "obtener_ranking_rubros",
        "buscar_gasto_por_proveedor",
        "obtener_ranking_proveedores",
        "obtener_evolucion_rubros",
        "obtener_gastos_fijos_completo",
        "obtener_matriz_prorrateo",
        "obtener_mayor_contable",
      ].includes(t.name)
    ) {
      return !esArea;
    }
    if (["obtener_capital_n", "obtener_capital_n_completo"].includes(t.name)) {
      return !esArea || area === "Banca Privada";
    }
    if (t.name === "obtener_quant_completo") return !esArea || area === "Mesa";
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

// Separa un buffer de texto SSE (lo que manda Claude con stream:true) en
// eventos "data: {...}" completos -- devuelve el resto del buffer tal cual
// (línea incompleta, a la espera de más bytes del próximo chunk) para no
// perder ni duplicar nada entre lecturas sucesivas del stream.
function extraerEventosSSE(buffer) {
  const lineas = buffer.split("\n");
  const resto = lineas.pop();
  const eventos = [];
  for (const linea of lineas) {
    if (!linea.startsWith("data:")) continue;
    const payload = linea.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    try {
      eventos.push(JSON.parse(payload));
    } catch (e) {
      // línea cortada a la mitad entre dos chunks -- no debería pasar ya
      // que extraerEventosSSE solo procesa líneas completas (separadas por
      // \n), pero un evento mal formado no debe tirar abajo el stream.
    }
  }
  return { eventos, resto };
}

// Reduce un evento de streaming de Claude a los eventos simplificados que
// entiende el frontend (ejecutarHerramientaChatIA/enviarMensajeChatIA en
// index.html): text_delta a medida que se genera cada pedacito de texto,
// tool_use recién cuando terminó de llegar el JSON completo de sus
// argumentos (no se puede ejecutar una herramienta con argumentos a medio
// armar). Separada de la lectura del stream en sí para poder testearla con
// eventos sintéticos, sin pegarle a la red real.
function procesarEventoAnthropicStream(evt, estado, emit) {
  if (evt.type === "content_block_start" && evt.content_block?.type === "tool_use") {
    estado.toolUse = { id: evt.content_block.id, name: evt.content_block.name, inputJson: "" };
  } else if (evt.type === "content_block_delta") {
    if (evt.delta?.type === "text_delta") {
      emit({ type: "text_delta", text: evt.delta.text });
    } else if (evt.delta?.type === "input_json_delta" && estado.toolUse) {
      estado.toolUse.inputJson += evt.delta.partial_json || "";
    }
  } else if (evt.type === "content_block_stop" && estado.toolUse) {
    let args = {};
    try {
      args = estado.toolUse.inputJson ? JSON.parse(estado.toolUse.inputJson) : {};
    } catch (e) {
      args = {};
    }
    emit({ type: "tool_use", name: estado.toolUse.name, args, id: estado.toolUse.id });
    estado.toolUse = null;
  } else if (evt.type === "error") {
    emit({ type: "error", error: evt.error || evt });
  }
}

// Edge Runtime, no el de Node por default -- una función serverless de
// Node en Vercel puede quedarse buffereando toda la respuesta de
// res.write() y entregarla de una sola vez al final (visto en producción:
// el streaming no se notaba, el chat seguía mostrando "Pensando..." hasta
// el final). El Edge Runtime corre sobre Web Streams de verdad, que es lo
// que garantiza que cada chunk llegue al navegador a medida que se escribe
// y no recién al cerrarse la respuesta.
export const config = { runtime: "edge" };

const jsonError = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

export default async function handler(req) {
  if (req.method !== "POST") return jsonError(405, { error: "Method not allowed" });

  let payload;
  try {
    payload = await req.json();
  } catch (e) {
    return jsonError(400, { error: "Body inválido (se esperaba JSON)." });
  }
  const { turnos, rol } = payload || {};
  if (!Array.isArray(turnos) || turnos.length === 0) {
    return jsonError(400, { error: "Falta 'turnos' (array de turnos de la conversación)." });
  }

  const messages = turnosAClaude(turnos);
  const tools = herramientasPermitidas(rol);

  // Tope de tiempo -- sin esto, una respuesta lenta puede quedar colgando
  // hasta el límite de duración de la función en vez de devolver un error
  // legible.
  const TIMEOUT_MS = 25000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let r;
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
        max_tokens: 2048,
        system: SYSTEM_PROMPT,
        messages,
        tools,
        // Un análisis/reporte puede necesitar varias herramientas, pero de a
        // una por vuelta -- el frontend (enviarMensajeChatIA) solo sabe
        // ejecutar y reenviar un tool_result a la vez.
        tool_choice: { type: "auto", disable_parallel_tool_use: true },
        // Streaming: el frontend va mostrando el texto a medida que se
        // genera, en vez de quedarse en "Pensando..." hasta tener la
        // respuesta completa.
        stream: true,
      }),
      signal: controller.signal,
    });
  } catch (e) {
    clearTimeout(timeoutId);
    console.error("chat.js: timeout/excepción", e.message);
    return jsonError(504, { error: `Timeout o error de red: ${e.message}` });
  }

  if (!r.ok) {
    clearTimeout(timeoutId);
    let data = null;
    try {
      data = await r.json();
    } catch (e) {
      // sin body de error legible -- se informa igual con lo que haya
    }
    console.error(`chat.js: Claude devolvió ${r.status}`, JSON.stringify(data));
    return jsonError(r.status, { error: data });
  }

  // A partir de acá la respuesta HTTP ya está comprometida a 200 -- se
  // transmite como NDJSON (una línea = un evento JSON) en vez de un único
  // JSON al final, para que el frontend pueda ir pintando el texto a
  // medida que llega. El ReadableStream se arma acá y se empieza a leer el
  // upstream de Claude recién cuando el runtime pide el primer chunk
  // (start), reenviando cada evento ya reducido apenas llega.
  const encoder = new TextEncoder();
  const estado = { toolUse: null };
  const upstreamReader = r.body.getReader();
  const decoder = new TextDecoder();

  const stream = new ReadableStream({
    async start(streamController) {
      const emit = (obj) => streamController.enqueue(encoder.encode(JSON.stringify(obj) + "\n"));
      let buffer = "";
      try {
        while (true) {
          const { done, value } = await upstreamReader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const { eventos, resto } = extraerEventosSSE(buffer);
          buffer = resto;
          eventos.forEach((evt) => procesarEventoAnthropicStream(evt, estado, emit));
        }
      } catch (e) {
        console.error("chat.js: error leyendo el stream de Claude", e.message);
        emit({ type: "error", error: e.message });
      } finally {
        clearTimeout(timeoutId);
        streamController.close();
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
    },
  });
}

// Exportadas solo para poder testear el parseo/reducción del stream con
// eventos sintéticos, sin pegarle a la red real -- Vercel sigue usando
// únicamente el default export de arriba.
export { extraerEventosSSE, procesarEventoAnthropicStream };
