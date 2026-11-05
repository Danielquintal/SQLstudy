"""Gera o projeto Power BI "Time Exemplo - Consultas" (.pbip) do zero, lendo a planilha do Google.

Uso:  python ferramentas/montar_powerbi.py
Saída: Power BI/Time Exemplo - Consultas.pbip (abra com o Power BI Desktop)
Fundo, logo e cores fictícios (layout de exemplo); dados da planilha "Time Exemplo - Nutrição" (Google Planilhas).
Rodar de novo recria o relatório (as páginas e as medidas): feche o Power BI antes.
"""
import json
import shutil
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REC = Path(__file__).resolve().parent / "recursos"
NOME = "Time Exemplo - Consultas"
SAIDA = RAIZ / "Power BI"
SM = SAIDA / f"{NOME}.SemanticModel"
RP = SAIDA / f"{NOME}.Report"
URL_PADRAO = "https://docs.google.com/spreadsheets/d/COLE-AQUI-O-ID-DA-PLANILHA/edit"

SCHEMA_VISUAL = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"
SCHEMA_PAGINA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
SCHEMA_PAGINAS = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"

# cores do relatório de exemplo (fundo, barras e títulos)
AZUL, AZUL_CLARO, AMARELO, VERDE, ESCURO = "#1F4E79", "#3A6EA5", "#8FA3B8", "#3A6EA5", "#2B3A4A"
TINTA, APAGADO, LINHA, BRANCO = "#1C2430", "#5F6B7A", "#DDE2E8", "#FFFFFF"
SERIES = ["#1F4E79", "#E07A5F", "#81B29A", "#F2CC8F", "#3D405B", "#5FA8D3", "#9C89B8", "#6D6875"]
BOM, RUIM, NEUTRO = "#1F8A5B", "#C2452D", "#5F6B7A"


def gid():
    return str(uuid.uuid4())


# ====================================================================== modelo semântico (TMDL)

def m_bloco(linhas, tabs):
    return "\n".join("\t" * tabs + l for l in linhas.strip("\n").split("\n"))


FUNCOES_M = {
    "fnAba": """
(aba as text) as table =>
let
    Fonte = GoogleSheets.Contents(URL_Planilha),
    Linha = Table.SelectRows(Fonte, each List.Contains(List.Transform(Record.FieldValues(_), each try Text.From(_) otherwise ""), aba)){0},
    Dados = Linha[Data],
    ComCabecalho = if List.Contains(Table.ColumnNames(Dados), "Atleta") or List.Contains(Table.ColumnNames(Dados), "Indicador")
        then Dados else Table.PromoteHeaders(Dados, [PromoteAllScalars = true])
in
    ComCabecalho""",
    "fnTexto": """
(x as any) as nullable text =>
    if x = null then null else let t = Text.Trim(Text.From(x)) in if t = "" then null else t""",
    "fnNumero": """
(x as any) as nullable number =>
    if x = null or x = "" then null else try Number.From(x, "pt-BR") otherwise try Number.From(Text.Replace(Text.From(x), ",", "."), "en-US") otherwise null""",
    "fnData": """
(x as any) as nullable date =>
    if x = null or x = "" then null else try Date.From(x, "pt-BR") otherwise null""",
    "fnHora": """
(x as any) as time =>
    if x = null or x = "" then #time(0, 0, 0)
    else if x is time then x
    else if x is datetime then Time.From(x)
    else if x is number then Time.From(x)
    else try Time.From(Text.From(x), "pt-BR") otherwise #time(0, 0, 0)""",
}


def tipos_m(cols):
    """cols = [(nome, tipo)] tipo: texto, numero, data, hora"""
    f = {"texto": ("fnTexto", "type nullable text"), "numero": ("fnNumero", "type nullable number"),
         "data": ("fnData", "type nullable date"), "hora": ("fnHora", "type time")}
    return ", ".join(f'{{"{n}", {f[t][0]}, {f[t][1]}}}' for n, t in cols)


TABELAS = {
    # nome no modelo: (aba da planilha, colunas [(nome, tipo)], passos extras M, chave obrigatória)
    "Atletas": ("Atletas", [("Atleta", "texto"), ("Nome curto", "texto"), ("Posição 1", "texto"), ("Posição 2", "texto"),
                            ("Posição 3", "texto"), ("Data de nascimento", "data"), ("Peso informado (kg)", "numero"),
                            ("Altura informada (m)", "numero"), ("QUAEST", "texto"), ("Status", "texto")],
                """
    Posicoes = Table.AddColumn(Unicos, "Posições", each Text.Combine(List.RemoveNulls({[Posição 1], [Posição 2], [Posição 3]}), "/"), type text),
    Curto = Table.ReplaceValue(Posicoes, each [Nome curto], each if [Nome curto] = null then [Atleta] else [Nome curto], Replacer.ReplaceValue, {"Nome curto"}),
    Resultado = Table.ReplaceValue(Curto, each [Status], each if [Status] = null then "Ativo" else [Status], Replacer.ReplaceValue, {"Status"})""",
                "Atleta"),
    "Consultas": ("Consultas", [("ID", "numero"), ("Atleta", "texto"), ("Data", "data"), ("Hora", "hora"), ("Duração (min)", "numero"),
                                ("Tipo", "texto"), ("Modalidade", "texto"), ("Status", "texto"), ("Objetivo / queixa", "texto"),
                                ("Resumo e condutas", "texto"), ("Próximo retorno", "data"), ("Nº do atendimento", "numero"),
                                ("Hábitos / recordatório", "texto"), ("Plano entregue", "texto"), ("Suplementação prescrita", "texto"),
                                ("Adesão (0-10)", "numero"), ("Sintomas / observações", "texto")],
                  """
    Inicio = Table.AddColumn(Unicos, "Início", each if [Data] = null then null else [Data] & [Hora], type nullable datetime),
    SemHora = Table.RemoveColumns(Inicio, {"Hora"}),
    Resultado = Table.ReplaceValue(SemHora, each [Status], each if [Status] = null then "Agendada" else [Status], Replacer.ReplaceValue, {"Status"})""",
                  "Atleta"),
    "Avaliacoes": ("Avaliações", [("Atleta", "texto"), ("Data", "data"), ("Peso (kg)", "numero"), ("Altura (cm)", "numero"),
                                  ("Dobra tríceps (mm)", "numero"), ("Dobra subescapular (mm)", "numero"),
                                  ("Dobra peitoral (mm)", "numero"), ("Dobra axilar média (mm)", "numero"),
                                  ("Dobra suprailíaca (mm)", "numero"), ("Dobra abdominal (mm)", "numero"),
                                  ("Dobra coxa medial (mm)", "numero"), ("Circ. braço relaxado (cm)", "numero"),
                                  ("Circ. braço contraído (cm)", "numero"), ("Circ. cintura (cm)", "numero"),
                                  ("Circ. coxa medial (cm)", "numero"), ("Massa muscular (kg)", "numero"),
                                  ("% água corporal", "numero"), ("Observações", "texto")],
                   """
    ComData = Table.SelectRows(Unicos, each [Data] <> null),
    Resultado = ComData""",
                   "Atleta"),
    "Referencias": ("Referências", [("Indicador", "texto"), ("Valor", "numero"), ("Unidade", "texto"), ("Fonte", "texto")],
                    """
    Resultado = Unicos""", "Indicador"),
}

TIPO_TMDL = {"texto": "string", "numero": "double", "data": "dateTime", "hora": "dateTime"}


def m_tabela(nome):
    aba, cols, extra, chave = TABELAS[nome]
    sel = ", ".join(f'"{c}"' for c, _ in cols)
    distinto = f'Table.Distinct(Linhas, {{"{chave}"}})' if nome == "Atletas" else "Linhas"
    return f"""
let
    Fonte = fnAba("{aba}"),
    Colunas = Table.SelectColumns(Fonte, {{{sel}}}, MissingField.UseNull),
    Tipos = Table.TransformColumns(Colunas, {{{tipos_m(cols)}}}),
    Linhas = Table.SelectRows(Tipos, each [{chave}] <> null),
    Unicos = {distinto},{extra}
in
    Resultado"""


def col_fonte(nome, tipo):
    t = TIPO_TMDL[tipo]
    out = [f"\tcolumn '{nome}'", f"\t\tdataType: {t}"]
    if tipo == "data":
        out.append("\t\tformatString: dd/mm/yyyy")
    if tipo == "numero":
        out.append("\t\tformatString: 0.0")
    out += [f"\t\tlineageTag: {gid()}", f"\t\tsummarizeBy: {'average' if tipo == 'numero' else 'none'}",
            f"\t\tsourceColumn: {nome}", ""]
    if tipo == "data":
        out += ["\t\tannotation UnderlyingDateTimeDataType = Date", ""]
    return out


# colunas calculadas (DAX): tabela -> [(nome, expressão, tipo TMDL, formato)]
DOBRAS7 = ["Dobra tríceps (mm)", "Dobra subescapular (mm)", "Dobra peitoral (mm)", "Dobra axilar média (mm)",
           "Dobra suprailíaca (mm)", "Dobra abdominal (mm)", "Dobra coxa medial (mm)"]
DOBRAS_FK = ["Dobra tríceps (mm)", "Dobra subescapular (mm)", "Dobra suprailíaca (mm)", "Dobra abdominal (mm)"]


def soma(cols):
    tem = " || ".join(f"ISBLANK(Avaliacoes[{c}])" for c in cols)
    return f"IF({tem}, BLANK(), " + " + ".join(f"Avaliacoes[{c}]" for c in cols) + ")"


CALC = {
    "Atletas": [
        # sem CALCULATE (transição de contexto) para não criar dependência circular entre as colunas
        ("Consultas realizadas", 'VAR a = Atletas[Atleta] RETURN COUNTROWS(FILTER(Consultas, Consultas[Atleta] = a && Consultas[Status] = "Realizada")) + 0', "int64", "0"),
        ("Próxima consulta", 'VAR a = Atletas[Atleta] RETURN MINX(FILTER(Consultas, Consultas[Atleta] = a && Consultas[Status] IN {"Agendada", "Confirmada"} && Consultas[Início] >= NOW()), Consultas[Início])', "dateTime", "dd/mm/yyyy hh:nn"),
        ("Acompanhamento", 'IF(Atletas[Consultas realizadas] > 0, "Em acompanhamento", IF(NOT ISBLANK(Atletas[Próxima consulta]), "1ª consulta marcada", "Sem consulta"))', "string", None),
        ("Avaliações feitas", "VAR a = Atletas[Atleta] RETURN COUNTROWS(FILTER(Avaliacoes, Avaliacoes[Atleta] = a)) + 0", "int64", "0"),
    ],
    "Consultas": [
        ("Nome curto", "RELATED(Atletas[Nome curto])", "string", None),
        ("Posição", "RELATED(Atletas[Posição 1])", "string", None),
        ("Semana", "IF(ISBLANK(Consultas[Data]), BLANK(), Consultas[Data] - WEEKDAY(Consultas[Data], 2) + 1)", "dateTime", "dd/mm/yyyy"),
        ("Quando", 'IF(Consultas[Início] >= NOW(), "Próxima", "Passada")', "string", None),
        ("Data e hora", 'FORMAT(Consultas[Início], "dd/mm/yyyy hh:nn")', "string", None),
    ],
    "Avaliacoes": [
        ("Nome curto", "RELATED(Atletas[Nome curto])", "string", None),
        ("Posição", "RELATED(Atletas[Posição 1])", "string", None),
        ("Idade", "VAR n = RELATED(Atletas[Data de nascimento]) RETURN IF(ISBLANK(n) || ISBLANK(Avaliacoes[Data]), BLANK(), INT(YEARFRAC(n, Avaliacoes[Data])))", "int64", "0"),
        ("Soma 7 dobras (mm)", soma(DOBRAS7), "double", "0.0"),
        ("% Gordura Pollock 7", "VAR s = Avaliacoes[Soma 7 dobras (mm)] VAR i = Avaliacoes[Idade] RETURN IF(ISBLANK(s) || ISBLANK(i), BLANK(), "
                                "495 / (1.112 - 0.00043499 * s + 0.00000055 * s * s - 0.00028826 * i) - 450)", "double", "0.0"),
        ("% Gordura Faulkner", f"VAR s = {soma(DOBRAS_FK)} RETURN IF(ISBLANK(s), BLANK(), 0.153 * s + 5.783)", "double", "0.0"),
        ("% Gordura", "IF(NOT ISBLANK(Avaliacoes[% Gordura Faulkner]), Avaliacoes[% Gordura Faulkner], Avaliacoes[% Gordura Pollock 7])", "double", "0.0"),
        ("Massa adiposa (kg)", "IF(ISBLANK(Avaliacoes[% Gordura]) || ISBLANK(Avaliacoes[Peso (kg)]), BLANK(), Avaliacoes[Peso (kg)] * Avaliacoes[% Gordura] / 100)", "double", "0.0"),
        ("Massa livre de gordura (kg)", "IF(ISBLANK(Avaliacoes[Massa adiposa (kg)]), BLANK(), Avaliacoes[Peso (kg)] - Avaliacoes[Massa adiposa (kg)])", "double", "0.0"),
        ("IMC", "IF(ISBLANK(Avaliacoes[Altura (cm)]) || Avaliacoes[Altura (cm)] = 0, BLANK(), Avaliacoes[Peso (kg)] / (Avaliacoes[Altura (cm)] / 100) ^ 2)", "double", "0.0"),
        ("Nº da avaliação", "COUNTROWS(FILTER(Avaliacoes, Avaliacoes[Atleta] = EARLIER(Avaliacoes[Atleta]) && Avaliacoes[Data] <= EARLIER(Avaliacoes[Data])))", "int64", "0"),
    ],
}

# indicadores da avaliação: (chave, coluna, unidade, direção boa: 1 sobe, -1 desce, 0 neutra, formato)
IND = [
    ("Peso", "Peso (kg)", "kg", 0, "0.0"),
    ("% Gordura", "% Gordura", "%", -1, "0.0"),
    ("Massa muscular", "Massa muscular (kg)", "kg", 1, "0.0"),
    ("Massa adiposa", "Massa adiposa (kg)", "kg", -1, "0.0"),
    ("MLG", "Massa livre de gordura (kg)", "kg", 1, "0.0"),
    ("Água", "% água corporal", "%", 1, "0.0"),
    ("IMC", "IMC", "kg/m²", 0, "0.0"),
    ("Soma 7 dobras", "Soma 7 dobras (mm)", "mm", -1, "0"),
]


def ultimo(col, ext="MAX"):
    c = f"Avaliacoes[{col}]"
    return (f"AVERAGEX(VALUES(Avaliacoes[Atleta]), VAR d = CALCULATE({ext}(Avaliacoes[Data]), NOT ISBLANK({c})) "
            f"RETURN CALCULATE(AVERAGE({c}), Avaliacoes[Data] = d))")


ATIVAS = '{"Agendada", "Confirmada"}'
MEDIDAS = {  # tabela -> [(nome, expressão, formato)]
    "Atletas": [
        ("Total de atletas", 'CALCULATE(COUNTROWS(Atletas), Atletas[Status] <> "Inativo") + 0', "0"),
        ("QUAEST respondidos", 'CALCULATE(COUNTROWS(Atletas), Atletas[QUAEST] = "Respondido", Atletas[Status] <> "Inativo") + 0', "0"),
        ("Em acompanhamento", 'CALCULATE(COUNTROWS(Atletas), Atletas[Acompanhamento] = "Em acompanhamento", Atletas[Status] <> "Inativo") + 0', "0"),
        ("Sem consulta", 'CALCULATE(COUNTROWS(Atletas), Atletas[Acompanhamento] = "Sem consulta", Atletas[Status] <> "Inativo") + 0', "0"),
        ("% em acompanhamento", "DIVIDE([Em acompanhamento], [Total de atletas])", "0%"),
        ("Atleta selecionado", 'IF(HASONEVALUE(Atletas[Atleta]), VALUES(Atletas[Atleta]), "Todos os atletas · escolha um atleta no filtro")', None),
        ("Ficha do atleta",
         'IF(HASONEVALUE(Atletas[Atleta]), "Posições: " & COALESCE(SELECTEDVALUE(Atletas[Posições]), "–") & "   ·   " & '
         'SELECTEDVALUE(Atletas[Acompanhamento]) & "   ·   " & FORMAT(SELECTEDVALUE(Atletas[Consultas realizadas]), "0") & " consulta(s) realizada(s)", '
         '"Time Exemplo · time de flag football")', None),
        ("Próxima consulta (texto)",
         f'VAR d = CALCULATE(MIN(Consultas[Início]), Consultas[Status] IN {ATIVAS}, Consultas[Início] >= NOW()) '
         'RETURN IF(ISBLANK(d), "Nenhuma consulta marcada", FORMAT(d, "dd/mm/yyyy") & " às " & FORMAT(d, "hh:nn"))', None),
        ("Último resumo",
         'VAR d = CALCULATE(MAX(Consultas[Início]), Consultas[Status] = "Realizada") '
         'RETURN IF(ISBLANK(d), "Nenhuma consulta realizada ainda.", FORMAT(d, "dd/mm/yyyy") & " · " & '
         'COALESCE(CALCULATE(MAX(Consultas[Resumo e condutas]), Consultas[Início] = d, Consultas[Status] = "Realizada"), "(sem resumo escrito)"))', None),
        ("Próximo retorno (texto)",
         'VAR d = CALCULATE(MAX(Consultas[Próximo retorno]), Consultas[Status] = "Realizada") '
         'RETURN IF(ISBLANK(d), "–", FORMAT(d, "dd/mm/yyyy") & IF(d < TODAY(), " (atrasado)", ""))', None),
        ("Cor do retorno",
         f'VAR d = CALCULATE(MAX(Consultas[Próximo retorno]), Consultas[Status] = "Realizada") '
         f'RETURN IF(NOT ISBLANK(d) && d < TODAY(), "{RUIM}", "{TINTA}")', None),
    ],
    "Consultas": [
        ("Total de consultas", "COUNTROWS(Consultas) + 0", "0"),
        ("Realizadas", 'CALCULATE(COUNTROWS(Consultas), Consultas[Status] = "Realizada") + 0', "0"),
        ("Faltas", 'CALCULATE(COUNTROWS(Consultas), Consultas[Status] = "Faltou") + 0', "0"),
        ("Próximas", f"CALCULATE(COUNTROWS(Consultas), Consultas[Status] IN {ATIVAS}, Consultas[Início] >= NOW()) + 0", "0"),
        ("Próximos 7 dias", f"CALCULATE(COUNTROWS(Consultas), Consultas[Status] IN {ATIVAS}, Consultas[Início] >= NOW(), Consultas[Início] < NOW() + 7) + 0", "0"),
        ("Não confirmadas", 'CALCULATE(COUNTROWS(Consultas), Consultas[Status] = "Agendada", Consultas[Início] >= NOW()) + 0', "0"),
        ("Taxa de comparecimento", 'VAR r = [Realizadas] VAR f = [Faltas] RETURN IF(r + f = 0, BLANK(), DIVIDE(r, r + f))', "0%"),
        ("Adesão média", "AVERAGE(Consultas[Adesão (0-10)])", "0.0"),
        ("Adesão média (texto)", 'IF(ISBLANK([Adesão média]), "–", FORMAT([Adesão média], "0.0"))', None),
        ("Atendimentos por atleta", 'DIVIDE([Realizadas], CALCULATE(DISTINCTCOUNT(Consultas[Atleta]), Consultas[Status] = "Realizada"))', "0.0"),
        ("Taxa de comparecimento (texto)", 'IF(ISBLANK([Taxa de comparecimento]), "–", FORMAT([Taxa de comparecimento], "0%"))', None),
    ],
    "Avaliacoes": [("Avaliações", "COUNTROWS(Avaliacoes) + 0", "0")],
}
for chave, col, unid, dirb, fmt in IND:
    c = f"Avaliacoes[{col}]"
    MEDIDAS["Avaliacoes"] += [
        (f"{chave} atual", ultimo(col), fmt),
        (f"{chave} inicial", ultimo(col, "MIN"), fmt),
        (f"{chave} média", f"AVERAGE({c})", fmt),
        (f"{chave} atual (texto)", f'IF(ISBLANK([{chave} atual]), "–", FORMAT([{chave} atual], "{fmt}"))', None),
        (f"{chave} variação",
         f"VAR n = CALCULATE(COUNTROWS(Avaliacoes), NOT ISBLANK({c})) VAR dif = [{chave} atual] - [{chave} inicial] "
         f"RETURN IF(n < 2 || ISBLANK(dif), \"1ª avaliação\", IF(dif > 0, \"+\", IF(dif < 0, \"−\", \"±\")) & FORMAT(ABS(dif), \"{fmt}\") & \" {unid} desde a 1ª\")", None),
        (f"{chave} cor",
         f"VAR dif = [{chave} atual] - [{chave} inicial] RETURN IF(ISBLANK(dif) || ABS(dif) < 0.05 || {dirb} = 0, \"{NEUTRO}\", "
         f"IF(SIGN(dif) = {dirb}, \"{BOM}\", \"{RUIM}\"))", None),
    ]
MEDIDAS["Avaliacoes"] += [
    ("Ref. massa muscular", 'CALCULATE(MAX(Referencias[Valor]), Referencias[Indicador] = "Massa muscular (kg)")', "0.00"),
    ("Ref. massa adiposa", 'CALCULATE(MAX(Referencias[Valor]), Referencias[Indicador] = "Massa adiposa (kg)")', "0.00"),
    ("Dif. massa muscular × ref.", "DIVIDE([Massa muscular atual] - [Ref. massa muscular], [Ref. massa muscular])", "+0.0%;-0.0%;0.0%"),
    ("Dif. massa adiposa × ref.", "DIVIDE([Massa adiposa atual] - [Ref. massa adiposa], [Ref. massa adiposa])", "+0.0%;-0.0%;0.0%"),
    ("Comparativo massa muscular (texto)",
     'IF(ISBLANK([Massa muscular atual]) || ISBLANK([Ref. massa muscular]), "Sem dados ainda", '
     'FORMAT([Massa muscular atual], "0.00") & " kg × referência " & FORMAT([Ref. massa muscular], "0.00") & " kg (" & FORMAT([Dif. massa muscular × ref.], "+0.0%;-0.0%") & ")")', None),
    ("Comparativo massa adiposa (texto)",
     'IF(ISBLANK([Massa adiposa atual]) || ISBLANK([Ref. massa adiposa]), "Sem dados ainda", '
     'FORMAT([Massa adiposa atual], "0.00") & " kg × referência " & FORMAT([Ref. massa adiposa], "0.00") & " kg (" & FORMAT([Dif. massa adiposa × ref.], "+0.0%;-0.0%") & ")")', None),
]
TABELA_DA_MEDIDA = {n: t for t, ms in MEDIDAS.items() for n, _, _ in ms}


def tabela_tmdl(nome):
    aba, cols, _, _ = TABELAS[nome]
    out = [f"table {nome}", f"\tlineageTag: {gid()}", ""]
    for n, expr, fmt in MEDIDAS.get(nome, []):
        out.append(f"\tmeasure '{n}' = {expr}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += ["\t\tdisplayFolder: Relatório", f"\t\tlineageTag: {gid()}", ""]
    for n, tipo in cols:
        if n == "Hora":
            continue
        out += col_fonte(n, tipo)
    if nome == "Atletas":
        out += col_fonte("Posições", "texto")
    if nome == "Consultas":
        out += ["\tcolumn 'Início'", "\t\tdataType: dateTime", "\t\tformatString: dd/mm/yyyy hh:nn", f"\t\tlineageTag: {gid()}",
                "\t\tsummarizeBy: none", "\t\tsourceColumn: Início", ""]
    for n, expr, tipo, fmt in CALC.get(nome, []):
        out.append(f"\tcolumn '{n}' = {expr}")
        out.append(f"\t\tdataType: {tipo}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tlineageTag: {gid()}", "\t\tsummarizeBy: none", ""]
    out += [f"\tpartition {nome} = m", "\t\tmode: import", "\t\tsource =", m_bloco(m_tabela(nome), 4), "",
            "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def gravar_modelo():
    d = SM / "definition"
    (d / "tables").mkdir(parents=True)
    (d / "cultures").mkdir()
    (SM / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
    (SM / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NOME}, "config": {"version": "2.0", "logicalId": gid()}}, indent=2),
        encoding="utf-8")
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1606\n\n", encoding="utf-8")
    ordem = list(TABELAS)
    model = ["model Model", "\tculture: pt-BR", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tsourceQueryCulture: pt-BR",
             "\tvalueFilterBehavior: independent", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
             "annotation __PBI_TimeIntelligenceEnabled = 0", "",
             "annotation PBI_QueryOrder = " + json.dumps(["URL_Planilha"] + list(FUNCOES_M) + ordem, ensure_ascii=False), "",
             'annotation PBI_ProTooling = ["DevMode"]', ""]
    model += [f"ref table {t}" for t in ordem] + ["", "ref cultureInfo pt-BR", ""]
    (d / "model.tmdl").write_text("\n".join(model), encoding="utf-8")
    exp = [f'expression URL_Planilha = "{URL_PADRAO}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
           f"\tlineageTag: {gid()}", "", "\tannotation PBI_ResultType = Text", ""]
    for n, corpo in FUNCOES_M.items():
        exp += [f"expression {n} =", m_bloco(corpo, 2), f"\tlineageTag: {gid()}", "", "\tannotation PBI_ResultType = Function", ""]
    (d / "expressions.tmdl").write_text("\n".join(exp), encoding="utf-8")
    rel = []
    for t in ("Consultas", "Avaliacoes"):
        rel += [f"relationship {gid()}", f"\tfromColumn: {t}.Atleta", "\ttoColumn: Atletas.Atleta", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel), encoding="utf-8")
    (d / "cultures" / "pt-BR.tmdl").write_text("cultureInfo pt-BR\n\n", encoding="utf-8")
    for t in ordem:
        (d / "tables" / f"{t}.tmdl").write_text(tabela_tmdl(t), encoding="utf-8")


# ====================================================================== relatório (PBIR)

def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def cor(h):
    return {"solid": {"color": lit(f"'{h}'")}}


def col(ent, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": ent}}, "Property": prop}}


def med(prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": TABELA_DA_MEDIDA[prop]}}, "Property": prop}}


def agg(ent, prop, f=1):  # 0 soma, 1 média, 2 contagem distinta, 3 mín, 4 máx, 5 contagem
    return {"Aggregation": {"Expression": col(ent, prop), "Function": f}}


def proj(field, ref, nome=None, **extra):
    p = {"field": field, "queryRef": ref, "nativeQueryRef": nome or ref.split(".")[-1]}
    if nome:
        p["displayName"] = nome
    p.update(extra)
    return p


def pm(nome, rotulo=None):
    return proj(med(nome), f"{TABELA_DA_MEDIDA[nome]}.{nome}", rotulo)


def pc(ent, prop, rotulo=None, **e):
    return proj(col(ent, prop), f"{ent}.{prop}", rotulo, **e)


def caixa(fundo=BRANCO, borda=True, titulo=None, raio=10, sombra=True, pad=(10, 14, 10, 14), cor_titulo=BRANCO):
    o = {"background": [{"properties": {"show": lit("true" if fundo else "false"),
                                        **({"color": cor(fundo), "transparency": lit("0D")} if fundo else {})}}],
         "border": [{"properties": {"show": lit("true" if borda else "false"), "color": cor(LINHA), "radius": lit(f"{raio}D")}}],
         "dropShadow": [{"properties": {"show": lit("true" if sombra and fundo else "false"), "shadowSpread": lit("2D")}}],
         "padding": [{"properties": {k: lit(f"{v}D") for k, v in zip(("top", "right", "bottom", "left"), pad)}}],
         "title": [{"properties": {"show": lit("false")}}]}
    if titulo:  # faixa escura do título, como no relatório de exemplo
        o["title"] = [{"properties": {"show": lit("true"), "text": lit(f"'{titulo}'"), "fontSize": lit("13D"), "bold": lit("true"),
                                      "fontColor": cor(cor_titulo), "background": cor(ESCURO), "alignment": lit("'center'"),
                                      "fontFamily": lit("'Arial'")}}]
    return o


def texto(paragrafos, fundo=None, borda=False, pad=(6, 12, 6, 12)):
    return {"visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [
                {"textRuns": [{"value": t, "textStyle": {"fontSize": f"{s}pt", "color": c, "fontFamily": "Arial",
                                                         **({"fontWeight": "bold"} if b else {})}}]} for t, s, c, b in paragrafos]}}]},
            "visualContainerObjects": caixa(fundo, borda, sombra=False, pad=pad)}


def valor(nome, tam, cor_fixa=None, cor_de=None):
    rot = {"fontSize": lit(f"{tam}D"), "fontFamily": lit("'Arial'"), "color": {"solid": {"color": {"expr": med(cor_de)}}} if cor_de else cor(cor_fixa or TINTA)}
    return {"visualType": "multiRowCard",
            "query": {"queryState": {"Values": {"projections": [pm(nome)]}}},
            "objects": {"dataLabels": [{"properties": rot}], "categoryLabels": [{"properties": {"show": lit("false")}}],
                        "card": [{"properties": {"barShow": lit("false"), "outline": lit("'None'"), "cardPadding": lit("0D"),
                                                 "cardBackground": cor(BRANCO)}}]},
            "visualContainerObjects": caixa(None, False, sombra=False, pad=(0, 0, 0, 0)),
            "drillFilterOtherVisuals": True}


def filtro_categ(ent, prop, valores):
    return {"filters": [{"name": uuid.uuid4().hex[:20], "field": col(ent, prop), "type": "Categorical",
                         "filter": {"Version": 2, "From": [{"Name": "t", "Entity": ent, "Type": 0}],
                                    "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}}],
                                                                    "Values": [[{"Literal": {"Value": f"'{v}'"}}] for v in valores]}}}]},
                         "howCreated": "User"}]}


def segmentacao(ent, prop, modo, grupo, cabecalho):
    return {"visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [pc(ent, prop, active=True)]}}},
            "objects": {"data": [{"properties": {"mode": lit(f"'{modo}'")}}],
                        "header": [{"properties": {"show": lit("true"), "text": lit(f"'{cabecalho}'"), "fontColor": cor(APAGADO),
                                                   "textSize": lit("10D"), "fontFamily": lit("'Arial'")}}],
                        "items": [{"properties": {"fontColor": cor(TINTA), "textSize": lit("11D")}}],
                        "selection": [{"properties": {"singleSelect": lit("false"), "selectAllCheckboxEnabled": lit("true")}}]},
            "visualContainerObjects": caixa(BRANCO, True, sombra=False, pad=(4, 8, 4, 8)),
            "syncGroup": {"groupName": grupo, "fieldChanges": True, "filterChanges": True},
            "drillFilterOtherVisuals": True}


def eixos(casas=1, legenda=True):
    e = {"fontSize": lit("10D"), "labelColor": cor(APAGADO), "showAxisTitle": lit("false"), "fontFamily": lit("'Arial'")}
    return {"categoryAxis": [{"properties": {**e}}],
            "valueAxis": [{"properties": {**e, "gridlineShow": lit("true"), "gridlineColor": cor(LINHA),
                                          "gridlineStyle": lit("'dotted'"), "labelPrecision": lit(f"{casas}L")}}],
            "legend": [{"properties": {"show": lit("true" if legenda else "false"), "position": lit("'Top'"),
                                       "labelColor": cor(APAGADO), "fontSize": lit("10D")}}],
            "labels": [{"properties": {"show": lit("true"), "fontSize": lit("9D"), "color": cor(TINTA), "labelPrecision": lit(f"{casas}L")}}]}


def grafico(tipo, titulo, categoria, ys, serie=None, casas=1, ordem=None, rotulos=True):
    """ys = [(projeção, cor)]"""
    q = {"Category": {"projections": [dict(categoria, active=True)]}, "Y": {"projections": [p for p, _ in ys]}}
    if serie:
        q["Series"] = {"projections": [serie]}
    obj = eixos(casas, legenda=len(ys) > 1 or bool(serie))
    if not rotulos:
        obj["labels"][0]["properties"]["show"] = lit("false")
    if not serie:
        obj["dataPoint"] = [{"properties": {"fill": cor(k)}, "selector": {"metadata": p["queryRef"]}} for p, k in ys]
    v = {"visualType": tipo, "query": {"queryState": q}, "objects": obj,
         "visualContainerObjects": caixa(titulo=titulo), "drillFilterOtherVisuals": True}
    if ordem:
        v["query"]["sortDefinition"] = {"sort": [ordem], "isDefaultSort": True}
    return v


def rosca(titulo, categoria, y):
    return {"visualType": "donutChart",
            "query": {"queryState": {"Category": {"projections": [dict(categoria, active=True)]}, "Y": {"projections": [y]}}},
            "objects": {"legend": [{"properties": {"show": lit("true"), "position": lit("'Bottom'"), "fontSize": lit("10D")}}],
                        "labels": [{"properties": {"show": lit("true"), "labelStyle": lit("'Category, data value'"), "fontSize": lit("10D")}}]},
            "visualContainerObjects": caixa(titulo=titulo), "drillFilterOtherVisuals": True}


def tabela(titulo, colunas, ordem=None):
    v = {"visualType": "tableEx",
         "query": {"queryState": {"Values": {"projections": colunas}}},
         "objects": {"columnHeaders": [{"properties": {"fontColor": cor(BRANCO), "backColor": cor(AZUL), "fontSize": lit("12D"),
                                                       "bold": lit("true"), "fontFamily": lit("'Arial'")}}],
                     "values": [{"properties": {"fontColor": cor(TINTA), "backColor": cor(BRANCO), "fontSize": lit("12D"),
                                                "fontFamily": lit("'Arial'"), "wordWrap": lit("true")}}],
                     "grid": [{"properties": {"gridHorizontal": lit("true"), "gridHorizontalColor": cor(LINHA),
                                              "gridVertical": lit("false"), "rowPadding": lit("6D")}}],
                     "total": [{"properties": {"totals": lit("false")}}]},
         "visualContainerObjects": caixa(titulo=titulo), "drillFilterOtherVisuals": True}
    if ordem:
        v["query"]["sortDefinition"] = {"sort": [ordem]}
    return v


def imagem(arquivo):
    return {"visualType": "image",
            "objects": {"image": [{"properties": {"sourceFile": {"image": {"name": lit(f"'{arquivo}'"),
                                                                           "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": arquivo}}},
                                                                           "scaling": lit("'Fit'")}}}}]},
            "visualContainerObjects": caixa(BRANCO, True, pad=(6, 6, 6, 6)), "drillFilterOtherVisuals": True}


FUNDO_IMG = "fundo_exemplo.jpg"


class Pagina:
    def __init__(self, nome, titulo, subtitulo):
        self.nome, self.titulo, self.visuais, self.z = nome, titulo, [], 0
        self.add(610, 58, 1290, 56, texto([(titulo.upper(), 24, AZUL, True)]))
        self.add(610, 112, 1290, 34, texto([(subtitulo, 12, APAGADO, False)]))
        self.add(0, 1026, 1920, 50, {"visualType": "pageNavigator", "drillFilterOtherVisuals": True})

    def add(self, x, y, w, h, visual, filtros=None):
        self.z += 1000
        v = {"$schema": SCHEMA_VISUAL, "name": uuid.uuid4().hex[:20],
             "position": {"x": x, "y": y, "z": self.z, "height": h, "width": w, "tabOrder": self.z}, "visual": visual}
        if filtros:
            v["filterConfig"] = filtros
        self.visuais.append(v)

    def filtros_topo(self, periodo=("Avaliacoes", "Data")):
        self.add(610, 156, 380, 74, segmentacao("Atletas", "Atleta", "Dropdown", "Atleta", "Atleta"))
        self.add(1006, 156, 200, 74, segmentacao("Atletas", "Posição 1", "Dropdown", "Posicao", "Posição"))
        if periodo:
            self.add(1222, 156, 420, 74, segmentacao(*periodo, "Between", "Periodo_" + periodo[0], "Período"))

    def gravar(self, pasta):
        p = pasta / self.nome
        (p / "visuals").mkdir(parents=True)
        pg = {"$schema": SCHEMA_PAGINA, "name": self.nome, "displayName": self.titulo, "displayOption": "FitToPage",
              "height": 1080, "width": 1920,
              "objects": {"background": [{"properties": {"color": cor(VERDE), "image": {"image": {
                  "name": lit(f"'{FUNDO_IMG}'"),
                  "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": FUNDO_IMG}}},
                  "scaling": lit("'Normal'")}}, "transparency": lit("0D")}}]}}
        (p / "page.json").write_text(json.dumps(pg, ensure_ascii=False, indent=2), encoding="utf-8")
        for v in self.visuais:
            d = p / "visuals" / v["name"]
            d.mkdir()
            (d / "visual.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")


def cartao(p, x, y, w, h, rotulo, medida, var=None, cor_var=None, tam=30):
    p.add(x, y, w, h, texto([(rotulo, 10, BRANCO, True)], fundo=ESCURO, pad=(6, 12, 6, 12)))
    p.add(x, y + 34, w, h - 34, texto([("", 8, TINTA, False)], fundo=BRANCO, borda=True))
    p.add(x + 12, y + 44, w - 24, 52, valor(medida, tam))
    if var:
        p.add(x + 12, y + h - 40, w - 24, 30, valor(var, 10, cor_de=cor_var))


def linha_cartoes(p, y, itens, h=140, x0=40, larg=1840):
    n = len(itens)
    w = (larg - (n - 1) * 16) / n
    for i, it in enumerate(itens):
        cartao(p, x0 + i * (w + 16), y, w, h, *it)


def montar_paginas():
    S = lambda ent, prop: {"field": col(ent, prop), "direction": "Ascending"}
    D = lambda ent, prop: {"field": col(ent, prop), "direction": "Descending"}
    pags = []

    # 1. Aba inicial ------------------------------------------------------------------
    p = Pagina("inicio", "Aba inicial", "Acompanhamento nutricional da time de flag football · consultas e avaliações")
    p.filtros_topo(periodo=None)
    linha_cartoes(p, 250, [("Atletas", "Total de atletas"), ("QUAEST respondidos", "QUAEST respondidos"),
                           ("Em acompanhamento", "Em acompanhamento"), ("Sem consulta", "Sem consulta"),
                           ("Próximos 7 dias", "Próximos 7 dias"), ("Comparecimento", "Taxa de comparecimento")])
    p.add(40, 410, 900, 600, tabela("Próximas consultas", [pc("Consultas", "Início", "Data e hora"), pc("Consultas", "Atleta"),
                                                           pc("Consultas", "Posição"), pc("Consultas", "Tipo"), pc("Consultas", "Status")],
                                    ordem=S("Consultas", "Início")),
          filtro_categ("Consultas", "Quando", ["Próxima"]))
    p.add(956, 410, 420, 600, rosca("Situação do acompanhamento", pc("Atletas", "Acompanhamento"), pm("Total de atletas", "Atletas")))
    p.add(1392, 410, 488, 600, tabela("Atletas sem consulta", [pc("Atletas", "Atleta"), pc("Atletas", "Posições")],
                                      ordem=S("Atletas", "Atleta")),
          filtro_categ("Atletas", "Acompanhamento", ["Sem consulta"]))
    pags.append(p)

    # 2. Consultas ----------------------------------------------------------------------
    p = Pagina("consultas", "Consultas", "Agenda, comparecimento e condutas de cada consulta")
    p.filtros_topo(periodo=("Consultas", "Data"))
    linha_cartoes(p, 250, [("Consultas", "Total de consultas"), ("Realizadas", "Realizadas"), ("Faltas", "Faltas"),
                           ("Próximas", "Próximas"), ("Não confirmadas", "Não confirmadas"), ("Adesão média (0-10)", "Adesão média")])
    p.add(40, 410, 1200, 290, grafico("clusteredColumnChart", "Consultas por semana", pc("Consultas", "Semana", "Semana"),
                                      [(pm("Total de consultas", "Consultas"), SERIES[0])], serie=pc("Consultas", "Status"), casas=0,
                                      ordem=S("Consultas", "Semana")))
    p.add(1256, 410, 624, 290, rosca("Tipo de consulta", pc("Consultas", "Tipo"), pm("Total de consultas", "Consultas")))
    p.add(40, 716, 1840, 294, tabela("Todas as consultas", [pc("Consultas", "Início", "Data e hora"), pc("Consultas", "Atleta"),
                                                            pc("Consultas", "Nº do atendimento", "Nº"),
                                                            pc("Consultas", "Tipo"), pc("Consultas", "Modalidade"), pc("Consultas", "Status"),
                                                            pc("Consultas", "Resumo e condutas"), pc("Consultas", "Adesão (0-10)", "Adesão"),
                                                            pc("Consultas", "Próximo retorno")],
                                     ordem=D("Consultas", "Início")))
    pags.append(p)

    # 3. Resumo de cada atleta ------------------------------------------------------------
    p = Pagina("resumo_atleta", "Resumo de cada atleta", "Escolha um atleta no filtro: ficha, última avaliação, evolução e histórico")
    p.filtros_topo()
    p.add(40, 250, 1100, 54, valor("Atleta selecionado", 22, cor_fixa=AZUL))
    p.add(40, 300, 1100, 34, valor("Ficha do atleta", 12, cor_fixa=APAGADO))
    p.add(1156, 250, 360, 84, texto([("PRÓXIMA CONSULTA", 9, APAGADO, True)], fundo=BRANCO, borda=True))
    p.add(1168, 282, 340, 40, valor("Próxima consulta (texto)", 14, cor_fixa=AZUL))
    p.add(1532, 250, 348, 84, texto([("PRÓXIMO RETORNO", 9, APAGADO, True)], fundo=BRANCO, borda=True))
    p.add(1544, 282, 330, 40, valor("Próximo retorno (texto)", 14, cor_de="Cor do retorno"))
    linha_cartoes(p, 350, [(f"{r}", f"{k} atual", f"{k} variação", f"{k} cor", 26) for r, k in
                           [("Peso (kg)", "Peso"), ("% Gordura", "% Gordura"), ("Massa muscular (kg)", "Massa muscular"),
                            ("Massa adiposa (kg)", "Massa adiposa"), ("% Água corporal", "Água"), ("IMC (kg/m²)", "IMC")]], h=150)
    p.add(40, 516, 900, 300, grafico("lineChart", "Evolução: peso e massa muscular (kg)", pc("Avaliacoes", "Data", "Data"),
                                     [(pm("Peso média", "Peso"), SERIES[0]), (pm("Massa muscular média", "Massa muscular"), SERIES[1]),
                                      (pm("Massa adiposa média", "Massa adiposa"), SERIES[2])], ordem=S("Avaliacoes", "Data")))
    p.add(956, 516, 924, 300, tabela("Histórico de atendimentos", [pc("Consultas", "Nº do atendimento", "Nº"), pc("Consultas", "Início", "Data"),
                                                                pc("Consultas", "Status"), pc("Consultas", "Resumo e condutas"),
                                                                pc("Consultas", "Plano entregue"), pc("Consultas", "Suplementação prescrita", "Suplementação"),
                                                                pc("Consultas", "Adesão (0-10)", "Adesão")],
                                     ordem=D("Consultas", "Início")))
    p.add(40, 832, 1840, 178, texto([("ÚLTIMA CONSULTA · RESUMO E CONDUTAS", 9, APAGADO, True)], fundo=BRANCO, borda=True))
    p.add(56, 862, 1808, 140, valor("Último resumo", 12))
    pags.append(p)

    # 4. Composição corporal ----------------------------------------------------------------
    p = Pagina("composicao", "Composição corporal", "Última avaliação de cada atleta · % de gordura por Faulkner (ou Pollock 7 quando faltam dobras)")
    p.filtros_topo()
    linha_cartoes(p, 250, [("Peso médio (kg)", "Peso atual"), ("% Gordura média", "% Gordura atual"),
                           ("Massa muscular média (kg)", "Massa muscular atual"), ("Massa adiposa média (kg)", "Massa adiposa atual"),
                           ("Avaliações", "Avaliações")])
    p.add(40, 410, 1840, 300, grafico("clusteredColumnChart", "Massa muscular, massa adiposa e peso por atleta (kg)",
                                      pc("Atletas", "Nome curto", "Atleta"),
                                      [(pm("Massa muscular atual", "Massa muscular"), SERIES[1]), (pm("Massa adiposa atual", "Massa adiposa"), SERIES[2]),
                                       (pm("Peso atual", "Peso"), SERIES[0])]))
    p.add(40, 726, 1200, 284, grafico("clusteredColumnChart", "% de gordura por atleta", pc("Atletas", "Nome curto", "Atleta"),
                                      [(pm("% Gordura atual", "% Gordura"), SERIES[0])]))
    p.add(1256, 726, 624, 284, grafico("clusteredBarChart", "Média por posição (kg)", pc("Atletas", "Posição 1", "Posição"),
                                       [(pm("Massa muscular atual", "Massa muscular"), SERIES[1]), (pm("Massa adiposa atual", "Massa adiposa"), SERIES[2])]))
    pags.append(p)

    # 5. Avaliação antropométrica -----------------------------------------------------------
    p = Pagina("antropometria", "Avaliação antropométrica", "Dobras cutâneas e circunferências (média das avaliações no período)")
    p.filtros_topo()
    p.add(40, 250, 1100, 760, grafico("barChart", "Dobras cutâneas por atleta (mm)", pc("Avaliacoes", "Nome curto", "Atleta"),
                                      [(proj(agg("Avaliacoes", c), f"Avg(Avaliacoes.{c})", c.replace(" (mm)", "").replace("Dobra ", "")), SERIES[i])
                                       for i, c in enumerate(["Dobra abdominal (mm)", "Dobra suprailíaca (mm)", "Dobra tríceps (mm)",
                                                              "Dobra coxa medial (mm)", "Dobra peitoral (mm)", "Dobra subescapular (mm)",
                                                              "Dobra axilar média (mm)"])], casas=0, rotulos=False))
    p.add(1156, 250, 724, 760, tabela("Circunferências e somatório (cm · mm)", [
        pc("Avaliacoes", "Nome curto", "Atleta"),
        proj(agg("Avaliacoes", "Circ. braço relaxado (cm)"), "Avg(Avaliacoes.Circ. braço relaxado (cm))", "Braço relax."),
        proj(agg("Avaliacoes", "Circ. braço contraído (cm)"), "Avg(Avaliacoes.Circ. braço contraído (cm))", "Braço contr."),
        proj(agg("Avaliacoes", "Circ. cintura (cm)"), "Avg(Avaliacoes.Circ. cintura (cm))", "Cintura"),
        proj(agg("Avaliacoes", "Circ. coxa medial (cm)"), "Avg(Avaliacoes.Circ. coxa medial (cm))", "Coxa"),
        proj(agg("Avaliacoes", "Soma 7 dobras (mm)"), "Avg(Avaliacoes.Soma 7 dobras (mm))", "Σ 7 dobras")],
        ordem=S("Avaliacoes", "Nome curto")))
    pags.append(p)

    # 6. Percentual de água corporal ---------------------------------------------------------
    p = Pagina("agua", "Percentual de água corporal", "Hidratação na última avaliação de cada atleta")
    p.filtros_topo()
    linha_cartoes(p, 250, [("% Água média", "Água atual"), ("Peso médio (kg)", "Peso atual"),
                           ("IMC médio", "IMC atual")], larg=1100)
    p.add(1156, 250, 724, 140, texto([("Bioimpedância: % de água corporal em relação ao peso.", 11, APAGADO, False),
                                      ("Referência usual para homens adultos: cerca de 50 a 65%.", 11, APAGADO, False)],
                                     fundo=BRANCO, borda=True))
    p.add(40, 410, 1840, 600, grafico("clusteredColumnChart", "% de água corporal por atleta", pc("Atletas", "Nome curto", "Atleta"),
                                      [(pm("Água atual", "% água corporal"), SERIES[0])]))
    pags.append(p)

    # 7. Comparativo × referência -------------------------------------------------------------
    p = Pagina("comparativo", "Time Exemplo × referência", "Média do grupo × valores de referência (aba Referências da planilha)")
    p.filtros_topo()
    for i, (rot, m, ref, dif) in enumerate([("MASSA MUSCULAR (kg)", "Comparativo massa muscular (texto)", "Ref. massa muscular", "Dif. massa muscular × ref."),
                                            ("MASSA ADIPOSA (kg)", "Comparativo massa adiposa (texto)", "Ref. massa adiposa", "Dif. massa adiposa × ref.")]):
        y = 250 + i * 190
        p.add(40, y, 1100, 174, texto([(rot, 11, BRANCO, True)], fundo=ESCURO))
        p.add(40, y + 36, 1100, 138, texto([("", 8, TINTA, False)], fundo=BRANCO, borda=True))
        p.add(60, y + 56, 1060, 60, valor(m, 22, cor_fixa=AZUL))
        p.add(60, y + 118, 1060, 40, texto([("Time Exemplo (média da última avaliação) × referência. A diferença também depende do método "
                                             "(bioimpedância × equações antropométricas).", 10, APAGADO, False)]))
    p.add(1156, 250, 724, 360, texto([("REFERÊNCIA", 11, BRANCO, True), ("Valores da aba Referências da planilha.", 12, TINTA, False),
                                      ("Ex.: perfil cineantropométrico de atletas de elite de flag football (Front. Nutr. 2025).", 11, APAGADO, False)],
                                     fundo=BRANCO, borda=True))
    p.add(40, 640, 1840, 370, grafico("clusteredColumnChart", "Por posição: massa muscular e massa adiposa (kg) × referência",
                                      pc("Atletas", "Posição 1", "Posição"),
                                      [(pm("Massa muscular atual", "Massa muscular"), SERIES[1]), (pm("Ref. massa muscular", "Ref. massa muscular"), SERIES[5]),
                                       (pm("Massa adiposa atual", "Massa adiposa"), SERIES[2]), (pm("Ref. massa adiposa", "Ref. massa adiposa"), SERIES[4])]))
    pags.append(p)

    # 8. Evolução do grupo ----------------------------------------------------------------------
    p = Pagina("evolucao", "Evolução do grupo", "Média do grupo em cada data de avaliação")
    p.filtros_topo()
    p.add(40, 250, 1200, 380, grafico("lineChart", "Massa muscular e massa adiposa (kg)", pc("Avaliacoes", "Data", "Data"),
                                      [(pm("Massa muscular média", "Massa muscular"), SERIES[1]), (pm("Massa adiposa média", "Massa adiposa"), SERIES[2])],
                                      ordem=S("Avaliacoes", "Data")))
    p.add(1256, 250, 624, 380, grafico("clusteredColumnChart", "Avaliações por data", pc("Avaliacoes", "Data", "Data"),
                                       [(pm("Avaliações"), SERIES[0])], casas=0, ordem=S("Avaliacoes", "Data")))
    p.add(40, 646, 1200, 364, grafico("lineChart", "% de gordura e % de água corporal", pc("Avaliacoes", "Data", "Data"),
                                      [(pm("% Gordura média", "% Gordura"), SERIES[3]), (pm("Água média", "% água"), SERIES[4])],
                                      ordem=S("Avaliacoes", "Data")))
    p.add(1256, 646, 624, 364, tabela("Variação desde a 1ª avaliação", [
        pc("Atletas", "Nome curto", "Atleta"), pm("Peso variação", "Peso"), pm("% Gordura variação", "% Gordura"),
        pm("Massa muscular variação", "Massa muscular")], ordem=S("Atletas", "Nome curto")))
    pags.append(p)
    return pags


def gravar_relatorio():
    d = RP / "definition"
    pastas = d / "pages"
    pastas.mkdir(parents=True)
    rec = RP / "StaticResources"
    (rec / "SharedResources" / "BaseThemes").mkdir(parents=True)
    (rec / "RegisteredResources").mkdir(parents=True)
    shutil.copy(REC / "Fluent2-CY26SU08.json", rec / "SharedResources" / "BaseThemes")
    for f in (FUNDO_IMG,):
        shutil.copy(REC / f, rec / "RegisteredResources" / f)
    (RP / "definition.pbir").write_text(json.dumps({"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NOME}.SemanticModel"}}}, indent=2), encoding="utf-8")
    (RP / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NOME}, "config": {"version": "2.0", "logicalId": gid()}}, indent=2), encoding="utf-8")
    (d / "version.json").write_text(json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}, indent=2), encoding="utf-8")
    versao = {"visual": "2.12.0", "report": "3.4.0", "page": "2.3.1"}
    rel = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
           "themeCollection": {"baseTheme": {"name": "Fluent2-CY26SU08", "reportVersionAtImport": versao, "type": "SharedResources"}},
           "objects": {"section": [{"properties": {"verticalAlignment": lit("'Top'")}}],
                       "outspacePane": [{"properties": {"expanded": lit("false")}}]},
           "resourcePackages": [{"name": "SharedResources", "type": "SharedResources", "items": [
               {"name": "Fluent2-CY26SU08", "path": "BaseThemes/Fluent2-CY26SU08.json", "type": "BaseTheme"}]},
               {"name": "RegisteredResources", "type": "RegisteredResources", "items": [
                   {"name": f, "path": f, "type": "Image"} for f in (FUNDO_IMG,)]}],
           "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                        "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                        "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}}
    (d / "report.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    pags = montar_paginas()
    for p in pags:
        p.gravar(pastas)
    (pastas / "pages.json").write_text(json.dumps({"$schema": SCHEMA_PAGINAS, "pageOrder": [p.nome for p in pags],
                                                   "activePageName": pags[0].nome}, ensure_ascii=False, indent=2), encoding="utf-8")
    return pags


if __name__ == "__main__":
    url_atual = None
    exp = SM / "definition" / "expressions.tmdl"
    if exp.exists():  # mantém o link da planilha que você já colou
        t = exp.read_text(encoding="utf-8")
        if 'expression URL_Planilha = "' in t:
            url_atual = t.split('expression URL_Planilha = "', 1)[1].split('"', 1)[0]
    for alvo in (SM, RP):
        if alvo.exists():
            shutil.rmtree(alvo)
    if url_atual and "COLE-AQUI" not in url_atual:
        URL_PADRAO = url_atual
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / f"{NOME}.pbip").write_text(json.dumps({"version": "1.0", "artifacts": [{"report": {"path": f"{NOME}.Report"}}],
                                                    "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")
    gravar_modelo()
    ps = gravar_relatorio()
    n_med = sum(len(v) for v in MEDIDAS.values())
    print(f"ok: {SAIDA / (NOME + '.pbip')}\n{n_med} medidas · {sum(len(v) for v in CALC.values())} colunas calculadas · páginas: "
          + ", ".join(f"{p.titulo} ({len(p.visuais)})" for p in ps))
