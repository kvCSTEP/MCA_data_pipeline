"""
ONE-TIME SETUP SCRIPT. Run this manually, once, from a machine with a
browser -- NOT inside prefect-serve.

Purpose: perform the single interactive login needed to bootstrap the
headless Teams-notification flow. After this, everything else refreshes
silently (see auth.py).

Steps:
    1. Set AZURE_CLIENT_ID / AZURE_TENANT_ID as env vars (same values
       app/teams/config.py reads).
    2. Run: python get_initial_refresh_token.py
    3. It prints a URL + a short code. Sign in AS THE DEDICATED SERVICE
       MAILBOX ACCOUNT (not your own account) at that URL and enter the
       code.
    4. On success, this script saves the refresh token directly into the
       Prefect Secret block "teams-notifier-refresh-token" -- make sure
       PREFECT_API_URL is pointed at your real server when you run this,
       or it'll save into an ephemeral local server instead.
    5. Confirm the channel can receive a message: this script also sends
       a one-line test post to the configured channel.

Re-run this only if auth.get_access_token() starts raising the
"refresh token acquisition failed" error (e.g. after a password reset
on the service account, or consent being revoked).
"""

import asyncio

import msal
from prefect.blocks.system import Secret
from pydantic import config

from .config import settings
from .notifier import post_standalone

GRAPH_SCOPES = ["ChannelMessage.Send", "Channel.ReadBasic.All"]


def _device_code_login() -> str:
    app = msal.PublicClientApplication(
        client_id=settings.azure_client_id,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
    )
    app._enable_broker=True
    flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device flow: {flow}")

    print(flow["message"])  # "To sign in, use a web browser to open ... and enter code ..."
    print("\nSign in as the DEDICATED SERVICE MAILBOX ACCOUNT, not your own account.\n")

    result = app.acquire_token_by_device_flow(flow)  # blocks until login completes
    if "refresh_token" not in result:
        raise RuntimeError(
            f"Device code login failed ({result.get('error')}): "
            f"{result.get('error_description')}"
        )
    return result["refresh_token"]


async def main() -> None:
    refresh_token = _device_code_login()
    print("-"*10,"refresh token:", refresh_token, "-"*10)
    print('''Share the MS login url and code to Ram. \n He can login and share the secret. Enter th
          Secret in the below box''')
    secret = Secret(value=refresh_token)
    await secret.save("teams-notifier-refresh-token", overwrite=True)
    print("Refresh token saved to Secret block 'teams-notifier-refresh-token'.")

    await post_standalone(
        "✅ Teams notifier setup complete. This is a one-time test message."
    )
    print("Test message posted to the configured channel. Setup done.")


if __name__ == "__main__":
    asyncio.run(main())
