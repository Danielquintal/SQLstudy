-- Lembretes do profissional (tela Lembretes do sistema; pode rodar mais de uma vez)
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS lembrete (
    id                serial PRIMARY KEY,
    texto             text NOT NULL,
    quando            timestamp NOT NULL,                       -- dia e hora do aviso
    paciente_id       integer REFERENCES paciente (id) ON DELETE SET NULL,   -- opcional
    repetir           text NOT NULL DEFAULT '',                 -- '' (uma vez), diario, semanal, quinzenal, mensal
    google            boolean NOT NULL DEFAULT true,            -- também vai para o Google Agenda (com aviso no celular)
    aviso_min         smallint NOT NULL DEFAULT 0,              -- minutos de antecedência do aviso do Google
    google_evento_id  text,
    feito_em          timestamp,                                -- concluído
    criado_em         timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS lembrete_quando_idx ON lembrete (quando) WHERE feito_em IS NULL;
CREATE INDEX IF NOT EXISTS lembrete_paciente_idx ON lembrete (paciente_id);
