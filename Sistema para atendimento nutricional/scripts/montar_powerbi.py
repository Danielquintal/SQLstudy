"""Monta o relatório Power BI (projeto .pbip) no mesmo padrão da página de evolução do paciente.

Uso:  python scripts/montar_powerbi.py [pasta do projeto, padrão Downloads\\teste11]
Precisa do projeto salvo como .pbip (Arquivo -> Salvar como -> Projeto do Power BI) e do Power BI fechado.
- Acrescenta (ou substitui) as medidas do relatório na tabela 'public avaliacao'
- Troca as páginas do relatório por: Composição corporal, Classificações, Circunferências, Dobras cutâneas
"""
import json, re, shutil, sys, uuid
from pathlib import Path

PROJETO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "Downloads"
NOME = "teste11"
MODELO = PROJETO / f"{NOME}.SemanticModel" / "definition" / "tables" / "public avaliacao.tmdl"
PAGINAS = PROJETO / f"{NOME}.Report" / "definition" / "pages"

AV, PAC = "public avaliacao", "public paciente"
DATA = f"'{AV}'[data_avaliacao]"
SCHEMA_VISUAL = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"
SCHEMA_PAGINA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"

# mesmas cores da página web (web/template.html)
FUNDO, SUPERFICIE, TINTA, APAGADO, LINHA = "#F2F6F6", "#FFFFFF", "#13262E", "#5E7178", "#DCE5E6"
MARCA, MARCA_SUAVE = "#12434F", "#C9DCDF"
C = {1: "#12434F", 2: "#1A9E8F", 3: "#E4572E", 4: "#E6A23C", 5: "#7B5EA7", 6: "#3F88C5", 7: "#6B8F71", 8: "#B5577A"}
BOM, RUIM, ATENCAO = "#1F8A5B", "#C2452D", "#A86A12"

# ---------------------------------------------------------------- medidas (DAX)

KPIS = [  # chave, coluna, rótulo, unidade, direção boa, formato
    ("Peso", "peso_kg", "Peso", "kg", -1, "0.0"),
    ("% Gordura", "gordura_pct", "% Gordura", "%", -1, "0.0"),
    ("Massa muscular", "massa_muscular_kg", "Massa muscular", "kg", 1, "0.0"),
    ("MLG", "mlg_kg", "Massa livre de gordura", "kg", 1, "0.0"),
    ("Cintura", "circ_cintura", "Cintura", "cm", -1, "0.0"),
    ("Somatório", "somatorio_dobras_mm", "Somatório de dobras", "mm", -1, "0"),
]
CLASSIF = [  # nome da medida de valor, coluna do valor, formato, nome da classificação, coluna da classificação
    ("IMC atual", "imc", "0.0", "Classificação IMC", "classificacao_imc"),
    ("Gordura dobras atual", "gordura_pct", "0.0", "Classificação gordura", "classificacao_gordura"),
    ("RCQ atual", "rcq", "0.00", "Risco RCQ", "risco_rcq"),
    ("CMB adequação atual", "cmb_adequacao_pct", "0.0", "Classificação CMB", "classificacao_cmb"),
    ("Gordura BIA atual", "bia_gordura_pct", "0.0", "Classificação gordura BIA", "bia_classificacao_gordura"),
]


def ultimo(col, agg="AVERAGE"):
    c = f"'{AV}'[{col}]"
    return f"VAR d = CALCULATE(MAX({DATA}), NOT ISBLANK({c})) RETURN CALCULATE({agg}({c}), {DATA} = d)"


def primeiro(col):
    c = f"'{AV}'[{col}]"
    return f"VAR d = CALCULATE(MIN({DATA}), NOT ISBLANK({c})) RETURN CALCULATE(AVERAGE({c}), {DATA} = d)"


def tom(medida):
    """verde se a classificação é adequada, amarelo para o resto (igual à página web)"""
    return (f"VAR c = [{medida}] RETURN IF(c = \"–\", \"{APAGADO}\", "
            f"IF(CONTAINSSTRING(c, \"eutr\") || CONTAINSSTRING(c, \"adequad\") || CONTAINSSTRING(c, \"excelente\") "
            f"|| CONTAINSSTRING(c, \"risco baixo\"), \"{BOM}\", \"{ATENCAO}\"))")


def medidas():
    m = [  # nome, expressão, formato
        ("Paciente", f"SELECTEDVALUE('{PAC}'[nome], \"Selecione um paciente\")", None),
        ("Altura atual", ultimo("altura_cm"), "0"),
        ("Resumo do período",
         f"VAR n = COUNTROWS('{AV}') RETURN IF(n = 0, \"Nenhuma avaliação no período\", "
         f"n & IF(n = 1, \" avaliação\", \" avaliações\") & \" · \" & FORMAT(MIN({DATA}), \"dd/mm/yyyy\") & \" a \" & "
         f"FORMAT(MAX({DATA}), \"dd/mm/yyyy\") & \" · Altura \" & FORMAT([Altura atual], \"0\") & \" cm\")", None),
    ]
    for chave, col, _, unid, direcao, fmt in KPIS:
        c = f"'{AV}'[{col}]"
        m += [
            (f"{chave} atual", ultimo(col), fmt),
            (f"{chave} inicial", primeiro(col), fmt),
            (f"{chave} variação",
             f"VAR a = [{chave} inicial] VAR b = [{chave} atual] VAR dif = b - a "
             f"VAR d = CALCULATE(MIN({DATA}), NOT ISBLANK({c})) "
             f"RETURN IF(ISBLANK(a) || ISBLANK(b) || CALCULATE(COUNTROWS('{AV}'), NOT ISBLANK({c})) < 2, "
             f"\"uma avaliação no período\", IF(dif > 0, \"+\", IF(dif < 0, \"−\", \"±\")) & "
             f"FORMAT(ABS(dif), \"0.0\") & \" {unid} desde \" & FORMAT(d, \"dd/mm/yyyy\"))", None),
            (f"{chave} cor",
             f"VAR dif = [{chave} atual] - [{chave} inicial] RETURN IF(ISBLANK(dif) || ABS(dif) < 0.05, \"{APAGADO}\", "
             f"IF(SIGN(dif) = {direcao}, \"{BOM}\", \"{RUIM}\"))", None),
        ]
    for valor, col, fmt, classe, col_classe in CLASSIF:
        m += [
            (valor, ultimo(col), fmt),
            (classe, f"{ultimo(col_classe, 'MAX').replace('RETURN ', 'VAR r = ')} RETURN IF(ISBLANK(r), \"–\", r)", None),
            (f"Cor {classe}", tom(classe), None),
        ]
    m += [
        ("Peso ideal", f"{ultimo('peso_ideal', 'MAX').replace('RETURN ', 'VAR r = ')} "
                       f"RETURN IF(ISBLANK(r), \"–\", SUBSTITUTE(SUBSTITUTE(r, \"Kg\", \" kg\"), \".\", \",\"))", None),
        ("Peso ideal situação",
         f"VAR t = SUBSTITUTE(SUBSTITUTE([Peso ideal], \" kg\", \"\"), \".\", \",\") VAR p = SEARCH(\" a \", t, 1, 0) "
         f"VAR lo = IFERROR(VALUE(LEFT(t, p - 1)), BLANK()) VAR hi = IFERROR(VALUE(MID(t, p + 3, 20)), BLANK()) "
         f"VAR peso = [Peso atual] RETURN IF(p = 0 || ISBLANK(lo) || ISBLANK(hi) || ISBLANK(peso), \"–\", "
         f"IF(peso > hi, FORMAT(peso - hi, \"0.0\") & \" kg acima da faixa\", "
         f"IF(peso < lo, FORMAT(lo - peso, \"0.0\") & \" kg abaixo da faixa\", \"Dentro da faixa\")))", None),
        ("Cor peso ideal", f"IF([Peso ideal situação] = \"Dentro da faixa\", \"{BOM}\", "
                           f"IF([Peso ideal situação] = \"–\", \"{APAGADO}\", \"{ATENCAO}\"))", None),
    ]
    return m


PASTA = "Relatório"  # pasta de exibição das medidas geradas; serve para trocá-las numa nova execução


def gravar_medidas():
    tmdl = MODELO.read_text(encoding="utf-8")
    # remove as medidas geradas antes (bloco "\tmeasure ..." até a linha em branco, com a pasta Relatório)
    tmdl = re.sub(r"\tmeasure [^\n]*\n(?:\t\t[^\n]*\n)*?\t\tdisplayFolder: " + PASTA + r"\n(?:\t\t[^\n]*\n)*\n", "", tmdl)
    bloco = ""
    for nome, expr, fmt in medidas():
        bloco += f"\tmeasure '{nome}' = {expr}\n"
        if fmt:
            bloco += f"\t\tformatString: {fmt}\n"
        bloco += f"\t\tdisplayFolder: {PASTA}\n\t\tlineageTag: {uuid.uuid4()}\n\n"
    pos = tmdl.index(f"\tpartition '{AV}'")
    MODELO.write_text(tmdl[:pos] + bloco + tmdl[pos:], encoding="utf-8")


# ---------------------------------------------------------------- visuais (PBIR)

def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def cor(hexa):
    return {"solid": {"color": lit(f"'{hexa}'")}}


def cor_medida(medida):
    return {"solid": {"color": {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": AV}}, "Property": medida}}}}}


def coluna(prop, ent=AV):
    return {"Column": {"Expression": {"SourceRef": {"Entity": ent}}, "Property": prop}}


def medida(prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": AV}}, "Property": prop}}


def media(prop):
    return {"Aggregation": {"Expression": coluna(prop), "Function": 1}}


def proj(field, ref, nome=None, **extra):
    p = {"field": field, "queryRef": ref, "nativeQueryRef": nome or ref.split(".")[-1]}
    if nome:
        p["displayName"] = nome
    p.update(extra)
    return p


def caixa(fundo=SUPERFICIE, borda=True, raio=14, sombra=False, pad=(12, 16, 12, 16), titulo=None):
    o = {
        "background": [{"properties": {"show": lit("true" if fundo else "false"),
                                       **({"color": cor(fundo), "transparency": lit("0D")} if fundo else {})}}],
        "border": [{"properties": {"show": lit("true" if borda else "false"), "color": cor(LINHA), "radius": lit(f"{raio}D")}}],
        "dropShadow": [{"properties": {"show": lit("true" if sombra else "false")}}],
        "padding": [{"properties": {k: lit(f"{v}D") for k, v in zip(("top", "right", "bottom", "left"), pad)}}],
        "title": [{"properties": {"show": lit("false")}}],
    }
    if titulo:
        o["title"] = [{"properties": {"show": lit("true"), "text": lit(f"'{titulo}'"), "fontSize": lit("13D"),
                                      "bold": lit("true"), "fontColor": cor(TINTA)}}]
    return o


class Pagina:
    def __init__(self, nome, titulo, altura=1080):
        self.nome, self.titulo, self.altura, self.visuais, self.z = nome, titulo, altura, [], 0

    def add(self, x, y, w, h, visual):
        self.z += 1000
        nome = uuid.uuid4().hex[:20]
        self.visuais.append({"$schema": SCHEMA_VISUAL, "name": nome,
                             "position": {"x": x, "y": y, "z": self.z, "height": h, "width": w, "tabOrder": self.z},
                             "visual": visual})

    def gravar(self):
        pasta = PAGINAS / self.nome
        (pasta / "visuals").mkdir(parents=True)
        pagina = {"$schema": SCHEMA_PAGINA, "name": self.nome, "displayName": self.titulo,
                  "displayOption": "FitToWidth" if self.altura > 1080 else "FitToPage", "height": self.altura, "width": 1920,
                  "objects": {"background": [{"properties": {"color": cor(FUNDO), "transparency": lit("0D")}}],
                              "outspace": [{"properties": {"color": cor(FUNDO), "transparency": lit("0D")}}]}}
        (pasta / "page.json").write_text(json.dumps(pagina, ensure_ascii=False, indent=2), encoding="utf-8")
        for v in self.visuais:
            d = pasta / "visuals" / v["name"]
            d.mkdir()
            (d / "visual.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")


def texto(paragrafos, fundo=None, borda=False, raio=14, pad=(10, 16, 10, 16)):
    """paragrafos = [(texto, tamanho, cor, negrito)]"""
    return {"visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [
                {"textRuns": [{"value": t, "textStyle": {"fontSize": f"{s}pt", "color": c,
                                                         **({"fontWeight": "bold"} if b else {})}}]}
                for t, s, c, b in paragrafos]}}]},
            "visualContainerObjects": caixa(fundo, borda, raio, pad=pad)}


def valor(nome_medida, tamanho, cor_fixa=None, cor_de=None):
    """cartão de várias linhas com um só valor, alinhado à esquerda e sem rótulo"""
    rotulos = {"fontSize": lit(f"{tamanho}D"), "color": cor_medida(cor_de) if cor_de else cor(cor_fixa or TINTA)}
    return {"visualType": "multiRowCard",
            "query": {"queryState": {"Values": {"projections": [proj(medida(nome_medida), f"{AV}.{nome_medida}")]}}},
            "objects": {"dataLabels": [{"properties": rotulos}],
                        "categoryLabels": [{"properties": {"show": lit("false")}}],
                        "card": [{"properties": {"barShow": lit("false"), "outline": lit("'None'"),
                                                 "cardPadding": lit("0D"), "cardBackground": cor(SUPERFICIE)}}]},
            "visualContainerObjects": caixa(None, False, pad=(0, 0, 0, 0)),
            "drillFilterOtherVisuals": True}


def segmentacao(campo, ref, modo, grupo, cabecalho, filtro=None):
    obj = {"data": [{"properties": {"mode": lit(f"'{modo}'")}}],
           "header": [{"properties": {"show": lit("true"), "text": lit(f"'{cabecalho}'"), "fontColor": cor(MARCA_SUAVE),
                                      "textSize": lit("10D")}}],
           "items": [{"properties": {"fontColor": cor(TINTA), "textSize": lit("12D")}}],
           "selection": [{"properties": {"singleSelect": lit("true" if modo == "Dropdown" else "false"),
                                         "selectAllCheckboxEnabled": lit("false")}}]}
    if filtro:
        obj["general"] = [{"properties": {"filter": {"filter": filtro}}}]
    return {"visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [proj(campo, ref, active=True)]}}},
            "objects": obj,
            "visualContainerObjects": caixa(None, False, pad=(4, 4, 4, 4)),
            "syncGroup": {"groupName": grupo, "fieldChanges": True, "filterChanges": True},
            "drillFilterOtherVisuals": True}


def linhas(titulo, series, rotulos=False, casas=1, nota=None):
    """series = [(coluna, nome, cor)]"""
    refs = [(f"Avg({AV}.{c})", n, k, c) for c, n, k in series]
    eixo = {"fontSize": lit("10D"), "labelColor": cor(APAGADO), "showAxisTitle": lit("false")}
    obj = {
        "categoryAxis": [{"properties": {**eixo, "gridlineShow": lit("false"), "axisType": lit("'Continuous'")}}],
        "valueAxis": [{"properties": {**eixo, "gridlineShow": lit("true"), "gridlineColor": cor(LINHA),
                                      "gridlineStyle": lit("'dotted'"), "labelPrecision": lit(f"{casas}L")}}],
        "legend": [{"properties": {"show": lit("true" if len(series) > 1 else "false"), "position": lit("'TopLeft'"),
                                   "labelColor": cor(APAGADO), "fontSize": lit("10D")}}],
        "lineStyles": [{"properties": {"strokeWidth": lit("2D"), "showMarker": lit("true"), "markerSize": lit("4D"),
                                       "lineChartType": lit("'smooth'")}}],
        "dataPoint": [{"properties": {"fill": cor(k)}, "selector": {"metadata": ref}} for ref, _, k, _ in refs],
    }
    if rotulos:
        obj["labels"] = [{"properties": {"show": lit("true"), "fontSize": lit("9D"), "color": cor(TINTA),
                                         "labelPrecision": lit(f"{casas}L")}}]
    return {"visualType": "lineChart",
            "query": {"queryState": {
                "Category": {"projections": [proj(coluna("data_avaliacao"), f"{AV}.data_avaliacao", "Data", active=True)]},
                "Y": {"projections": [proj(media(c), ref, n) for ref, n, _, c in refs]}},
                "sortDefinition": {"sort": [{"field": coluna("data_avaliacao"), "direction": "Ascending"}],
                                   "isDefaultSort": True}},
            "objects": obj,
            "visualContainerObjects": caixa(titulo=titulo + (f" · {nota}" if nota else "")),
            "drillFilterOtherVisuals": True}


def tabela(titulo, colunas):
    """colunas = [(coluna, nome)]; mostra os valores sem somar, da avaliação mais recente para a mais antiga"""
    return {"visualType": "tableEx",
            "query": {"queryState": {"Values": {"projections": [
                proj(coluna(c), f"{AV}.{c}", n) for c, n in [("data_avaliacao", "Data")] + colunas]}},
                "sortDefinition": {"sort": [{"field": coluna("data_avaliacao"), "direction": "Descending"}]}},
            "objects": {"columnHeaders": [{"properties": {"fontColor": cor(APAGADO), "backColor": cor(SUPERFICIE),
                                                          "fontSize": lit("10D"), "bold": lit("true")}}],
                        "values": [{"properties": {"fontColor": cor(TINTA), "backColor": cor(SUPERFICIE),
                                                   "fontSize": lit("10D")}}],
                        "grid": [{"properties": {"gridHorizontal": lit("true"), "gridHorizontalColor": cor(LINHA),
                                                 "gridVertical": lit("false"), "rowPadding": lit("4D")}}],
                        "total": [{"properties": {"totals": lit("false")}}]},
            "visualContainerObjects": caixa(titulo=titulo),
            "drillFilterOtherVisuals": True}


# ---------------------------------------------------------------- páginas

PACIENTE_INICIAL = "Otávio Nogueira Barbosa"   # paciente que já vem escolhido ao abrir o relatório
FILTRO_PACIENTE = {"Version": 2, "From": [{"Name": "p", "Entity": PAC, "Type": 0}],
                   "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "p"}},
                                                                                 "Property": "nome"}}],
                                                    "Values": [[{"Literal": {"Value": f"'{PACIENTE_INICIAL}'"}}]]}}}]}
M, LARG = 24, 1872  # margem e largura útil


def cabecalho(p):
    p.add(0, 0, 1920, 150, texto([("EVOLUÇÃO ANTROPOMÉTRICA", 10, MARCA_SUAVE, False)], fundo=MARCA, raio=0, pad=(22, 24, 0, 24)))
    p.add(M, 52, 1100, 48, valor("Paciente", 26, cor_fixa="#FFFFFF"))
    p.add(M, 102, 1100, 30, valor("Resumo do período", 12, cor_fixa=MARCA_SUAVE))
    p.add(1200, 28, 330, 96, segmentacao(coluna("nome", PAC), f"{PAC}.nome", "Dropdown", "Paciente", "Paciente",
                                         FILTRO_PACIENTE))
    p.add(1550, 28, 346, 96, segmentacao(coluna("data_avaliacao"), f"{AV}.data_avaliacao", "Between", "Periodo", "Período"))


def cartoes(p, y=170, h=130):
    w = (LARG - 5 * 16) / 6
    for i, (chave, _, rotulo, unid, _, _) in enumerate(KPIS):
        x = M + i * (w + 16)
        p.add(x, y, w, h, texto([(f"{rotulo.upper()} ({unid})", 9, APAGADO, False)], fundo=SUPERFICIE, borda=True,
                                pad=(12, 16, 0, 16)))
        p.add(x + 16, y + 38, w - 32, 46, valor(f"{chave} atual", 24))
        p.add(x + 16, y + 88, w - 32, 30, valor(f"{chave} variação", 10, cor_de=f"{chave} cor"))


def classificacoes(p, y=320, h=190):
    itens = [("ÍNDICE DE MASSA CORPORAL (kg/m²)", "IMC atual", "Classificação IMC", "Cor Classificação IMC"),
             ("FAIXA DE PESO IDEAL", "Peso ideal", "Peso ideal situação", "Cor peso ideal"),
             ("% GORDURA (DOBRAS)", "Gordura dobras atual", "Classificação gordura", "Cor Classificação gordura"),
             ("RELAÇÃO CINTURA/QUADRIL", "RCQ atual", "Risco RCQ", "Cor Risco RCQ"),
             ("CMB · % DE ADEQUAÇÃO", "CMB adequação atual", "Classificação CMB", "Cor Classificação CMB"),
             ("% GORDURA (BIOIMPEDÂNCIA)", "Gordura BIA atual", "Classificação gordura BIA", "Cor Classificação gordura BIA")]
    w = (LARG - 5 * 16) / 6
    for i, (rotulo, v, classe, tom_) in enumerate(itens):
        x = M + i * (w + 16)
        p.add(x, y, w, h, texto([(rotulo, 9, APAGADO, False)], fundo=SUPERFICIE, borda=True, pad=(12, 16, 0, 16)))
        p.add(x + 16, y + 40, w - 32, 50, valor(v, 22 if v == "Peso ideal" else 26))
        p.add(x + 16, y + 100, w - 32, 60, valor(classe, 13, cor_de=tom_))


def montar_paginas():
    alto = 360
    comp = Pagina("composicao", "Composição corporal")
    cabecalho(comp); cartoes(comp)
    meio = (LARG - 16) / 2
    comp.add(M, 320, meio, alto, linhas("Peso corporal (kg)", [("peso_kg", "Peso", C[1])], rotulos=True))
    comp.add(M + meio + 16, 320, meio, alto, linhas("Percentual de gordura (%)", [("gordura_pct", "% Gordura", C[3])],
                                                     rotulos=True, nota="dobras cutâneas"))
    comp.add(M, 700, LARG, alto, linhas("Composição corporal (kg)", [
        ("mlg_kg", "Massa livre de gordura", C[1]), ("massa_muscular_kg", "Massa muscular", C[2]),
        ("massa_gordura_kg", "Massa de gordura", C[3])]))

    cls = Pagina("classificacoes", "Classificações")
    cabecalho(cls); cartoes(cls); classificacoes(cls)
    cls.add(M, 530, LARG, 530, tabela("Classificações por avaliação", [
        ("imc", "IMC"), ("classificacao_imc", "Classificação IMC"), ("rcq", "RCQ"), ("risco_rcq", "Risco (RCQ)"),
        ("gordura_pct", "% Gordura"), ("classificacao_gordura", "Classif. gordura"),
        ("bia_gordura_pct", "% Gordura (BIA)"), ("bia_classificacao_gordura", "Classif. (BIA)"),
        ("cmb_adequacao_pct", "Adequação CMB (%)"), ("classificacao_cmb", "Classif. CMB"), ("peso_ideal", "Peso ideal")]))

    circ = Pagina("circunferencias", "Circunferências", altura=1460)
    cabecalho(circ); cartoes(circ)
    dois_tercos = (LARG - 16) * 2 / 3
    circ.add(M, 320, dois_tercos, alto, linhas("Cintura, abdômen e quadril (cm)", [
        ("circ_cintura", "Cintura", C[1]), ("circ_abdomen", "Abdômen", C[2]), ("circ_quadril", "Quadril", C[4])]))
    circ.add(M + dois_tercos + 16, 320, LARG - dois_tercos - 16, alto,
             linhas("Relação cintura/quadril", [("rcq", "RCQ", C[3])], rotulos=True, casas=2))
    circ.add(M, 700, meio, alto, linhas("Membros superiores (cm)", [
        ("braco_relaxado_e", "Braço relaxado E", C[1]), ("braco_relaxado_d", "Braço relaxado D", C[6]),
        ("braco_contraido_e", "Braço contraído E", C[2]), ("braco_contraido_d", "Braço contraído D", C[7]),
        ("antebraco_e", "Antebraço E", C[3]), ("antebraco_d", "Antebraço D", C[4])], nota="E = esquerdo · D = direito"))
    circ.add(M + meio + 16, 700, meio, alto, linhas("Membros inferiores (cm)", [
        ("coxa_proximal_e", "Coxa proximal E", C[1]), ("coxa_proximal_d", "Coxa proximal D", C[6]),
        ("coxa_medial_e", "Coxa medial E", C[2]), ("coxa_medial_d", "Coxa medial D", C[7]),
        ("coxa_distal_e", "Coxa distal E", C[5]), ("coxa_distal_d", "Coxa distal D", C[8]),
        ("panturrilha_e", "Panturrilha E", C[3]), ("panturrilha_d", "Panturrilha D", C[4])], nota="E = esquerdo · D = direito"))
    circ.add(M, 1080, LARG, alto, linhas("Tórax e ombro (cm)", [("circ_torax", "Tórax", C[6]), ("circ_ombro", "Ombro", C[5])]))

    dob = Pagina("dobras", "Dobras cutâneas")
    cabecalho(dob); cartoes(dob)
    um_terco = (LARG - 16) / 3
    dob.add(M, 320, um_terco, alto, linhas("Somatório de dobras (mm)", [("somatorio_dobras_mm", "Somatório", C[3])],
                                           rotulos=True, casas=0))
    dob.add(M + um_terco + 16, 320, LARG - um_terco - 16, alto, linhas("Dobras cutâneas (mm)", [
        ("dobra_tricipital", "Tricipital", C[1]), ("dobra_subescapular", "Subescapular", C[6]),
        ("dobra_toracica", "Torácica", C[2]), ("dobra_axilar_media", "Axilar média", C[7]),
        ("dobra_suprailiaca", "Suprailíaca", C[4]), ("dobra_abdominal", "Abdominal", C[3]), ("dobra_coxa", "Coxa", C[5])]))
    dob.add(M, 700, LARG, 360, tabela("Dobras por avaliação (mm)", [
        ("dobra_tricipital", "Tricipital"), ("dobra_subescapular", "Subescapular"), ("dobra_toracica", "Torácica"),
        ("dobra_axilar_media", "Axilar média"), ("dobra_suprailiaca", "Suprailíaca"), ("dobra_abdominal", "Abdominal"),
        ("dobra_coxa", "Coxa"), ("somatorio_dobras_mm", "Somatório"), ("gordura_pct", "% Gordura")]))

    paginas = [comp, cls, circ, dob]
    for d in PAGINAS.iterdir():
        if d.is_dir():
            shutil.rmtree(d)
    for p in paginas:
        p.gravar()
    meta = json.loads((PAGINAS / "pages.json").read_text(encoding="utf-8"))
    meta["pageOrder"] = [p.nome for p in paginas]
    meta["activePageName"] = paginas[0].nome
    (PAGINAS / "pages.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return paginas


if __name__ == "__main__":
    if not MODELO.exists():
        sys.exit(f"Projeto não encontrado: {MODELO}\nSalve o relatório como .pbip (Arquivo -> Salvar como).")
    gravar_medidas()
    ps = montar_paginas()
    print(f"{len(medidas())} medidas; páginas: " + ", ".join(f"{p.titulo} ({len(p.visuais)} visuais)" for p in ps))
