-- Lembretes e mensagens de WhatsApp (pode rodar mais de uma vez)
-- Desfazer: sql/03_whatsapp_desfazer.sql
SET client_encoding = 'UTF8';

ALTER TABLE paciente
    ADD COLUMN IF NOT EXISTS retorno_em          date,                            -- próxima consulta
    ADD COLUMN IF NOT EXISTS whatsapp_bloqueado  boolean NOT NULL DEFAULT false;  -- pediu para não receber mensagens

-- Mensagens de WhatsApp abertas pelo sistema (para não lembrar duas vezes)
CREATE TABLE IF NOT EXISTS contato (
    id           serial PRIMARY KEY,
    paciente_id  integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    tipo         text NOT NULL,      -- retorno, evolucao, aniversario, livre
    referencia   text,               -- ex.: a data do retorno lembrado
    feito_em     timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS contato_paciente_idx ON contato (paciente_id, tipo, feito_em);

-- colunas da primeira versão do check-in (com código), retirada em 03/11/2026; a atual está em 08_checkin.sql
ALTER TABLE paciente DROP COLUMN IF EXISTS checkin_dias, DROP COLUMN IF EXISTS checkin_codigo;
