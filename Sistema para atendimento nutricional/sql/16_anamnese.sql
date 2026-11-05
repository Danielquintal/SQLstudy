-- Anamnese de cada avaliação (aba "Anamnese" da nova avaliação). Pode rodar mais de uma vez.
-- Desfazer: DROP TABLE anamnese;
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS anamnese (
    id            serial PRIMARY KEY,
    paciente_id   integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    avaliacao_id  integer NOT NULL UNIQUE REFERENCES avaliacao (id) ON DELETE CASCADE,
    dados         jsonb NOT NULL,             -- respostas: chaves de sistema/anamnese.py (CAMPOS)
    atualizado_em timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS anamnese_paciente_idx ON anamnese (paciente_id);
