"""Anamnese da avaliação (aba "Anamnese" da tela de nova avaliação).

Uma anamnese por avaliação (tabela anamnese, sql/16_anamnese.sql), com as respostas em jsonb. Uma avaliação nova já
abre com a última anamnese do paciente, para só atualizar o que mudou. É só do profissional: não vai para a página
do paciente.

Para mudar as perguntas, edite CAMPOS: (chave, rótulo, tipo, opções). Tipos: texto (uma linha), longo (várias
linhas), numero, escolha (uma opção), varias (caixas de marcar), escala (1 a 5). Chaves novas não estragam as
anamneses antigas; chaves tiradas somem da tela, mas continuam guardadas.
"""
from psycopg.types.json import Jsonb

ESCALA = ["1", "2", "3", "4", "5"]

SECOES = [
    ("Objetivo", None, [
        ("objetivo", "Objetivo principal", "escolha", ["Emagrecimento", "Ganho de massa muscular", "Recomposição corporal",
                                                       "Desempenho esportivo", "Manutenção", "Saúde e qualidade de vida", "Outro"]),
        ("queixa", "Motivo da consulta / queixa principal", "longo", None),
        ("expectativa", "Expectativa e prazo", "texto", None),
    ]),
    ("Saúde", None, [
        ("doencas", "Doenças diagnosticadas", "longo", None),
        ("cirurgias", "Cirurgias e lesões (região, lado e situação: aparecem no boneco da aba Lesões)", "longo", None),
        ("medicamentos", "Medicamentos em uso (nome e dose)", "longo", None),
        ("suplementos", "Suplementos em uso", "longo", None),
        ("alergias", "Alergias e intolerâncias alimentares", "texto", None),
        ("familia", "Histórico familiar", "varias", ["Diabetes", "Hipertensão", "Colesterol alto", "Doença cardíaca",
                                                     "Obesidade", "Câncer", "Doença da tireoide"]),
        ("sintomas", "Sintomas frequentes", "varias", ["Azia/refluxo", "Inchaço/gases", "Dor de cabeça", "Cansaço",
                                                       "Câimbras", "Queda de cabelo", "Ansiedade", "Tontura"]),
    ]),
    ("Hábitos", None, [
        ("sono_horas", "Sono (horas por noite)", "numero", None),
        ("sono_qualidade", "Qualidade do sono (1 ruim a 5 ótima)", "escala", ESCALA),
        ("intestino", "Funcionamento do intestino", "escolha", ["Todo dia", "A cada 2 dias", "Menos de 3 vezes por semana",
                                                                "Irregular", "Diarreia frequente"]),
        ("agua", "Água por dia (litros)", "numero", None),
        ("alcool", "Bebida alcoólica", "escolha", ["Não bebe", "Raramente", "Fins de semana", "Várias vezes por semana", "Todo dia"]),
        ("fumo", "Tabagismo", "escolha", ["Não fuma", "Fuma", "Ex-fumante", "Vape/narguilé"]),
        ("estresse", "Nível de estresse (1 baixo a 5 alto)", "escala", ESCALA),
        ("rotina", "Rotina (trabalho, estudo, horários)", "longo", None),
    ]),
    ("Atividade física", None, [
        ("modalidade", "Modalidade(s)", "texto", None),
        ("treino_vezes", "Treinos por semana", "numero", None),
        ("treino_duracao", "Duração do treino (minutos)", "numero", None),
        ("treino_horario", "Horário do treino", "texto", None),
        ("nivel", "Nível", "escolha", ["Sedentário", "Iniciante", "Intermediário", "Avançado", "Atleta"]),
        ("competicao", "Competições / próxima prova", "texto", None),
    ]),
    ("Alimentação", None, [
        ("refeicoes", "Refeições por dia", "numero", None),
        ("fome", "Fome / apetite (1 pouca a 5 muita)", "escala", ESCALA),
        ("onde_come", "Onde come e quem prepara", "texto", None),
        ("preferencias", "Preferências", "texto", None),
        ("aversoes", "Aversões (o que não come)", "texto", None),
        ("restricao", "Restrição alimentar", "escolha", ["Nenhuma", "Vegetariano", "Vegano", "Sem glúten", "Sem lactose",
                                                         "Low carb", "Outra"]),
        ("beliscos", "Beliscos, compulsão ou episódios de exagero", "texto", None),
        ("recordatorio", "Recordatório de 24 horas", "longo", None),
    ]),
    ("Saúde da mulher", "F", [
        ("ciclo", "Ciclo menstrual", "escolha", ["Regular", "Irregular", "Ausente (amenorreia)", "Menopausa"]),
        ("dum", "Data da última menstruação", "texto", None),
        ("contraceptivo", "Contraceptivo / hormônios", "texto", None),
        ("gestacao", "Gestação ou amamentação", "escolha", ["Não", "Gestante", "Amamentando", "Planejando engravidar"]),
        ("tpm", "Sintomas pré-menstruais", "texto", None),
    ]),
    ("Observações", None, [
        ("observacoes", "Observações gerais", "longo", None),
    ]),
]

CAMPOS = {k: (rot, tipo, ops) for _, _, itens in SECOES for k, rot, tipo, ops in itens}


def ler_form(form):
    """respostas do formulário (campos an_<chave>) -> dict só com o que foi preenchido"""
    dados = {}
    for k, (_, tipo, ops) in CAMPOS.items():
        if tipo == "varias":
            v = [x for x in form.getlist("an_" + k) if x in ops]
        else:
            v = (form.get("an_" + k) or "").strip().replace("\r\n", "\n")
            if tipo in ("escolha", "escala") and v not in ops:
                v = ""
        if v:
            dados[k] = v
    return dados


def da_avaliacao(cur, aid):
    cur.execute("SELECT dados FROM anamnese WHERE avaliacao_id = %s", (aid,))
    r = cur.fetchone()
    return r[0] if r else None


def ultima(cur, pid):
    """(dados, data da avaliação) da anamnese mais recente do paciente, ou (None, None)"""
    cur.execute("""SELECT a.dados, v.data_avaliacao FROM anamnese a JOIN avaliacao v ON v.id = a.avaliacao_id
                   WHERE a.paciente_id = %s ORDER BY v.data_avaliacao DESC LIMIT 1""", (pid,))
    r = cur.fetchone()
    return (r[0], r[1]) if r else (None, None)


def gravar(cur, pid, aid, dados):
    """grava (ou troca) a anamnese da avaliação; sem nenhuma resposta, apaga"""
    if not dados:
        cur.execute("DELETE FROM anamnese WHERE avaliacao_id = %s", (aid,))
        return
    cur.execute("""INSERT INTO anamnese (paciente_id, avaliacao_id, dados) VALUES (%s, %s, %s)
                   ON CONFLICT (avaliacao_id) DO UPDATE SET dados = EXCLUDED.dados, atualizado_em = now()""",
                (pid, aid, Jsonb(dados)))
