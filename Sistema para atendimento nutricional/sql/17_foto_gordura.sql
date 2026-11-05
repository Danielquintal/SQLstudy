-- % de gordura estimado por foto com inteligência artificial (ex.: aplicativo Shaped), ao lado das dobras e da
-- bioimpedância. Base: Ferreira et al., npj Digital Medicine 2025 (concordância com DXA: CCC 0,98). Pode rodar mais de uma vez.
-- Desfazer: ALTER TABLE avaliacao DROP COLUMN foto_gordura_pct, DROP COLUMN foto_app;
SET client_encoding = 'UTF8';

ALTER TABLE avaliacao ADD COLUMN IF NOT EXISTS foto_gordura_pct numeric;   -- % de gordura dado pelo aplicativo
ALTER TABLE avaliacao ADD COLUMN IF NOT EXISTS foto_app text;              -- nome do aplicativo usado
