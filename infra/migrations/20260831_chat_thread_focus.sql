-- Persist server-resolved provenance for a conversation's selected FDA document.
-- Apply as the schema owner before deploying the API focus endpoints.

BEGIN;

CREATE TABLE IF NOT EXISTS public.chat_thread_focus (
  thread_id varchar(36) PRIMARY KEY
    REFERENCES public.chat_threads(id) ON DELETE CASCADE,
  warning_letter_id varchar(36) NOT NULL
    REFERENCES public.warning_letters(id) ON DELETE CASCADE,
  document_id varchar(36) NOT NULL
    REFERENCES public.documents(id) ON DELETE CASCADE,
  document_version_id varchar(36) NOT NULL
    REFERENCES public.document_versions(id) ON DELETE CASCADE,
  source_chunk_id varchar(36) NOT NULL
    REFERENCES public.document_chunks(id) ON DELETE CASCADE,
  source_message_id varchar(36) NOT NULL
    REFERENCES public.chat_messages(id) ON DELETE CASCADE,
  selected_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_chat_thread_focus_warning_letter_id
  ON public.chat_thread_focus (warning_letter_id);
CREATE INDEX IF NOT EXISTS ix_chat_thread_focus_document_id
  ON public.chat_thread_focus (document_id);
CREATE INDEX IF NOT EXISTS ix_chat_thread_focus_document_version_id
  ON public.chat_thread_focus (document_version_id);
CREATE INDEX IF NOT EXISTS ix_chat_thread_focus_source_chunk_id
  ON public.chat_thread_focus (source_chunk_id);
CREATE INDEX IF NOT EXISTS ix_chat_thread_focus_source_message_id
  ON public.chat_thread_focus (source_message_id);
CREATE INDEX IF NOT EXISTS ix_chat_thread_focus_document_version
  ON public.chat_thread_focus (document_version_id, thread_id);

COMMIT;
