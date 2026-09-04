-- Persist user-authored saved-view descriptions and enforce owner-scoped names.
-- Apply as the schema owner before deploying the saved-view CRUD endpoints.

BEGIN;

ALTER TABLE public.subscriptions
  ADD COLUMN IF NOT EXISTS description varchar(1000) NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_subscriptions_owner_name
  ON public.subscriptions (owner_id, name);

COMMIT;
