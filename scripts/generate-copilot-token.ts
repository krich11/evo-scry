#!/usr/bin/env npx tsx

/**
 * GitHub Copilot Token Generation Script
 *
 * Uses the GitHub OAuth Device Flow to authenticate and obtain a Copilot API token.
 * This is the same flow used by copilot.vim and other Copilot integrations.
 *
 * Usage:
 *   npx tsx scripts/generate-copilot-token.ts
 *   # or
 *   npm run generate-token
 *
 * The script will:
 * 1. Request a device code from GitHub
 * 2. Display a URL and user code for you to enter in your browser
 * 3. Poll GitHub until you've authorized the application
 * 4. Exchange the OAuth token for a Copilot API token
 * 5. Print both tokens for use in environment variables
 */

// Copilot's registered OAuth app client ID (public, used by all Copilot clients)
const GITHUB_CLIENT_ID = "Iv1.b507a08c87ecfe98";

interface DeviceCodeResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
}

interface TokenResponse {
  access_token?: string;
  token_type?: string;
  scope?: string;
  error?: string;
  error_description?: string;
}

interface CopilotTokenResponse {
  token: string;
  expires_at: number;
}

async function requestDeviceCode(): Promise<DeviceCodeResponse> {
  const response = await fetch("https://github.com/login/device/code", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: JSON.stringify({
      client_id: GITHUB_CLIENT_ID,
      scope: "copilot",
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to request device code: HTTP ${response.status}`);
  }

  return (await response.json()) as DeviceCodeResponse;
}

async function pollForToken(deviceCode: string, interval: number): Promise<string> {
  const pollInterval = Math.max(interval, 5) * 1000; // minimum 5 seconds

  while (true) {
    await new Promise((resolve) => setTimeout(resolve, pollInterval));

    const response = await fetch("https://github.com/login/oauth/access_token", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
      },
      body: JSON.stringify({
        client_id: GITHUB_CLIENT_ID,
        device_code: deviceCode,
        grant_type: "urn:ietf:params:oauth:grant-type:device_code",
      }),
    });

    const data = (await response.json()) as TokenResponse;

    if (data.access_token) {
      return data.access_token;
    }

    if (data.error === "authorization_pending") {
      process.stderr.write(".");
      continue;
    }

    if (data.error === "slow_down") {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      continue;
    }

    if (data.error === "expired_token") {
      throw new Error("Device code expired. Please run the script again.");
    }

    if (data.error === "access_denied") {
      throw new Error("Authorization was denied by the user.");
    }

    throw new Error(`Unexpected error: ${data.error} — ${data.error_description}`);
  }
}

async function getCopilotToken(githubToken: string): Promise<CopilotTokenResponse> {
  const response = await fetch("https://api.github.com/copilot_internal/v2/token", {
    method: "GET",
    headers: {
      "Authorization": `token ${githubToken}`,
      "Accept": "application/json",
      "User-Agent": "evo-scry/1.0.0",
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Failed to get Copilot token: HTTP ${response.status} — ${body}`);
  }

  return (await response.json()) as CopilotTokenResponse;
}

async function main() {
  console.log("=== evo-scry Copilot Token Generator ===\n");

  // Step 1: Request device code
  console.log("Requesting device authorization...");
  const deviceCode = await requestDeviceCode();

  // Step 2: Prompt user
  console.log("\n┌──────────────────────────────────────────────────┐");
  console.log("│  Open this URL in your browser:                  │");
  console.log(`│  ${deviceCode.verification_uri.padEnd(48)} │`);
  console.log("│                                                  │");
  console.log(`│  Enter this code: ${deviceCode.user_code.padEnd(30)} │`);
  console.log("└──────────────────────────────────────────────────┘\n");
  console.log(`Code expires in ${Math.floor(deviceCode.expires_in / 60)} minutes.`);
  process.stderr.write("Waiting for authorization");

  // Step 3: Poll for token
  const githubToken = await pollForToken(deviceCode.device_code, deviceCode.interval);
  console.log("\n\n✓ GitHub authorization successful!\n");

  // Step 4: Exchange for Copilot token
  console.log("Exchanging for Copilot API token...");
  const copilotToken = await getCopilotToken(githubToken);

  const expiresAt = new Date(copilotToken.expires_at * 1000);
  console.log(`✓ Copilot token obtained! Expires: ${expiresAt.toISOString()}\n`);

  // Step 5: Output
  console.log("═══════════════════════════════════════════════════");
  console.log("Add these to your .env or systemd environment file:");
  console.log("═══════════════════════════════════════════════════\n");
  console.log(`EVOSCRY_COPILOT_TOKEN=${copilotToken.token}`);
  console.log(`EVOSCRY_COPILOT_REFRESH_TOKEN=${githubToken}`);
  console.log(`\n# Token expires: ${expiresAt.toISOString()}`);
  console.log("# Use the refresh token to obtain new Copilot tokens automatically.");
  console.log("# The server will use EVOSCRY_COPILOT_REFRESH_TOKEN to refresh when needed.\n");
}

main().catch((err) => {
  console.error(`\nError: ${(err as Error).message}`);
  process.exit(1);
});
