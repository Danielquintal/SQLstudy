"""Rastreio de RED-S (deficiência energética relativa no esporte): LEAF-Q e energia disponível.

LEAF-Q (Low Energy Availability in Females Questionnaire, Melin et al., 2014): total de 8 ou mais indica risco de
baixa disponibilidade energética. Perguntas e pontos iguais aos da planilha "Rastreio dinâmico de RED-S".
Energia disponível (ED) = (ingestão − gasto energético no exercício) ÷ massa livre de gordura, em kcal/kg MLG/dia:
adequada ≥ 45, subclínica 30–45, baixa < 30 (Loucks).
"""

RISCO_LEAFQ = 8

SIM_NAO = [("Sim", 0), ("Não", 0)]
FREQ_GI = [("Sim, diversas vezes ao dia", 3), ("Sim, diversas vezes durante a semana", 2),
           ("Sim, uma ou duas vezes na semana ou mais raramente", 1), ("Raramente ou nunca", 0)]

# (chave, seção, pergunta, tipo, opções [(texto, pontos)]) — tipo: unica, multipla ou texto
PERGUNTAS = [
    ("lesao", "lesoes", "Você se ausentou do treinamento, ou deixou de participar de alguma competição no último ano, devido a lesões?",
     "unica", [("Não, de forma alguma", 0), ("Sim, uma ou duas vezes", 1), ("Sim, três a quatro vezes", 2), ("Sim, cinco vezes ou mais", 3)]),
    ("lesao_dias", "lesoes", "Se sim, por quantos dias se ausentou do treinamento ou de competições, no último ano?",
     "unica", [("1-7 dias", 1), ("8-14 dias", 2), ("15-21 dias", 3), ("22 dias ou mais", 4)]),
    ("lesao_tipos", "lesoes", "Se sim, que tipos de lesões teve no último ano?", "texto", []),
    ("gi_gases", "gastro", "Sente-se com gases ou com o abdômen inchado, mesmo fora da menstruação?", "unica", FREQ_GI),
    ("gi_colicas", "gastro", "Tem cólicas ou dores estomacais que não estão relacionadas à menstruação?", "unica", FREQ_GI),
    ("gi_evacuacao", "gastro", "Com que frequência evacua?", "unica",
     [("Diversas vezes ao dia", 1), ("Uma vez por dia", 0), ("A cada dois dias", 2), ("Duas vezes por semana", 3),
      ("Uma vez por semana ou menos", 4)]),
    ("gi_fezes", "gastro", "Como descreve suas fezes?", "unica",
     [("Normal (branda)", 0), ("Parecendo diarreia (aguada)", 1), ("Dura e seca", 2)]),
    ("aco_usa", "menstrual", "Usa anticoncepcional oral?", "unica", SIM_NAO),
    ("aco_motivo", "menstrual", "Se sim, por que usa anticoncepcional oral?", "multipla",
     [("Contracepção", 0), ("Redução das dores menstruais", 0), ("Redução do sangramento", 0),
      ("Para regular o ciclo menstrual e sua influência no desempenho esportivo", 0),
      ("Se eu não usar, a menstruação para", 1), ("Outros motivos", 0)]),
    ("aco_outro", "menstrual", "Usa outro contraceptivo hormonal (implante, DIU hormonal)?", "unica", SIM_NAO),
    ("men_idade", "menstrual", "Que idade tinha quando menstruou pela primeira vez?", "unica",
     [("11 anos ou menos", 0), ("12-14 anos", 0), ("15 anos ou mais", 1), ("Não me lembro", 0), ("Nunca menstruei", 8)]),
    ("men_natural", "menstrual", "A primeira menstruação veio naturalmente (por si só)?", "unica",
     [("Sim", 0), ("Não", 1), ("Não me lembro", 1)]),
    ("men_tratamento", "menstrual", "Se não, que tratamento foi usado para iniciar o ciclo menstrual?", "multipla",
     [("Tratamento hormonal", 1), ("Ganho de peso", 1), ("Redução da quantidade de exercícios", 1), ("Outro", 1)]),
    ("men_normal", "menstrual", "Sua menstruação é normal?", "unica",
     [("Sim", 0), ("Não", 2), ("Não sei", 1)]),
    ("men_ultima", "menstrual", "Quando foi sua última menstruação?", "unica",
     [("0-4 semanas atrás", 0), ("1-2 meses atrás", 1), ("3-4 meses atrás", 2), ("5 meses atrás ou mais", 3)]),
    ("men_regular", "menstrual", "Sua menstruação é regular (a cada 28 a 34 dias)?", "unica",
     [("Sim, na maioria das vezes", 0), ("Não, na maioria das vezes não", 1)]),
    ("men_dias", "menstrual", "Por quantos dias tem sangramento?", "unica",
     [("1-2 dias", 1), ("3-4 dias", 0), ("5-6 dias", 0), ("7-8 dias", 0), ("9 dias ou mais", 0)]),
    ("men_intenso", "menstrual", "Já teve problemas com sangramento menstrual intenso?", "unica", SIM_NAO),
    ("men_12m", "menstrual", "Quantas vezes menstruou nos últimos 12 meses?", "unica",
     [("12 ou mais", 0), ("9-11", 1), ("6-8", 2), ("3-5", 3), ("0-2", 4)]),
    ("men_c6", "menstrual", "Se a menstruação não é normal (ou não sabe), quando foi a última?", "unica",
     [("2-3 meses atrás", 1), ("4-5 meses atrás", 2), ("6 meses atrás ou mais", 3), ("Estou grávida", 0)]),
    ("men_3meses", "menstrual", "Já ficou sem menstruar por 3 meses seguidos ou mais (fora gravidez)?", "unica",
     [("Não, nunca", 0), ("Sim, já aconteceu antes", 1), ("Sim, está ocorrendo agora", 2)]),
    ("men_muda", "menstrual", "A menstruação muda quando aumenta a intensidade, frequência ou duração dos treinos?", "unica",
     [("Sim", 1), ("Não", 0)]),
    ("men_como", "menstrual", "Se sim, como muda?", "multipla",
     [("Eu sangro menos", 1), ("Eu sangro por menos dias", 1), ("Minha menstruação é interrompida", 2),
      ("Eu sangro mais", 0), ("Eu sangro por mais dias", 0)]),
]
SECOES = {"lesoes": "Lesões", "gastro": "Função gastrointestinal", "menstrual": "Função menstrual e contraceptivos"}


def ler_formulario(form):
    """respostas do formulário da tela (radios, caixas e textos)"""
    respostas = {}
    for chave, _, _, tipo, opcoes in PERGUNTAS:
        if tipo == "multipla":
            marcadas = [t for t, _ in opcoes if t in form.getlist(chave)]
            if marcadas:
                respostas[chave] = marcadas
        elif form.get(chave, "").strip():
            v = form[chave].strip()
            if tipo == "texto" or v in [t for t, _ in opcoes]:
                respostas[chave] = v
    return respostas


def pontuar(respostas):
    """(lesões, gastrointestinal, menstrual, total)"""
    soma = {s: 0 for s in SECOES}
    for chave, secao, _, tipo, opcoes in PERGUNTAS:
        v = respostas.get(chave)
        if not v or tipo == "texto":
            continue
        pontos = dict(opcoes)
        if chave == "men_tratamento":   # só vale quando a primeira menstruação não veio sozinha
            soma[secao] += 1 if respostas.get("men_natural") in ("Não", "Não me lembro") else 0
        elif tipo == "multipla":
            soma[secao] += sum(pontos.get(x, 0) for x in v)
        else:
            soma[secao] += pontos.get(v, 0)
    return soma["lesoes"], soma["gastro"], soma["menstrual"], sum(soma.values())


def classe_leafq(total):
    return "Risco de baixa disponibilidade energética" if total >= RISCO_LEAFQ else "Sem risco pelo LEAF-Q"


def energia_disponivel(ingestao, gasto, mlg):
    """kcal/kg MLG/dia"""
    return (float(ingestao) - float(gasto)) / float(mlg) if mlg else None


def classe_ed(ed):
    if ed is None:
        return ""
    return "Adequada" if ed >= 45 else "Baixa" if ed < 30 else "Subclínica"


# ---------- respostas vindas de fora: planilha antiga e Formulário Google ----------
import io, re, time, unicodedata
from datetime import datetime

# coluna da planilha "Respostas ao formulário 1" -> pergunta do sistema
COLUNAS_PLANILHA = {"O": "lesao", "P": "lesao_dias", "Q": "lesao_tipos", "R": "gi_gases", "S": "gi_colicas",
                    "T": "gi_evacuacao", "U": "gi_fezes", "W": "aco_usa", "X": "aco_motivo", "AA": "aco_outro",
                    "AC": "men_idade", "AD": "men_natural", "AE": "men_tratamento", "AF": "men_normal", "AG": "men_ultima",
                    "AH": "men_regular", "AI": "men_dias", "AJ": "men_intenso", "AK": "men_12m", "AL": "men_c6",
                    "AM": "men_3meses", "AN": "men_muda", "AO": "men_como"}
OUTRO = {"aco_motivo": "Outros motivos", "men_tratamento": "Outro"}   # resposta livre nas perguntas de várias opções
_ultima_busca = 0.0


def _n(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = s.replace("(va para a pergunta c6)", "").replace("semana atras", "semanas atras")
    return re.sub(r"[‐–-]", "-", re.sub(r"\s+", " ", s)).strip(" .")


def respostas_de(itens):
    """{pergunta: texto ou lista} vindo de fora -> respostas com o texto exato das opções do sistema"""
    respostas = {}
    for chave, _, _, tipo, opcoes in PERGUNTAS:
        v = itens.get(chave)
        if v in (None, "", []):
            continue
        if tipo == "texto":
            respostas[chave] = str(v).strip()
            continue
        textos = {_n(t): t for t, _ in opcoes}
        if chave == "men_c6":
            textos[_n("Estou grávida e, portanto, não menstruo")] = "Estou grávida"
        partes = v if isinstance(v, list) else ([p for p in re.split(r",\s*(?=[A-ZÁÉÍÓÚ])", str(v))] if tipo == "multipla" else [v])
        achadas = []
        for p in partes:
            t = textos.get(_n(p))
            if t is None and _n(p).startswith(("nao", "sim")) and tipo == "unica":   # "Não (vá para ...)" etc.
                t = next((txt for k, txt in textos.items() if _n(p).startswith(k)), None)
            if t is None and chave in OUTRO and str(p).strip():
                t = OUTRO[chave]
            if t and t not in achadas:
                achadas.append(t)
        if achadas:
            respostas[chave] = achadas if tipo == "multipla" else achadas[0]
    return respostas


def ler_planilha(dados):
    """respostas da aba "Respostas ao formulário 1" da planilha de RED-S: [{linha, data, nome, respostas, pontos}]"""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(dados), data_only=True)
    ws = wb["Respostas ao formulário 1"] if "Respostas ao formulário 1" in wb.sheetnames else wb.worksheets[0]
    saida = []
    for r in range(2, ws.max_row + 1):
        itens = {chave: ws[f"{col}{r}"].value for col, chave in COLUNAS_PLANILHA.items()}
        respostas = respostas_de(itens)
        if len(respostas) < 3:      # linha vazia ou só com o link do formulário
            continue
        quando = ws[f"A{r}"].value
        saida.append({"linha": r, "data": quando.date().isoformat() if isinstance(quando, datetime) else "",
                      "nome": str(ws[f"C{r}"].value or "").strip(), "email": str(ws[f"B{r}"].value or "").strip(),
                      "respostas": respostas, "pontos": pontuar(respostas)})
    return saida


def link_leafq(cfg, nome):
    c = cfg.get("checkin", {})
    if not c.get("leafq_formulario"):
        return None
    from urllib.parse import quote
    return c["leafq_formulario"].replace(c.get("marca") or "NOME_DO_PACIENTE", quote(nome.strip()))


def criar_formulario(cfg):
    """pede ao script do Google (versão 5) para criar o formulário do LEAF-Q com as perguntas deste arquivo"""
    import checkin
    ck = cfg["checkin"]
    perguntas = [{"chave": k, "secao": SECOES[s], "titulo": t, "tipo": tipo, "opcoes": [o for o, _ in opcoes]}
                 for k, s, t, tipo, opcoes in PERGUNTAS]
    r = checkin._postar(ck["url"], {"chave": ck["chave"], "acao": "criar_leafq", "perguntas": perguntas})
    if r.get("erro"):
        raise checkin.ErroGoogle("O script do Google não criou o formulário" + (": atualize o código do script." if r["erro"] == "acao" else f" ({r['erro']})."))
    return r


def sincronizar(cur, cfg):
    """traz as respostas novas do formulário do LEAF-Q; devolve (novas, sem paciente)"""
    global _ultima_busca
    import checkin
    ck = cfg["checkin"]
    if not (ck.get("url") and ck.get("chave") and ck.get("leafq_formulario")):
        return 0, 0
    dados = checkin._chamar(ck["url"], ck["chave"], acao="leafq")
    _ultima_busca = time.time()
    cur.execute("SELECT id, nome FROM paciente")
    pacientes = cur.fetchall()
    novas = sem = 0
    for r in dados.get("respostas", []):
        itens = r.get("itens", {})
        nome = str(itens.get("nome") or "").strip()
        achados = [i for i, n in pacientes if checkin.norm(n) == checkin.norm(nome)]
        pid = achados[0] if len(achados) == 1 else None
        respostas = respostas_de(itens)
        les, gi, men, total = pontuar(respostas)
        quando = datetime.fromisoformat(r["quando"].replace("Z", "+00:00")).astimezone().date()
        cur.execute("""INSERT INTO reds_leafq (paciente_id, data, respostas, lesoes, gastro, menstrual, total, origem, nome_informado)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (origem) DO NOTHING""",
                    (pid, quando, __import__("json").dumps(respostas, ensure_ascii=False), les, gi, men, total,
                     "form:" + r["id"], nome or None))
        if cur.rowcount:
            novas += 1
            sem += pid is None
    return novas, sem


def sincronizar_se_preciso(con, cfg, minutos=10):
    import checkin
    if time.time() - _ultima_busca < minutos * 60 or not cfg.get("checkin", {}).get("leafq_formulario"):
        return None
    try:
        r = sincronizar(con.cursor(), cfg)
        con.commit()
        return r
    except checkin.ErroGoogle:
        globals()["_ultima_busca"] = time.time()
        return None


def para_pagina(cur, pid):
    """resultados do rastreio de RED-S para a página do paciente (do mais antigo ao mais novo)"""
    cur.execute("SELECT data, lesoes, gastro, menstrual, total FROM reds_leafq WHERE paciente_id = %s ORDER BY data, id", (pid,))
    leafq = [{"data": d.strftime("%d/%m/%Y"), "lesoes": l, "gastro": g, "menstrual": m, "total": t, "risco": t >= RISCO_LEAFQ,
              "classe": classe_leafq(t)} for d, l, g, m, t in cur.fetchall()]
    cur.execute("SELECT data, ingestao_kcal, gasto_exercicio_kcal, mlg_kg, observacao FROM reds_energia WHERE paciente_id = %s "
                "ORDER BY data, id", (pid,))
    energia = []
    for d, ing, gee, mlg, obs in cur.fetchall():
        ed = energia_disponivel(ing, gee, mlg)
        energia.append({"data": d.strftime("%d/%m/%Y"), "ingestao": float(ing), "gasto": float(gee), "mlg": float(mlg),
                        "ed": round(ed, 1) if ed is not None else None, "classe": classe_ed(ed), "obs": obs or ""})
    return {"leafq": leafq, "energia": energia}
