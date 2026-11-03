-- Tabela de alimentos para montar planos: TACO (carregada por scripts/carregar_taco.py) e alimentos próprios
-- (marcas, suplementos, receitas), todos com nutrientes por 100 g. Pode rodar mais de uma vez.
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS alimento_grupo (
    id    integer PRIMARY KEY,
    nome  text NOT NULL
);

CREATE TABLE IF NOT EXISTS alimento (
    id            serial PRIMARY KEY,
    fonte         text NOT NULL DEFAULT 'proprio',   -- 'TACO' ou 'proprio'
    codigo_taco   integer UNIQUE,                     -- número do alimento na TACO
    nome          text NOT NULL,
    grupo_id      integer REFERENCES alimento_grupo (id),
    -- por 100 g (NULL = não informado na fonte)
    umidade_pct   numeric, kcal numeric, kj numeric,
    proteina_g    numeric, lipidios_g numeric, carboidrato_g numeric, fibra_g numeric, cinzas_g numeric,
    colesterol_mg numeric,
    ag_saturados_g numeric, ag_monoinsaturados_g numeric, ag_poliinsaturados_g numeric, ag_trans_g numeric,
    calcio_mg numeric, magnesio_mg numeric, manganes_mg numeric, fosforo_mg numeric, ferro_mg numeric,
    sodio_mg numeric, potassio_mg numeric, cobre_mg numeric, zinco_mg numeric,
    retinol_mcg numeric, vit_a_re_mcg numeric, vit_a_rae_mcg numeric,
    tiamina_mg numeric, riboflavina_mg numeric, piridoxina_mg numeric, niacina_mg numeric, vit_c_mg numeric,
    criado_em     timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alimento_nome_idx ON alimento (lower(nome));

-- Medidas caseiras de cada alimento (ex.: "Colher de sopa cheia" = 25 g), cadastradas ao montar os planos
CREATE TABLE IF NOT EXISTS medida_caseira (
    id           serial PRIMARY KEY,
    alimento_id  integer NOT NULL REFERENCES alimento (id) ON DELETE CASCADE,
    nome         text NOT NULL,
    gramas       numeric NOT NULL CHECK (gramas > 0),
    UNIQUE (alimento_id, nome)
);
