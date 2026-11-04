-- Check-in semanal pelo Formulário Google (pode rodar mais de uma vez)
-- As respostas chegam pelo script sistema/checkin_google.gs; o sistema busca e grava aqui.
SET client_encoding = 'UTF8';

ALTER TABLE paciente
    ADD COLUMN IF NOT EXISTS checkin_pausado boolean NOT NULL DEFAULT false;   -- não pedir check-in a este paciente

-- Uma linha por resposta do formulário
CREATE TABLE IF NOT EXISTS checkin (
    id               serial PRIMARY KEY,
    google_id        text NOT NULL UNIQUE,     -- id da resposta no Google (evita gravar duas vezes)
    paciente_id      integer REFERENCES paciente (id) ON DELETE CASCADE,  -- vazio = nome não bateu com ninguém
    respondido_em    timestamp NOT NULL,
    nome_informado   text,
    peso_kg          numeric,
    cintura_cm       numeric,
    adesao           smallint,   -- 1 (quase nada) a 5 (seguiu totalmente)
    dificuldades     text,
    fome             smallint,   -- 1 (muita fome) a 5 (fome controlada)
    sono             smallint,   -- 1 (muito ruim) a 5 (muito bom)
    energia          smallint,   -- 1 (muito baixa) a 5 (muito alta)
    intestino        text,
    agua             text,       -- faixa de litros por dia
    treinos          smallint,   -- treinos na semana
    treino_sensacao  smallint,   -- 1 (muito mal) a 5 (muito bem)
    comentario       text,
    respostas        jsonb NOT NULL,           -- a resposta inteira, como veio do Google
    importado_em     timestamp NOT NULL DEFAULT now(),
    excluido         boolean NOT NULL DEFAULT false   -- excluída no sistema; fica aqui para não voltar na próxima busca
);
ALTER TABLE checkin ADD COLUMN IF NOT EXISTS excluido boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS checkin_paciente_idx ON checkin (paciente_id, respondido_em);
