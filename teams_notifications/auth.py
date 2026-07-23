"""
Delegated-permission auth for posting to Teams channels via Microsoft Graph.

Why delegated, not app-only:
    Microsoft Graph rejects application (client-credentials) tokens for
    posting live channel messages -- POST /teams/{id}/channels/{id}/messages
    returns 401 "allowed in application-only context only for import
    purposes" outside of tenant-migration scenarios. Delegated permissions
    (ChannelMessage.Send) are required.

How this stays headless:
    A one-time interactive device-code login (run manually, see
    get_initial_refresh_token.py) is performed ONCE against a dedicated
    service/bot mailbox account. That yields a refresh token, stored in a
    Prefect Secret block. From then on, every access token is minted via
    MSAL's silent refresh-token flow -- no user interaction. MSAL rotates
    the refresh token on most calls, so the (possibly new) refresh token is
    written back to the same Secret block after every acquisition.

    This keeps working indefinitely unless: the service account's password
    changes, a conditional access / MFA policy starts applying to it, an
    admin revokes consent, or the refresh token goes stale from not being
    used for ~90 days (not a concern here since it's used on every flow
    run).

Required Azure AD app registration settings:
    - "Allow public client flows" = Yes (needed for device code flow)
    - Delegated Graph permissions, admin-consented:
        ChannelMessage.Send
        Channel.ReadBasic.All   (only needed if you resolve team/channel
                                  names to IDs dynamically; skip if IDs are
                                  hardcoded in config)
        offline_access          (implicitly requested by MSAL; grants the
                                  refresh token)
"""

import msal
from prefect.blocks.system import Secret

from .config import settings

REFRESH_TOKEN_SECRET_NAME = "teams-notifier-refresh-token"

# Delegated scopes. offline_access/openid/profile are added automatically
# by MSAL for a public client -- no need to list them explicitly.
GRAPH_SCOPES = ["ChannelMessage.Send", "Channel.ReadBasic.All"]


def _build_msal_app() -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id=settings.azure_client_id,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
    )


async def get_access_token() -> str:
    """
    Returns a valid Graph access token for the service mailbox identity,
    refreshing headlessly via the stored refresh token. Raises RuntimeError
    if the refresh token is no longer valid (needs re-consent, see the
    module docstring above).
    """
    secret_block = await Secret.load(REFRESH_TOKEN_SECRET_NAME)
    refresh_token = secret_block.get()

    app = _build_msal_app()
    result = app.acquire_token_by_refresh_token(refresh_token, scopes=GRAPH_SCOPES)

    if "access_token" not in result:
        raise RuntimeError(
            "Teams notifier: refresh token acquisition failed "
            f"({result.get('error')}): {result.get('error_description')}. "
            "The service account's refresh token likely needs to be "
            "re-issued -- rerun get_initial_refresh_token.py."
        )

    new_refresh_token = result.get("refresh_token")
    if new_refresh_token and new_refresh_token != refresh_token:
        rotated = Secret(value=new_refresh_token)
        await rotated.save(REFRESH_TOKEN_SECRET_NAME, overwrite=True)

    return result["access_token"]
