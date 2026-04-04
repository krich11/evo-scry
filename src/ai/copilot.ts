const COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions";
const COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token";

interface CopilotTokenResponse {
  token: string;
  expires_at: number;
}

let cachedToken: string | undefined;
let tokenExpiresAt = 0;

async function getValidToken(token: string | undefined, refreshToken: string | undefined): Promise<string> {
  // If we have a cached token that's still valid (with 60s buffer), use it
  if (cachedToken && Date.now() / 1000 < tokenExpiresAt - 60) {
    return cachedToken;
  }

  // Try refreshing using the GitHub OAuth token
  if (refreshToken) {
    try {
      const response = await fetch(COPILOT_TOKEN_URL, {
        method: "GET",
        headers: {
          "Authorization": `token ${refreshToken}`,
          "Accept": "application/json",
          "User-Agent": "evo-scry/1.0.0",
        },
        signal: AbortSignal.timeout(10_000),
      });

      if (response.ok) {
        const data = (await response.json()) as CopilotTokenResponse;
        cachedToken = data.token;
        tokenExpiresAt = data.expires_at;
        return cachedToken;
      }
    } catch {
      // Fall through to use the static token
    }
  }

  // Fall back to the static token from env
  if (token) {
    return token;
  }

  throw new Error("No valid Copilot token available");
}

export async function chatCopilot(
  prompt: string,
  token: string,
  refreshToken?: string,
): Promise<string> {
  const validToken = await getValidToken(token, refreshToken);

  const response = await fetch(COPILOT_CHAT_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${validToken}`,
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
