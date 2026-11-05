"""Lê o PDF do laudo de exames de sangue (de qualquer laboratório) e acha os resultados da tabela sistema/exames.json.

Não depende do layout de um laboratório: procura, linha a linha, o nome do exame no começo da linha (com os nomes que os
laboratórios costumam usar) e pega o resultado na mesma linha ("HEMOGLOBINA : 15,2 g/dL 13,3 a 16,5") ou nas linhas
logo abaixo, no modelo em bloco ("COLESTEROL TOTAL, soro" / "Método: ..." / "124 mg/dL ..."). O que achar vai para
o formulário de lançamento já preenchido: o nutricionista confere e salva.

  ler(dados, senha="") -> {"data": date|None, "laboratorio": str, "valores": {id: {"valor", "ref", "linha", "unidade"}},
                           "paginas": n, "erro": None | "senha" | "sem_texto" | "pdf"}
"""
import re
import unicodedata
from collections import Counter
from datetime import date

import pypdfium2

# nome do exame no laudo -> id em sistema/exames.json. None bloqueia (ex.: "testosterona livre" não é a total).
# Vale o nome mais comprido que casar com o começo da linha.
NOMES = {
    "hemacias": ["hemacias", "eritrocitos", "contagem de hemacias", "globulos vermelhos", "contagem de eritrocitos"],
    "hemoglobina": ["hemoglobina", "hb"],
    "hematocrito": ["hematocrito", "ht"],
    "vcm": ["vcm", "volume corpuscular medio", "v c m"],
    "hcm": ["hcm", "hemoglobina corpuscular media", "h c m"],
    "chcm": ["chcm", "concentracao de hemoglobina corpuscular media", "concentracao hemoglobinica corpuscular media",
             "c h c m"],
    "rdw": ["rdw", "coeficiente de variacao do volume eritrocitario", "amplitude de distribuicao dos eritrocitos",
            "indice de anisocitose"],
    "leucocitos": ["leucocitos", "leucocitos totais", "globulos brancos", "contagem de leucocitos"],
    "neutrofilos": ["neutrofilos segmentados", "segmentados", "neutrofilos"],
    "bastonetes": ["bastonetes", "neutrofilos bastonetes", "bastoes"],
    "eosinofilos": ["eosinofilos"],
    "basofilos": ["basofilos"],
    "monocitos": ["monocitos"],
    "linfocitos": ["linfocitos", "linfocitos tipicos", "linfocitos totais"],
    "plaquetas": ["plaquetas", "contagem de plaquetas", "plaquetometria"],
    "glicose": ["glicose", "glicemia", "glicemia de jejum", "glicose de jejum", "glicose em jejum", "glicose plasmatica",
                "glicose jejum"],
    "insulina": ["insulina", "insulina basal", "insulina de jejum", "insulina jejum"],
    "hba1c": ["hemoglobina glicada", "hemoglobina glicosilada", "hba1c", "hb a1c", "a1c", "glicohemoglobina"],
    "colesterol_total": ["colesterol total", "colesterol"],
    "hdl": ["hdl", "hdl colesterol", "colesterol hdl", "hdl c"],
    "ldl": ["ldl", "ldl colesterol", "colesterol ldl", "ldl c"],
    "vldl": ["vldl", "vldl colesterol", "colesterol vldl"],
    "triglicerides": ["triglicerides", "triglicerideos", "triglicéridos", "trigliceridios", "triglicerideo"],
    "creatinina": ["creatinina", "creatinina serica"],
    "acido_urico": ["acido urico", "uricemia"],
    "ureia": ["ureia", "ureia serica"],
    "tgo": ["tgo", "ast", "tgo ast", "ast tgo", "aspartato aminotransferase", "transaminase oxalacetica",
            "transaminase glutamico oxalacetica"],
    "tgp": ["tgp", "alt", "tgp alt", "alt tgp", "alanina aminotransferase", "transaminase piruvica",
            "transaminase glutamico piruvica"],
    "ggt": ["ggt", "gama gt", "gama glutamil transferase", "gama glutamiltransferase", "gamaglutamiltransferase",
            "gama glutamil transpeptidase"],
    "cpk": ["cpk", "ck", "ck total", "creatinoquinase", "creatina quinase", "creatinofosfoquinase", "creatina fosfoquinase",
            "creatinoquinase total"],
    "calcio": ["calcio", "calcio total", "calcio serico"],
    "potassio": ["potassio", "potassio serico"],
    "magnesio": ["magnesio", "magnesio serico"],
    "sodio": ["sodio", "sodio serico"],
    "fosforo": ["fosforo", "fosforo serico", "fosforo inorganico"],
    "selenio": ["selenio"],
    "zinco": ["zinco", "zinco serico"],
    "ferro": ["ferro", "ferro serico", "sideremia"],
    "ferritina": ["ferritina"],
    "tsh": ["tsh", "hormonio tireoestimulante", "hormonio tiroestimulante", "hormonio tireotrofico", "tirotropina",
            "tsh ultrassensivel", "hormonio estimulante da tireoide"],
    "t4l": ["t4 livre", "t4l", "tiroxina livre"],
    "t3": ["t3", "t3 total", "triiodotironina", "triiodotironina total"],
    "t3r": ["t3 reverso", "t3 reversa", "t3r", "triiodotironina reversa"],
    "fsh": ["fsh", "hormonio foliculo estimulante", "hormonio folículo estimulante"],
    "progesterona": ["progesterona"],
    "cortisol": ["cortisol", "cortisol basal", "cortisol matinal", "cortisol serico"],
    "pth": ["pth", "paratormonio", "hormonio da paratireoide", "paratormonio intacto", "pth intacto"],
    "testosterona": ["testosterona", "testosterona total"],
    "prolactina": ["prolactina"],
    "estradiol": ["estradiol"],
    "acth": ["acth", "hormonio adrenocorticotrofico", "corticotrofina"],
    "aldosterona": ["aldosterona"],
    "androstenediona": ["androstenediona", "delta 4 androstenediona"],
    "dhea": ["dhea s", "dheas", "s dhea", "sdhea", "sulfato de dehidroepiandrosterona", "sulfato de deidroepiandrosterona",
             "dehidroepiandrosterona sulfato"],
    "dht": ["dht", "dihidrotestosterona", "di hidrotestosterona", "diidrotestosterona"],
    "serotonina": ["serotonina"],
    "igf1": ["igf 1", "igf1", "somatomedina c", "igf 1 somatomedina c"],
    "shbg": ["shbg", "globulina ligadora de hormonios sexuais", "globulina de ligacao dos hormonios sexuais"],
    "homocisteina": ["homocisteina"],
    "pcr": ["pcr", "proteina c reativa", "pcr ultrassensivel", "proteina c reativa ultrassensivel", "pcr us"],
    "transferrina": ["transferrina"],
    "vitamina_d": ["vitamina d", "25 hidroxivitamina d", "25 hidroxi vitamina d", "25 oh vitamina d", "25(oh)d",
                   "25 (oh) vitamina d", "25(oh) vitamina d", "vitamina d3", "vitamina d 25 hidroxi", "25 hidroxicolecalciferol"],
    "vitamina_b12": ["vitamina b12", "vitamina b 12", "cianocobalamina", "cobalamina"],
    "vitamina_c": ["vitamina c", "acido ascorbico"],
    # parecidos que NÃO são o exame da tabela
    None: ["calcio ionico", "calcio ionizado", "testosterona livre", "testosterona biodisponivel", "t4 total", "t4",
           "tiroxina total", "t3 livre", "nao hdl", "nao hdl colesterol", "colesterol nao hdl", "vitamina d 1,25",
           "1,25 dihidroxi", "1,25 di hidroxi", "ferro capacidade", "indice de saturacao", "saturacao", "hemoglobina fetal",
           "eritrocitos na urina", "hemacias na urina", "glicose na urina", "relacao", "estimativa", "glicemia media",
           "ureia urinaria", "creatinina urinaria", "clearance", "proteinas", "albumina", "hemoglobina a2", "ck mb",
           "linfocitos atipicos", "linfocitos reativos", "monocitos atipicos"],
}

# conversões quando o laboratório usa outra unidade (unidade do laudo, sem acento e minúscula -> fator para a da tabela)
CONVERTE = {
    "vitamina_d": {"nmol/l": 1 / 2.496},
    "testosterona": {"nmol/l": 28.84},
    "glicose": {"mmol/l": 18.0},
    "colesterol_total": {"mmol/l": 38.67}, "hdl": {"mmol/l": 38.67}, "ldl": {"mmol/l": 38.67}, "vldl": {"mmol/l": 38.67},
    "triglicerides": {"mmol/l": 88.57},
    "creatinina": {"umol/l": 1 / 88.4, "µmol/l": 1 / 88.4, "μmol/l": 1 / 88.4},
    "vitamina_b12": {"pmol/l": 1.355},
    "ferritina": {},   # microg/L, µg/L e ng/mL são iguais
}

LABORATORIOS = ["Fleury", "a+ Medicina Diagnóstica", "Delboni Auriemo", "Lavoisier", "Hermes Pardini", "Sabin", "Dasa",
                "CDB", "Alta Diagnósticos", "Salomão Zoppi", "Labi", "Sérgio Franco", "Bronstein", "Lâmina", "DB Diagnósticos",
                "Einstein", "Sírio-Libanês", "Oswaldo Cruz", "Cura", "Richet", "Weinmann", "Exame", "Frischmann Aisengart",
                "Biocenter", "Labs a+", "Lab Rede", "Grupo Pardini", "Diagnósticos da América", "Alvaro", "Hermes",
                "Laboratório São Paulo", "Unimed", "Hapvida", "Amil", "Prevent Senior", "Beneficência Portuguesa",
                "Labclin", "Sollutio", "Biofast", "Hemolab", "LabCenter"]

NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?(?!\d|[.,]\d)|\d+(?:[.,]\d+)?(?!\d|[.,]\d)"
# número solto (não o "1" de "A1C" nem o "4" de "T4")
NUMV = r"(?<![A-Za-zÀ-ÿ\d.,])(?:" + NUM + ")"


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s):
    """minúsculas, sem acento, hífens e sinais como espaço: para comparar nomes de exames"""
    s = sem_acento(s.lower()).replace("\xad", " ").replace("￾", " ")
    s = re.sub(r"[-–—_:;.,*•·]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# lista (nome normalizado, id), do mais comprido para o mais curto
_NOMES = sorted(((norm(n), k) for k, ns in NOMES.items() for n in ns), key=lambda x: -len(x[0]))


def _numero(s):
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


PALAVRA = re.compile(r"[A-Za-zÀ-ÿµμ0-9()]+")


def _exame_no_inicio(linha):
    """(id, resto da linha depois do nome) se a linha começa com o nome de um exame; senão None.
    Compara palavra a palavra (sem acento), então "VITAMINA B-12", "Vitamina B12" e "TGO/AST" casam."""
    todas = [(m, sem_acento(m.group(0).lower())) for m in PALAVRA.finditer(linha)]
    # também sem as palavras entre parênteses no meio: "TIROXINA (T4) LIVRE" = "tiroxina livre"
    sem_par = [(m, p) for m, p in todas if not (p.startswith("(") and p.endswith(")"))]
    for pals in (todas, sem_par):
        if not pals:
            continue
        for nome, k in _NOMES:
            alvo = nome.split()
            if len(alvo) <= len(pals) and [p for _, p in pals[:len(alvo)]] == alvo:
                return k, linha[pals[len(alvo) - 1][0].end():]
    return None


def _ref(texto):
    """referência do laudo, só quando clara: "13,3 a 16,5", "até 190", "acima de 20" (ignora idades: "20 - 59 a:")"""
    t = sem_acento(texto.lower())
    faixas = [m for m in re.finditer(rf"({NUMV})\s*(?:a|-|ate)\s*({NUM})(?!\s*anos)(?!\s*a\s*:)", t)
              if not re.match(r"\s*a\s*:", t[m.end():])]
    if faixas:
        a, b = faixas[-1].group(1), faixas[-1].group(2)
        if _numero(a) is not None and _numero(b) is not None and _numero(a) < _numero(b):
            return f"{a} a {b}"
    m = re.search(rf"(ate|menor que|inferior a|abaixo de|<)\s*({NUM})(?!\s*anos)", t)
    if m:
        return f"até {m.group(2)}"
    m = re.search(rf"(acima de|maior que|superior a|>)\s*({NUM})(?!\s*anos)", t)
    if m:
        return f"acima de {m.group(2)}"
    return None


def _valor(item, texto, unidade_tab):
    """primeiro resultado do texto (com a unidade logo depois); no leucograma, % ou /mm³ conforme a tabela"""
    t = texto.replace("\xa0", " ")
    achados = [(m, _numero(m.group(0))) for m in re.finditer(NUMV, t)]
    achados = [(m, v) for m, v in achados if v is not None]
    if not achados:
        return None
    # números que fazem parte da faixa de referência não são resultado
    ref_ini = None
    mf = re.search(rf"({NUMV})\s*(?:a|-|até|ate)\s*({NUM})", t)
    if mf:
        ref_ini = mf.start()
    candidatos = [(m, v) for m, v in achados if ref_ini is None or m.start() < ref_ini] or achados[:1]
    escolhido, dois = candidatos[0], len(candidatos) >= 2
    if dois and unidade_tab.startswith("/mm"):
        escolhido = candidatos[1]          # "Neutrófilos : 40,3  3.030" -> o absoluto
    m, v = escolhido
    um = re.match(r"\s*([a-zA-Zµμ%/][\w/µμ%³.]*)", t[m.end():])
    unidade = um.group(1).rstrip(".") if um else ""
    resto = t[m.end() + (um.end() if um else 0):]
    # com % e /mm³ na mesma linha, a referência é a do absoluto: não serve para o %
    return v, unidade, None if dois and not unidade_tab.startswith("/mm") else _ref(resto)


def _linhas(pdf):
    linhas = []
    for pg in pdf:
        for l in pg.get_textpage().get_text_range().replace("\r", "").split("\n"):
            l = l.replace("\xad", "-").replace("\xa0", " ").replace("￾", "-").strip()
            if l:
                linhas.append(l)
    # nome do exame quebrado em duas linhas: "CONCENTRAÇÃO DE HEMOGLOBINA" + "CORPUSCULAR MÉDIA:  33,1 g/dL"
    juntas, i = [], 0
    while i < len(linhas):
        l = linhas[i]
        # (só quando a linha de baixo, sozinha, não é outro exame: "HEMOGRAMA" + "Hemoglobina: 13,2" ficam separadas)
        if (i + 1 < len(linhas) and not re.search(r"\d", l) and ":" not in l and len(l) < 60
                and re.match(r"^[A-Za-zÀ-ÿ ()]+:\s*\d", linhas[i + 1]) and not _exame_no_inicio(linhas[i + 1])):
            juntas.append(l + " " + linhas[i + 1])
            i += 2
            continue
        juntas.append(l)
        i += 1
    return juntas


IGNORAR = re.compile(r"^(metodo|material|amostra|resultado|valor(es)? de referencia|unidade|nota|obs|liberado|"
                     r"assinatura|coletado|recebido|data|pagina|interpretacao|exame|laudo)", re.I)


def _data(linhas):
    """data da coleta: a que vem com "coleta"/"coletado"; senão a mais repetida (fora a de nascimento)"""
    for l in linhas:
        n = sem_acento(l.lower())
        m = re.search(r"colet\w*(?:\s+em)?\s*:?\s*(\d{2})/(\d{2})/(\d{4})", n)
        if m:
            return _dt(m)
    datas = Counter()
    for i, l in enumerate(linhas):
        if "nasc" in sem_acento(l.lower()) or (i and "nasc" in sem_acento(linhas[i - 1].lower())):
            continue
        for m in re.finditer(r"(\d{2})/(\d{2})/(\d{4})", l):
            if _dt(m):
                datas[_dt(m)] += 1
    return datas.most_common(1)[0][0] if datas else None


def _dt(m):
    try:
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return d if 2000 <= d.year <= date.today().year + 1 else None
    except ValueError:
        return None


def _laboratorio(texto):
    t = norm(texto)
    for nome in LABORATORIOS:
        if re.search(rf"\b{re.escape(norm(nome))}\b", t):
            return nome
    return ""


def ler(dados, senha="", tabela=None):
    """tabela: {id: item de exames.json} (para a unidade e para pular os calculados)"""
    try:
        pdf = pypdfium2.PdfDocument(dados, password=senha or None)
    except pypdfium2.PdfiumError as e:
        return {"erro": "senha" if "password" in str(e).lower() else "pdf", "valores": {}}
    linhas = _linhas(pdf)
    texto = "\n".join(linhas)
    if len(texto) < 50:
        return {"erro": "sem_texto", "valores": {}, "paginas": len(pdf)}
    tabela = tabela or {}
    valores = {}
    for i, l in enumerate(linhas):
        achou = _exame_no_inicio(l)
        if not achou or achou[0] is None:
            continue
        k, resto = achou
        it = tabela.get(k, {})
        if k in valores or it.get("calculado"):
            continue                       # vale o primeiro resultado de cada exame
        lido, onde = None, l
        if re.search(NUMV, resto):
            lido = _valor(k, resto, it.get("unidade", ""))
        else:
            # modelo em bloco: o resultado vem nas linhas de baixo
            for prox in linhas[i + 1:i + 9]:
                if _exame_no_inicio(prox) and _exame_no_inicio(prox)[0] is not None:
                    break                  # começou outro exame
                p = re.sub(r"^\s*resultado\s*:?\s*", "", prox, flags=re.I)
                if re.match(r"^\s*\d{1,2}/\d{1,2}/\d{2,4}", p):
                    continue                   # data (rodapé, nascimento): não é resultado
                if re.match(rf"^\s*[<>]?\s*({NUM})", p) and not IGNORAR.match(norm(p)):
                    lido, onde = _valor(k, p, it.get("unidade", "")), prox
                    break
        if not lido:
            continue
        v, unidade, ref = lido
        fator = CONVERTE.get(k, {}).get(sem_acento(unidade.lower()).replace("μ", "u").replace("µ", "u"))
        if fator:
            v, ref = v * fator, None       # outra unidade: a referência do laudo não vale para a da tabela
        if it.get("unidade") == "%" and v > 100:
            continue                       # veio o absoluto onde a tabela pede %
        valores[k] = {"valor": round(v, 3), "ref": ref, "linha": onde[:120], "unidade": unidade}
    return {"erro": None, "data": _data(linhas), "laboratorio": _laboratorio(texto), "valores": valores,
            "paginas": len(pdf)}


if __name__ == "__main__":
    import json, sys
    r = ler(open(sys.argv[1], "rb").read(), sys.argv[2] if len(sys.argv) > 2 else "")
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
