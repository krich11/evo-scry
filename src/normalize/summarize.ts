import type { SearchResult } from "../providers/types.js";
import { loadConfig } from "../config.js";
import { chatCopilot } from "../ai/copilot.js";
import { chatLocal } from "../ai/local.js";

export async function summarizeResults(
  query: string,
  results: SearchResult[],
): Promise<string | undefined> {
  const top = results.slice(0, 5);
  if (top.length === 0) return undefined;

  const context = top
    .map((r, i) => `${i + 1}. [${r.title}](${r.url})\n   ${r.snippet}`)
    .join("\n\n");

  const prompt = `Summarize the following search results for the query "${query}". Provide a concise 2-3 sentence overview of what the results indicate. Do not include any URLs or links in the summary.\n\nResults:\n${context}`;

  try {
    return await chatWithAI(prompt);
  } catch {
    // AI unavailable — return no summary rather than failing
    return undefined;
  }
}

async function chatWithAI(prompt: string): Promise<string> {
  const config = loadConfig();

  // Try Copilot first
  if (config.copilotToken) {
    try {
      return await chatCopilot(prompt, config.copilotToken);
    } catch {
      // Fall through to local model
    }
  }

  // Try local model
  if (config.localModelUrl) {
    return await chatLocal(prompt, config.localModelUrl, config.localModelName);
  }

  throw new Error("No AI provider configured");
}
