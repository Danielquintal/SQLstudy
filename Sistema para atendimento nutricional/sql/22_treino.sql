-- Rotinas de treino importadas de outros apps (por enquanto, o PDF do MFIT Personal que o paciente vê).
-- sessoes (jsonb): [{"nome", "exercicios": [{"nome", "series": [{"series", "carga", "intervalo"}], "instrucoes",
-- "grupo" (exercícios combinados), "substituto" (ou substitua por)}]}]. Pode rodar mais de uma vez.
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS treino_externo (
    id            serial PRIMARY KEY,
    paciente_id   integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    fonte         text NOT NULL DEFAULT 'mfit',
    rotina        text,                  -- nome da rotina
    objetivo      text,                  -- ex.: Hipertrofia, Condicionamento físico
    nivel         text,                  -- ex.: Adaptação, Avançado
    periodo       text,                  -- ex.: 09/11/2023 - 09/12/2023
    nome_no_pdf   text,                  -- nome do aluno que veio no PDF (para conferir)
    sessoes       jsonb NOT NULL,
    arquivo       text,
    importado_em  timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS treino_externo_paciente_idx ON treino_externo (paciente_id, importado_em);
