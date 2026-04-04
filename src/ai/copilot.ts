const COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions";

export async function chatCopilot(prompt: string, token: string): Promise<string> {
  const response = await fetch(COPILOT_CHAT_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
      "Editor-Version": "vscode/1.96.0",
      "Editor-Plugin-Version": "copilot-chat/0.24.0",
      "Openai-Intent": "conversation-panel",
      "Copilot-Integration-Id": "vscode-chat",
    },
    body: JSON.stringify({
      model: "gpt-4o",
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
      max_tokens: 300,
      temperature: 0.3,
    }),
    signal: AbortSignal.timeout(15_000),
  });

  if (!response.ok) {
    throw new Error(`Copilot API returned HTTP ${response.status}`);
  }

  const data = (await response.json()) as {
    choices?: { message?: { content?: string } }[];
  };

  const content = data.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error("Copilot returned empty response");
  }

  return content.trim();
}
