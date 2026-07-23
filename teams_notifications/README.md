# Teams thread notifications for master_pipeline runs

Replaces the email notifier. Every `master_pipeline1` / `master_pipeline2`
run gets its own Teams thread; every state change of that run and all its
sub-flow runs (at any depth) is posted as a reply in that same thread.

## 1. Azure AD app registration changes

On the existing app registration (the one already used for NGINX/oauth2-proxy OIDC):

- **Authentication** → enable **"Allow public client flows"** (needed for
  device code login).
- **API permissions** → add, as **Delegated** (not Application):
  - `ChannelMessage.Send`
  - `Channel.ReadBasic.All`
  - `offline_access` is requested automatically by MSAL; no need to add it manually.
- Grant admin consent for the tenant.

Application (client-credentials) permissions will **not** work for this --
Graph rejects app-only tokens for live channel posting outside of tenant
migration scenarios. This is why the flow below uses delegated auth with a
one-time interactive login.

## 2. Create the dedicated service mailbox account

Create (or reuse) a normal M365 user account that will be the "From"
identity for all Teams messages (e.g. `pipeline-bot@yourtenant.com`). Add
it as a member of the target Team/channel.

## 3. Run the schema migration

```
psql "$DATABASE_URL" -f migrations/001_create_teams_threads.sql

From windows machine, run this :
docker cp .\teams_notifications\001_create_teams_threads.sql mca_prefect_db:/tmp/001_create_teams_threads.sql
docker exec -i mca_prefect_db psql -U prefect -d prefect -f /tmp/001_create_teams_threads.sql
```

## 4. One-time interactive login

Run locally (not inside `prefect-serve`), with `PREFECT_API_URL` pointed at
your real Prefect server so the Secret block is saved in the right place:

```
export AZURE_CLIENT_ID=...
export AZURE_TENANT_ID=...
export TEAMS_TEAM_ID=...
export TEAMS_CHANNEL_ID=...
export DATABASE_URL=postgresql://...
export PREFECT_API_URL=http://<your-prefect-server>/api
python -m app.teams.get_initial_refresh_token
```

Sign in **as the service mailbox account** at the printed URL/code. This
saves a refresh token into the Prefect Secret block
`teams-notifier-refresh-token` and posts a one-line test message to confirm
the channel is reachable. You should not need to run this again unless the
service account's password changes or consent is revoked -- after this,
`app/teams/auth.py` refreshes tokens headlessly on every use and persists
the rotated refresh token automatically.

## 5. Env vars for `prefect-serve` (and anything importing `app.teams`)

```
AZURE_CLIENT_ID=...
AZURE_TENANT_ID=...
TEAMS_TEAM_ID=...
TEAMS_CHANNEL_ID=...
DATABASE_URL=postgresql://...        # same Postgres already in the compose stack
PREFECT_UI_BASE_URL=https://prefect.yourdomain   # external URL, through NGINX -- not PREFECT_API_URL
```

## 6. Wire hooks into the five flows

**`master_pipeline1` / `master_pipeline2`** (top-level -- these create the thread):

```python
from app.teams import on_running, on_completion, on_failure, on_crashed, notify_paused

@flow(
    on_running=[on_running],
    on_completion=[on_completion],
    on_failure=[on_failure],
    on_crashed=[on_crashed],
)
def master_pipeline1(...):
    logger = get_run_logger()
    ...
    # wherever you currently call pause_flow_run():
    from prefect.context import get_run_context
    from prefect.flow_runs import pause_flow_run

    flow_run_id = get_run_context().flow_run.id
    await notify_paused(flow_run_id, "master_pipeline1")
    pause_flow_run(...)
```

**`mca_script_run`, `area_calculation`, `spatial_join`, `csv_polygon`**
(sub-flows -- same hooks, no special top-level handling needed, the
dispatcher figures out they're not top-level automatically):

```python
from app.teams import on_running, on_completion, on_failure, on_crashed

@flow(
    on_running=[on_running],
    on_completion=[on_completion],
    on_failure=[on_failure],
    on_crashed=[on_crashed],
)
def spatial_join(...):
    ...
```

That's it -- no thread id is passed through `run_deployment()` parameters.
Each flow resolves its own thread at notification time by walking
`parent_task_run_id` up to whichever top-level run registered a thread.

## 7. Remove the old email path

Once this is verified, remove the Microsoft Graph `sendMail` calls and the
SMTP/Graph mail config from `init_prefect.py` and wherever the notifier was
invoked in the flows.

## Behavior notes

- If a sub-deployment is run manually from the UI (not via
  `master_pipeline1/2`), its topmost-ancestor walk still resolves to
  itself with no thread row found -- it posts a **standalone** message and
  writes nothing to `teams_threads`, so it can't be mistaken for a new
  thread root by later runs.
- Messages carry no error detail, just state + a link to the flow run in
  the Prefect UI, per current requirements.
- `Paused` has no native Prefect flow-level hook; `notify_paused()` must be
  called explicitly at the same call site as `pause_flow_run()`.

![alt text](<Flow State Change-2026-07-20-102734-1.png>)