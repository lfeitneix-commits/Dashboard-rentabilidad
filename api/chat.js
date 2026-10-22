export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  const { prompt } = req.body;
  const modelos = ["gemini-flash-latest", "gemini-flash-lite-latest"];

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
        body: JSON.stringify({ contents: [{ role: "user", parts: [{ text: prompt }] }] }),
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
