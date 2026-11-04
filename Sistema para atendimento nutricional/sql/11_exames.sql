-- Exames laboratoriais e testes de desempenho (pode rodar mais de uma vez)
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS exame (
    id           serial PRIMARY KEY,
    paciente_id  integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    data         date NOT NULL,             -- data da coleta
    laboratorio  text,
    observacao   text,
    criado_em    timestamp NOT NULL DEFAULT now(),
    UNIQUE (paciente_id, data)
);

CREATE TABLE IF NOT EXISTS exame_valor (
    exame_id   integer NOT NULL REFERENCES exame (id) ON DELETE CASCADE,
    item       text NOT NULL,               -- id do exame em sistema/exames.json (ex.: glicose)
    valor      numeric NOT NULL,
    ref_laudo  text,                        -- referência que veio no laudo (ex.: "0,4 a 4,5"); vale no lugar da padrão
    PRIMARY KEY (exame_id, item)
);

CREATE TABLE IF NOT EXISTS desempenho (
    id           serial PRIMARY KEY,
    paciente_id  integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    data         date NOT NULL,
    teste        text NOT NULL,             -- ex.: Supino reto, Dinamometria, Sprint 20 m
    unidade      text NOT NULL DEFAULT '',
    melhor       text NOT NULL DEFAULT 'maior' CHECK (melhor IN ('maior', 'menor')),   -- carga sobe; tempo de sprint desce
    valor        numeric NOT NULL,          -- lado direito quando o teste tem dois lados
    valor_esq    numeric,                   -- lado esquerdo (dinamometria e testes unilaterais)
    observacao   text,
    criado_em    timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS desempenho_paciente_idx ON desempenho (paciente_id, teste, data);
