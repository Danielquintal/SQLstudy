-- Dados de relógio/app esportivo importados de arquivo (por enquanto, Garmin: planilha de atividades ou "Exportar seus
-- dados"). Pode rodar mais de uma vez. Reimportar o mesmo arquivo atualiza, não duplica.
SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS atividade_externa (
    id           serial PRIMARY KEY,
    paciente_id  integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    fonte        text NOT NULL DEFAULT 'garmin',
    id_externo   text NOT NULL,                       -- id da atividade no Garmin (ou data+tipo, na planilha)
    inicio       timestamp NOT NULL,
    tipo         text,                                -- corrida, ciclismo, musculação...
    titulo       text,
    duracao_s    integer CHECK (duracao_s >= 0),
    distancia_m  numeric CHECK (distancia_m >= 0),
    calorias     integer,
    fc_media     smallint,
    fc_max       smallint,
    passos       integer,
    subida_m     numeric,
    importado_em timestamp NOT NULL DEFAULT now(),
    UNIQUE (paciente_id, fonte, id_externo)
);
CREATE INDEX IF NOT EXISTS atividade_externa_paciente_idx ON atividade_externa (paciente_id, inicio);

CREATE TABLE IF NOT EXISTS diario_externo (
    paciente_id      integer NOT NULL REFERENCES paciente (id) ON DELETE CASCADE,
    fonte            text NOT NULL DEFAULT 'garmin',
    dia              date NOT NULL,
    passos           integer,
    meta_passos      integer,
    sono_min         integer,                         -- sono total (sem os períodos acordado)
    sono_profundo_min integer,
    sono_rem_min     integer,
    fc_repouso       smallint,
    calorias_ativas  integer,
    PRIMARY KEY (paciente_id, fonte, dia)
);
