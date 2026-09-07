-- Run only on the selected production Supabase project after hosted verification.
-- Enable pg_cron, pg_net, and Vault in Supabase first. Create these Vault entries
-- through the dashboard: pharma_worker_origin (exact HTTPS production origin),
-- pharma_worker_trigger_secret (same as Vercel WORKER_TRIGGER_SECRET).
-- The worker endpoints take no caller-selected job IDs, URLs, or tool arguments.
-- No credential values are stored in cron.job or in source control.
BEGIN;

DO $validate$
DECLARE
  origin text;
  credential text;
BEGIN
  SELECT decrypted_secret INTO STRICT origin FROM vault.decrypted_secrets
    WHERE name = 'pharma_worker_origin';
  SELECT decrypted_secret INTO STRICT credential FROM vault.decrypted_secrets
    WHERE name = 'pharma_worker_trigger_secret';
  IF origin IS NULL OR credential IS NULL
     OR origin !~ '^https://[a-zA-Z0-9.-]+(:[0-9]+)?$' OR length(credential) < 32 THEN
    RAISE EXCEPTION 'Configure an exact HTTPS worker origin and a strong trigger secret in Vault';
  END IF;
END
$validate$;

SELECT cron.schedule('pharma-case-worker', '* * * * *', $job$
  SELECT net.http_post(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets
            WHERE name = 'pharma_worker_origin') || '/internal/worker/cases',
    headers := jsonb_build_object('Content-Type', 'application/json', 'Authorization', 'Bearer ' ||
      (SELECT decrypted_secret FROM vault.decrypted_secrets
       WHERE name = 'pharma_worker_trigger_secret')),
    body := '{}'::jsonb,
    timeout_milliseconds := 270000
  );
$job$);

SELECT cron.schedule('pharma-ingestion-worker', '* * * * *', $job$
  SELECT net.http_post(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets
            WHERE name = 'pharma_worker_origin') || '/internal/worker/ingestion',
    headers := jsonb_build_object('Content-Type', 'application/json', 'Authorization', 'Bearer ' ||
      (SELECT decrypted_secret FROM vault.decrypted_secrets
       WHERE name = 'pharma_worker_trigger_secret')),
    body := '{}'::jsonb,
    timeout_milliseconds := 270000
  );
$job$);
COMMIT;

-- Rollback/pause: SELECT cron.unschedule('pharma-case-worker');
--                SELECT cron.unschedule('pharma-ingestion-worker');
-- Also set SERVERLESS_WORKER_ENABLED=false to reject further triggers.
-- Monitor net._http_response as well as cron.job_run_details: enqueue success
-- alone does not prove the HTTP request or the business job succeeded.
