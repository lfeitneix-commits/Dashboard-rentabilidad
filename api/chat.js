export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  const { prompt } = req.body;

  const r = await fetch(
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent",
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
  if (!r.ok) return res.status(r.status).json({ error: data });
  res.status(200).json({ text: data.candidates?.[0]?.content?.parts?.[0]?.text ?? "" });
}
