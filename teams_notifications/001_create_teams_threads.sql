-- teams_threads: one row per TOP-LEVEL pipeline run (master_pipeline1, master_pipeline2, ...)
-- Row is inserted only when that flow's "Running" state is first observed.
-- Sub-flows never insert here; they only look up an existing row via the
-- topmost-ancestor walk (see app/teams/thread_resolver.py).

CREATE TABLE IF NOT EXISTS teams_threads (
    flow_run_id   UUID PRIMARY KEY,          -- Prefect flow_run.id of the top-level run
    flow_name     TEXT NOT NULL,             -- e.g. 'master_pipeline1'
    team_id       TEXT NOT NULL,
    channel_id    TEXT NOT NULL,
    message_id    TEXT NOT NULL,             -- root Teams message id (thread anchor)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fast lookup path used on every state-change event.
CREATE INDEX IF NOT EXISTS idx_teams_threads_flow_run_id ON teams_threads (flow_run_id);
