-- Agenda de consultas (pode rodar mais de uma vez)
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS consulta (
    id                   serial PRIMARY KEY,
    paciente_id          integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    inicio               timestamp NOT NULL,
    duracao_min          smallint NOT NULL DEFAULT 60,
    modalidade           text NOT NULL DEFAULT 'presencial',   -- presencial | online
    local                text,                                 -- endereço ou link da chamada
    status               text NOT NULL DEFAULT 'agendada',     -- agendada, confirmada, realizada, faltou, cancelada
    observacao           text,
    criado_em            timestamp NOT NULL DEFAULT now(),
    whatsapp_enviado_em  timestamp,                            -- confirmação aberta no WhatsApp
    email_enviado_em     timestamp                             -- confirmação enviada por e-mail
);
CREATE INDEX IF NOT EXISTS consulta_inicio_idx ON consulta (inicio);
CREATE INDEX IF NOT EXISTS consulta_paciente_idx ON consulta (paciente_id, inicio);

-- integração com o Google Agenda: id do evento criado na agenda do profissional
ALTER TABLE consulta ADD COLUMN IF NOT EXISTS google_evento_id text;
