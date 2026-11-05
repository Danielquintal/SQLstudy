-- Meta de passos por dia de cada paciente (aparece na aba Metas diárias da página). Pode rodar mais de uma vez.
-- Desfazer: ALTER TABLE paciente DROP COLUMN meta_passos;
SET client_encoding = 'UTF8';

ALTER TABLE paciente ADD COLUMN IF NOT EXISTS meta_passos integer;   -- vazio = sem meta de passos
