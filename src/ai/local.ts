export async function chatLocal(
  prompt: string,
  baseUrl: string,
  model: string,
): Promise<string> {
  const url = `${baseUrl.replace(/\/$/, "")}/api/chat`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages: [
        {
          role: "system",
          content: "You are a helpful search result summarizer. Be concise and factual.",
        },
        {
          role: "user",
          content: prompt,
        },
      ],
      stream: false,
    }),
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) {
    throw new Error(`Local model returned HTTP ${response.status}`);
  }

  const data = (await response.json()) as {
    message?: { content?: string };
  };

  const content = data.message?.content;
  if (!content) {
    throw new Error("Local model returned empty response");
  }

  return content.trim();
}
