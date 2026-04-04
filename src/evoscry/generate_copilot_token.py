#!/usr/bin/env python3
"""Generate a GitHub Copilot refresh token via OAuth Device Flow.

Usage:
    python -m evoscry.generate_copilot_token

The resulting token should be set as EVOSCRY_COPILOT_REFRESH_TOKEN in your
environment or systemd service.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

CLIENT_ID = "Iv1.b507a08c87ecfe98"  # GitHub Copilot VS Code extension
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


def main() -> None:
    # Step 1: Request device code
    print("Requesting device code from GitHub...")
    data = json.dumps({"client_id": CLIENT_ID, "scope": "read:user"}).encode()
    req = urllib.request.Request(
        "https://github.com/login/device/code",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        device = json.loads(resp.read())

    user_code = device["user_code"]
    device_code = device["device_code"]
    verification_uri = device["verification_uri"]
    interval = device.get("interval", 5)
    expires_in = device.get("expires_in", 900)

    print(f"\n1. Open: {verification_uri}")
    print(f"2. Enter code: {user_code}")
    print(f"\nWaiting for authorization (expires in {expires_in}s)...\n")

    # Step 2: Poll for token
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        poll_data = json.dumps({
            "client_id": CLIENT_ID,
            "device_code": device_code,
            "grant_type": GRANT_TYPE,
        }).encode()
        poll_req = urllib.request.Request(
            "https://github.com/login/oauth/access_token",
            data=poll_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(poll_req) as resp:
                result = json.loads(resp.read())
        except Exception as exc:
            print(f"Poll error: {exc}", file=sys.stderr)
            continue

        error = result.get("error")
        if error == "authorization_pending":
            print(".", end="", flush=True)
            continue
        elif error == "slow_down":
            interval += 5
            continue
        elif error:
            print(f"\nError: {error} — {result.get('error_description', '')}", file=sys.stderr)
            sys.exit(1)

        token = result.get("access_token")
        if token:
            print(f"\n\nSuccess! Your Copilot refresh token:\n\n  {token}\n")
            print("Set it in your environment:")
            print(f'  export EVOSCRY_COPILOT_REFRESH_TOKEN="{token}"')
            print("\nOr in your systemd env file:")
            print(f"  EVOSCRY_COPILOT_REFRESH_TOKEN={token}")
            return

    print("\nTimeout — authorization expired.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
