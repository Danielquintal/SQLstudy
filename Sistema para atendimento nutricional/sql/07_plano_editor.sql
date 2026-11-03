-- Planos montados no próprio sistema (editor): a montagem fica guardada para editar depois. Pode rodar mais de uma vez.
SET client_encoding = 'UTF8';
ALTER TABLE plano_alimentar ADD COLUMN IF NOT EXISTS editor jsonb;   -- vazio = plano enviado em PDF
