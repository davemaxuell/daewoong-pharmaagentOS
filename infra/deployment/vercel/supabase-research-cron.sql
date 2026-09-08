-- Research only. Does not enable ingestion, case specialists or external delivery.
-- Vault entries: pharma_research_origin and pharma_research_trigger_secret.
BEGIN;
DO $validate$
DECLARE origin text; credential text;
BEGIN
  SELECT decrypted_secret INTO STRICT origin FROM vault.decrypted_secrets
    WHERE name = 'pharma_research_origin';
  SELECT decrypted_secret INTO STRICT credential FROM vault.decrypted_secrets
    WHERE name = 'pharma_research_trigger_secret';
  IF origin <> 'https://pharmaagent-os.vercel.app' OR length(credential) < 32 THEN
    RAISE EXCEPTION 'Configure the exact research origin and strong trigger secret in Vault';
  END IF;
END $validate$;
SELECT cron.schedule('pharma-research-worker', '* * * * *', $job$
  SELECT net.http_post(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets
            WHERE name='pharma_research_origin') || '/internal/worker/research',
    headers := jsonb_build_object('Content-Type', 'application/json', 'Authorization', 'Bearer ' ||
      (SELECT decrypted_secret FROM vault.decrypted_secrets
       WHERE name='pharma_research_trigger_secret')),
    body := '{}'::jsonb, timeout_milliseconds := 220000
  ) WHERE EXISTS (
    SELECT 1 FROM public.research_runs
    WHERE status='queued' OR (status='running' AND lease_expires_at < now())
  );
$job$);
COMMIT;
-- Pause recovery: SELECT cron.unschedule('pharma-research-worker');
-- Disable execution and new tasks: RESEARCH_AGENT_ENABLED=false on Vercel.
