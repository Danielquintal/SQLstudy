"""Importação do treino do MFIT Personal pelo PDF que o paciente vê (o MFIT não tem API pública).

Dois formatos:
  - Rotina detalhada (uma sessão por página): nome do aluno, "Rotina: ...", objetivo, nível, título da sessão e os
    exercícios com "Séries:", "Carga:", "Intervalo:", "Instruções:"; blocos "Exercícios combinados" (alternar) e
    "Ou substitua por:".
  - Resumo "Rotinas de Treinos": nome da rotina, período, objetivo e nível, e "Treino 1..N" com os grupos musculares
    e o começo da descrição.
"""
import re

CHAVES = {"series": r"S[ée]ries:", "carga": r"Carga:", "intervalo": r"Intervalo:"}
IGNORAR = re.compile(r"^(Você (ainda não )?realizou.*|VER TREINO|Histórico.*|Evolução|Orientações gerais|\$|[!\s]+|"
                     r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}|Página \d+ de \d+|\d+x\s*\.*)$", re.I)


class ErroMfit(Exception):
    pass


def _limpa(l):
    l = re.sub(r"[-]", "", l).replace("￾", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", l).strip()


def _texto(conteudo):
    import io
    import pypdfium2 as pdfium
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(conteudo))
    except Exception:   # noqa: BLE001
        raise ErroMfit("o arquivo não é um PDF válido") from None
    return [[_limpa(l) for l in pdf[i].get_textpage().get_text_range().splitlines()] for i in range(len(pdf))]


def ler(conteudo):
    """PDF -> {"rotina", "objetivo", "nivel", "periodo", "nome", "sessoes": [...]}"""
    paginas = _texto(conteudo)
    todas = [l for p in paginas for l in p if l]
    if not todas:
        raise ErroMfit("o PDF não tem texto (é uma foto?). Exporte o treino do MFIT em PDF")
    if todas[0].lower().startswith("rotinas de treinos"):
        return _ler_resumo(todas)
    if any(l.startswith("Rotina:") for l in todas[:4]):
        return _ler_detalhado(paginas)
    raise ErroMfit("não reconheci este PDF como um treino do MFIT")


def _ler_detalhado(paginas):
    r = {"rotina": None, "objetivo": None, "nivel": None, "periodo": None, "nome": None, "sessoes": []}
    for pag in paginas:
        linhas = [l for l in pag if l]
        i = 0
        if linhas and len(linhas) > 3 and linhas[1].startswith("Rotina:"):      # cabeçalho de cada página
            r["nome"] = r["nome"] or linhas[0]
            r["rotina"] = r["rotina"] or linhas[1].split(":", 1)[1].strip()
            r["objetivo"], r["nivel"] = r["objetivo"] or linhas[2], r["nivel"] or linhas[3]
            i = 4
        if i >= len(linhas):
            continue
        titulo = linhas[i]
        i += 1
        if r["sessoes"] and r["sessoes"][-1]["nome"] == titulo:
            sessao = r["sessoes"][-1]                                              # continua da página anterior
        else:
            sessao = {"nome": titulo, "exercicios": []}
            r["sessoes"].append(sessao)
        corpo = linhas[i:]
        grupo, n_grupo, atual, ultimo_campo, modo, substituto = None, 0, None, None, None, False
        for k, l in enumerate(corpo):
            if l.startswith("Exercícios combinados"):
                n_grupo += 1
                grupo, atual, modo = n_grupo, None, None
                continue
            if l in ("Alterne esses exercícios", ""):
                continue
            if l.startswith("Ou substitua por"):
                substituto, atual, modo = True, None, None
                continue
            campo = _campo(l)
            if campo and atual is not None:
                valor = l.split(":", 1)[1].strip()
                if campo == "series" and atual["series"] and atual["series"][-1].get("series"):
                    atual["series"].append({})                                     # mais uma linha de série (pirâmide)
                if not atual["series"]:
                    atual["series"].append({})
                atual["series"][-1][campo] = valor
                ultimo_campo, modo = campo, "campos"
                continue
            if _instrucoes(l) and atual is not None:
                modo = "instr"
                continue
            minuscula = l[:1].islower() or l[:1] in "\"'(0123456789"
            if atual is not None and minuscula and modo == "campos" and ultimo_campo:
                atual["series"][-1][ultimo_campo] += " " + l                       # valor quebrado em duas linhas
                continue
            if atual is not None and modo == "instr" and not _e_nome(corpo, k):
                atual["instrucoes"] = (atual["instrucoes"] + " " + l).strip()
                continue
            if atual is not None and modo is None and not atual["series"] and _continua_nome(atual["nome"], l):
                atual["nome"] = f"{atual['nome']} {l}"                             # nome quebrado em duas linhas
                continue
            atual = {"nome": l, "series": [], "instrucoes": "", "grupo": grupo, "substituto": substituto}
            sessao["exercicios"].append(atual)
            modo, ultimo_campo, substituto = None, None, False
    for s in r["sessoes"]:
        s["exercicios"] = [e for e in s["exercicios"] if e["nome"] and not IGNORAR.match(e["nome"])]
    if not any(s["exercicios"] for s in r["sessoes"]):
        raise ErroMfit("não encontrei exercícios neste PDF")
    return r


CONECTIVOS = {"com", "de", "da", "do", "das", "dos", "na", "no", "em", "para", "e", "a", "o", "ao", "sem", "pelo", "pela"}


def _campo(l):
    return next((k for k, rx in CHAVES.items() if re.match(rx, l, re.I)), None)


def _instrucoes(l):
    return l.startswith("Instruç") and l.rstrip().endswith(":")


def _e_chave(l):
    return bool(_campo(l) or _instrucoes(l) or l.startswith(("Exercícios combinados", "Ou substitua por")))


def _e_nome(corpo, k):
    """corpo[k] é nome de exercício? Começa com maiúscula e logo depois (1 ou 2 linhas, se o nome quebrou)
    vem "Séries:", "Carga:", "Intervalo:" ou "Instruções:", ou outro nome/bloco"""
    l = corpo[k]
    if not l[:1].isupper() or _e_chave(l) or l.endswith((".", ",", ";")):
        return False
    for j in (k + 1, k + 2):
        if j >= len(corpo):
            return j == k + 1
        if _e_chave(corpo[j]):
            return True
        if j == k + 1 and not _continua_nome(l, corpo[j]):
            return False
    return False


def _continua_nome(nome, l):
    """a linha l é o resto de um nome que quebrou ("Rotacak externa de ombro com" + "bastão")?"""
    if _e_chave(l):
        return False
    ultima = nome.split()[-1].lower() if nome.split() else ""
    return l[:1].islower() or len(l.split()) == 1 or ultima in CONECTIVOS


def _ler_resumo(linhas):
    r = {"rotina": None, "objetivo": None, "nivel": None, "periodo": None, "nome": None, "sessoes": []}
    i = 1
    if i < len(linhas):
        r["rotina"] = linhas[i]
        i += 1
    while i < len(linhas) and not re.match(r"^Treino \d+$", linhas[i]):
        l = linhas[i]
        if re.search(r"\d{2}/\d{2}/\d{4}", l):
            r["periodo"] = l
        elif not IGNORAR.match(l) and r["objetivo"] is None:
            partes = l.split()
            niveis = [p for p in partes if p.lower() in ("iniciante", "intermediário", "intermediario", "avançado", "avancado", "adaptação", "adaptacao")]
            r["nivel"] = niveis[0] if niveis else None
            r["objetivo"] = " ".join(p for p in partes if p not in niveis) or None
        i += 1
    sessao = None
    for l in linhas[i:]:
        if re.match(r"^Treino \d+$", l):
            sessao = {"nome": l, "exercicios": [], "grupos": ""}
            r["sessoes"].append(sessao)
        elif sessao is not None and not IGNORAR.match(l):
            if not sessao["grupos"]:
                sessao["grupos"] = l
                sessao["nome"] = f"{sessao['nome']} · {l}"
            else:
                sessao["exercicios"].append({"nome": l.rstrip(". "), "series": [], "instrucoes": "", "grupo": None,
                                             "substituto": False, "resumo": True})
    if not r["sessoes"]:
        raise ErroMfit("não encontrei os treinos neste PDF")
    return r


def gravar(cur, pid, dados, arquivo, fonte="mfit"):
    from psycopg.types.json import Jsonb
    cur.execute("""INSERT INTO treino_externo (paciente_id, fonte, rotina, objetivo, nivel, periodo, nome_no_pdf, sessoes, arquivo)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (pid, fonte, dados["rotina"], dados["objetivo"], dados["nivel"], dados["periodo"], dados["nome"],
                 Jsonb(dados["sessoes"]), arquivo))
    return cur.fetchone()[0]


def atual(cur, pid):
    """rotina mais recente do paciente (e quantas existem)"""
    cur.execute("""SELECT id, rotina, objetivo, nivel, periodo, nome_no_pdf, sessoes, arquivo, importado_em,
                          count(*) OVER (), fonte FROM treino_externo WHERE paciente_id = %s ORDER BY importado_em DESC LIMIT 1""", (pid,))
    r = cur.fetchone()
    if not r:
        return None
    t = dict(zip(["id", "rotina", "objetivo", "nivel", "periodo", "nome_no_pdf", "sessoes", "arquivo", "importado_em", "n", "fonte"], r))
    t["n_exercicios"] = sum(len(s["exercicios"]) for s in t["sessoes"])
    return t
