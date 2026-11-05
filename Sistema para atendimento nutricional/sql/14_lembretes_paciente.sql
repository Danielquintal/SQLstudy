-- Lembretes para os pacientes: WhatsApp (você envia pelo Contatos), Telegram e e-mail automáticos e convite no
-- Google Agenda (os automáticos saem pelo script do Google, mesmo com o computador desligado). Pode rodar mais de uma vez.
SET client_encoding = 'UTF8';

-- Telegram: o paciente toca no link com o código e o robô passa a mandar os lembretes para ele
ALTER TABLE paciente
    ADD COLUMN IF NOT EXISTS telegram_codigo  text UNIQUE,
    ADD COLUMN IF NOT EXISTS telegram_chat    text,         -- conversa do paciente com o robô (vazio = não vinculado)
    ADD COLUMN IF NOT EXISTS telegram_desde   timestamp;

CREATE TABLE IF NOT EXISTS lembrete_paciente (
    id            serial PRIMARY KEY,
    paciente_id   integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    texto         text NOT NULL,                    -- mensagem (aceita {primeiro_nome})
    inicio        timestamp NOT NULL,               -- primeira vez
    repetir       text NOT NULL DEFAULT '',         -- '' (uma vez), diario, semanal, quinzenal, mensal
    ate           date,                             -- última data, para os que repetem (vazio = sem fim)
    whatsapp      boolean NOT NULL DEFAULT true,    -- aparece em Contatos para você enviar
    telegram      boolean NOT NULL DEFAULT false,   -- automático
    email         boolean NOT NULL DEFAULT false,   -- automático
    google        boolean NOT NULL DEFAULT false,   -- convite no Google Agenda do paciente
    ativo         boolean NOT NULL DEFAULT true,    -- pausado = false
    whatsapp_ate  timestamp,                        -- última vez já tratada no WhatsApp
    criado_em     timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS lembrete_paciente_pac_idx ON lembrete_paciente (paciente_id);

-- histórico: cada vez que um lembrete saiu (ou falhou) em cada canal
CREATE TABLE IF NOT EXISTS lembrete_envio (
    id           serial PRIMARY KEY,
    lembrete_id  integer NOT NULL REFERENCES lembrete_paciente (id) ON DELETE CASCADE,
    canal        text NOT NULL,                     -- whatsapp, telegram, email
    ocorrencia   timestamp NOT NULL,                -- a vez do lembrete (dia e hora marcados)
    feito_em     timestamp NOT NULL DEFAULT now(),
    erro         text,
    UNIQUE (lembrete_id, canal, ocorrencia)
);
