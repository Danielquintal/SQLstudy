-- Banco de dados dos pacientes e avaliações antropométricas (origem: App Naive)
-- Rodar conectado ao banco "app_naive":  psql -U postgres -d app_naive -f 01_schema.sql
SET client_encoding = 'UTF8';

DROP TABLE IF EXISTS contato;   -- tabelas de sql/03_whatsapp.sql e 04_plano.sql, que dependem de paciente
DROP TABLE IF EXISTS plano_alimentar;
DROP VIEW IF EXISTS vw_resumo_paciente;
DROP VIEW IF EXISTS vw_avaliacao;
DROP TABLE IF EXISTS avaliacao;
DROP TABLE IF EXISTS paciente;

-- Cadastro (planilha "pacientes_app_naive_02-11-2026.xlsx")
CREATE TABLE paciente (
    id               serial PRIMARY KEY,
    app_naive_id       bigint UNIQUE,          -- código do paciente no App Naive (link da evolução)
    nome             text NOT NULL,
    cpf              varchar(14),
    telefone         text,
    email            text,
    genero           char(1) CHECK (genero IN ('M', 'F')),
    data_nascimento  date,
    criado_em        timestamp,
    modificado_em    timestamp,
    etiquetas        text,
    cep              varchar(9),
    endereco         text,
    bairro           text,
    cidade           text,
    estado           varchar(2)
);
CREATE INDEX paciente_nome_idx ON paciente (lower(nome));

-- Uma linha por avaliação (aba "Avaliações" da planilha Antropometria_Pacientes_2025-2026.xlsx)
CREATE TABLE avaliacao (
    id                       serial PRIMARY KEY,
    paciente_id              integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    data_avaliacao           date NOT NULL,
    -- Análises básicas
    peso_kg                  numeric,
    altura_cm                numeric,
    imc                      numeric,
    classificacao_imc        text,
    peso_ideal               text,
    rcq                      numeric,
    risco_rcq                text,
    cmb_cm                   numeric,
    cmb_adequacao_pct        numeric,
    classificacao_cmb        text,
    gordura_pct              numeric,
    classificacao_gordura    text,
    massa_gordura_kg         numeric,
    massa_ossea_kg           numeric,
    massa_muscular_kg        numeric,
    massa_residual_kg        numeric,
    mlg_kg                   numeric,
    somatorio_dobras_mm      numeric,
    densidade_corporal       numeric,
    protocolo_dobras         text,
    equacao_gordura          text,
    -- Bioimpedância
    bia_gordura_pct          numeric,
    bia_classificacao_gordura text,
    bia_massa_magra_pct      numeric,
    bia_massa_muscular_kg    numeric,
    bia_agua_kg              numeric,
    bia_massa_ossea_kg       numeric,
    bia_massa_gordura_kg     numeric,
    bia_mlg_kg               numeric,
    bia_gordura_visceral     numeric,
    bia_idade_metabolica     numeric,
    -- Medidas complementares (cm)
    altura_sentado_cm        numeric,
    altura_joelho_cm         numeric,
    -- Dobras cutâneas (mm)
    dobra_tricipital         numeric,
    dobra_bicipital          numeric,
    dobra_subescapular       numeric,
    dobra_toracica           numeric,
    dobra_axilar_media       numeric,
    dobra_suprailiaca        numeric,
    dobra_supraespinhal      numeric,
    dobra_abdominal          numeric,
    dobra_coxa               numeric,
    dobra_panturrilha        numeric,
    -- Circunferências (cm); _e = esquerdo, _d = direito
    circ_pescoco             numeric,
    circ_torax               numeric,
    circ_ombro               numeric,
    circ_cintura             numeric,
    circ_abdomen             numeric,
    circ_quadril             numeric,
    braco_relaxado_e         numeric,
    braco_relaxado_d         numeric,
    braco_contraido_e        numeric,
    braco_contraido_d        numeric,
    antebraco_e              numeric,
    antebraco_d              numeric,
    coxa_proximal_e          numeric,
    coxa_proximal_d          numeric,
    coxa_medial_e            numeric,
    coxa_medial_d            numeric,
    coxa_distal_e            numeric,
    coxa_distal_d            numeric,
    panturrilha_e            numeric,
    panturrilha_d            numeric,
    -- Diâmetros ósseos (cm)
    diametro_umero           numeric,
    diametro_punho           numeric,
    diametro_femur           numeric
);
CREATE INDEX avaliacao_paciente_data_idx ON avaliacao (paciente_id, data_avaliacao);

-- Avaliações com nome e idade na data da avaliação
CREATE VIEW vw_avaliacao AS
SELECT p.nome, p.genero,
       date_part('year', age(a.data_avaliacao, p.data_nascimento))::int AS idade_na_avaliacao,
       a.*
FROM avaliacao a
JOIN paciente p ON p.id = a.paciente_id;

-- Substitui a aba "Resumo por paciente": primeira x última avaliação, sempre atualizado
CREATE VIEW vw_resumo_paciente AS
WITH ordenadas AS (
    SELECT a.*,
           row_number() OVER (PARTITION BY paciente_id ORDER BY data_avaliacao)      AS ordem,
           row_number() OVER (PARTITION BY paciente_id ORDER BY data_avaliacao DESC) AS ordem_inv,
           count(*)     OVER (PARTITION BY paciente_id)                               AS n_avaliacoes
    FROM avaliacao a
),
primeira AS (SELECT * FROM ordenadas WHERE ordem = 1),
ultima   AS (SELECT * FROM ordenadas WHERE ordem_inv = 1)
SELECT p.id AS paciente_id, p.nome, p.genero,
       u.n_avaliacoes,
       pr.data_avaliacao AS primeira_avaliacao,
       u.data_avaliacao  AS ultima_avaliacao,
       pr.peso_kg AS peso_inicial,       u.peso_kg AS peso_atual,       u.peso_kg - pr.peso_kg AS peso_variacao,
       pr.imc AS imc_inicial,            u.imc AS imc_atual,            u.imc - pr.imc AS imc_variacao,
       pr.gordura_pct AS gordura_inicial, u.gordura_pct AS gordura_atual, u.gordura_pct - pr.gordura_pct AS gordura_variacao,
       pr.massa_muscular_kg AS massa_muscular_inicial, u.massa_muscular_kg AS massa_muscular_atual,
       u.massa_muscular_kg - pr.massa_muscular_kg AS massa_muscular_variacao,
       pr.mlg_kg AS mlg_inicial,         u.mlg_kg AS mlg_atual,         u.mlg_kg - pr.mlg_kg AS mlg_variacao,
       pr.circ_cintura AS cintura_inicial, u.circ_cintura AS cintura_atual, u.circ_cintura - pr.circ_cintura AS cintura_variacao,
       pr.somatorio_dobras_mm AS somatorio_inicial, u.somatorio_dobras_mm AS somatorio_atual,
       u.somatorio_dobras_mm - pr.somatorio_dobras_mm AS somatorio_variacao,
       u.classificacao_imc     AS classificacao_imc_atual,
       u.classificacao_gordura AS classificacao_gordura_atual
FROM paciente p
JOIN primeira pr ON pr.paciente_id = p.id
JOIN ultima   u  ON u.paciente_id  = p.id;
