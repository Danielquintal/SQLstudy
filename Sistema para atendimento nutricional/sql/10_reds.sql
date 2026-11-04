-- Rastreio de RED-S: questionário LEAF-Q e energia disponível (pode rodar mais de uma vez)
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS reds_leafq (
    id           serial PRIMARY KEY,
    paciente_id  integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    data         date NOT NULL,
    respostas    jsonb NOT NULL,        -- resposta de cada pergunta (texto da opção, lista ou texto livre)
    lesoes       smallint NOT NULL,
    gastro       smallint NOT NULL,
    menstrual    smallint NOT NULL,
    total        smallint NOT NULL,     -- 8 ou mais = risco de baixa disponibilidade energética
    criado_em    timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reds_leafq_paciente_idx ON reds_leafq (paciente_id, data);

CREATE TABLE IF NOT EXISTS reds_energia (
    id                 serial PRIMARY KEY,
    paciente_id        integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    data               date NOT NULL,
    ingestao_kcal      numeric NOT NULL,
    gasto_exercicio_kcal numeric NOT NULL,
    mlg_kg             numeric NOT NULL,
    observacao         text,           -- ex.: fase da periodização, campeonato
    criado_em          timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reds_energia_paciente_idx ON reds_energia (paciente_id, data);

-- respostas vindas de fora (Formulário Google do LEAF-Q ou planilha antiga): de onde veio, para não entrar duas vezes;
-- sem paciente identificada, a resposta espera na tela de respostas do LEAF-Q
ALTER TABLE reds_leafq ADD COLUMN IF NOT EXISTS origem text UNIQUE;
ALTER TABLE reds_leafq ADD COLUMN IF NOT EXISTS nome_informado text;
ALTER TABLE reds_leafq ALTER COLUMN paciente_id DROP NOT NULL;
