-- Endereço da página do paciente no Cloudflare Pages: https://<projeto>.pages.dev/p/<pagina_token>
-- (aleatório e longo: não dá para adivinhar). Pode rodar mais de uma vez.
-- Desfazer: ALTER TABLE paciente DROP COLUMN pagina_token;
SET client_encoding = 'UTF8';

ALTER TABLE paciente ADD COLUMN IF NOT EXISTS pagina_token text UNIQUE;
