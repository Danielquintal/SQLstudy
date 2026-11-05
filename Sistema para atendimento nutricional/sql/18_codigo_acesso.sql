-- Código de acesso (6 números) da página do paciente: login = data de nascimento, senha = este código.
-- A página publicada vai criptografada (AES-256) com eles. Pode rodar mais de uma vez.
-- Desfazer: ALTER TABLE paciente DROP COLUMN codigo_acesso;
SET client_encoding = 'UTF8';

ALTER TABLE paciente ADD COLUMN IF NOT EXISTS codigo_acesso text CHECK (codigo_acesso ~ '^[0-9]{6}$');
