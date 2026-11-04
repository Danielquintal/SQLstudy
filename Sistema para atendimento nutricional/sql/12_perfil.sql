-- Metas do perfil antropométrico de cada paciente (pode rodar mais de uma vez)
SET client_encoding = 'UTF8';

ALTER TABLE paciente ADD COLUMN IF NOT EXISTS meta_gordura_pct numeric;   -- % de gordura alvo: dá o peso sugerido
ALTER TABLE paciente ADD COLUMN IF NOT EXISTS meta_imo numeric;           -- índice músculo-ósseo alvo: dá a massa muscular alvo
