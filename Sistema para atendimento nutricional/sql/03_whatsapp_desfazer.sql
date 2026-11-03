-- Desfaz sql/03_whatsapp.sql: apaga o histórico de contatos e os campos de retorno e bloqueio do paciente
SET client_encoding = 'UTF8';
DROP TABLE IF EXISTS contato;
ALTER TABLE paciente
    DROP COLUMN IF EXISTS retorno_em,
    DROP COLUMN IF EXISTS whatsapp_bloqueado;
