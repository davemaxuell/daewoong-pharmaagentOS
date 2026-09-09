# Railway backend deployment

The current GitHub deployment guide is [RAILWAY_SETUP.md](../../../RAILWAY_SETUP.md).
It configures an API and a background ingestion/research worker on Railway while
preserving the Vercel website, Supabase database, private evidence bucket and
signed no-login browser sessions.

Use [api.env.example](api.env.example) and [worker.env.example](worker.env.example).
The former staging-only instructions for a Railway web service, new database,
OAuth providers and separate cron service are superseded by this setup.
