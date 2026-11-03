-- Vários planos alimentares por paciente (ex.: dia de treino e dia de descanso). Pode rodar mais de uma vez.
SET client_encoding = 'UTF8';

ALTER TABLE plano_alimentar ADD COLUMN IF NOT EXISTS id serial;
DO $$
BEGIN
    -- a chave deixa de ser o paciente (um plano só) e passa a ser o próprio plano
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'plano_alimentar_pkey'
               AND conrelid = 'plano_alimentar'::regclass
               AND pg_get_constraintdef(oid) LIKE '%(paciente_id)%') THEN
        ALTER TABLE plano_alimentar DROP CONSTRAINT plano_alimentar_pkey;
        ALTER TABLE plano_alimentar ADD PRIMARY KEY (id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS plano_alimentar_paciente_idx ON plano_alimentar (paciente_id, id);
