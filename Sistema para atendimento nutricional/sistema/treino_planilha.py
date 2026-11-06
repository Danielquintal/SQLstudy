"""Treino feito em planilha (Excel .xlsx ou .csv), em qualquer um dos formatos mais comuns:
  - uma aba por treino (Treino A, Treino B...);
  - uma coluna "Treino"/"Dia"/"Sessão" dizendo de qual treino é cada exercício;
  - linhas de título ("TREINO A - Peito e tríceps") antes dos exercícios.
As colunas são achadas pelo nome (Exercício, Séries, Repetições, Carga, Intervalo, Observação...). Sem cabeçalho,
a 1ª coluna vira o exercício. Sai no mesmo formato do MFIT (sistema/mfit.py), para a mesma tela.
"""
import csv
import io
import re
import unicodedata

COLUNAS = {   # sem acento, minúsculas
    "exercicio": ("exercicio", "exercicios", "exercise", "movimento", "nome do exercicio", "nome", "atividade"),
    "sessao": ("treino", "sessao", "dia", "divisao", "ficha", "rotina", "bloco"),
    "series": ("series", "serie", "sets", "set", "n series", "no series", "qtd series"),
    "reps": ("repeticoes", "repeticao", "reps", "rep", "repet", "rep."),
    "carga": ("carga", "peso", "kg", "carga (kg)", "peso (kg)", "load"),
    "intervalo": ("intervalo", "descanso", "pausa", "rest", "intervalo (s)", "descanso (s)"),
    "obs": ("observacao", "observacoes", "obs", "obs.", "instrucoes", "instrucao", "notas", "metodo", "tecnica", "cadencia"),
    "grupo": ("grupo muscular", "musculo", "musculos", "grupamento", "grupo"),
}
TITULO = re.compile(r"^(treino|dia|sess[aã]o|ficha|divis[aã]o|semana|bloco)\b", re.I)


class ErroPlanilha(Exception):
    pass


def _n(t):
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().strip().lower()


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def _abas(nome, conteudo):
    """[(nome da aba, linhas)]"""
    n = (nome or "").lower()
    if n.endswith((".xlsx", ".xlsm")):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True, read_only=True)
        except Exception:   # noqa: BLE001
            raise ErroPlanilha("não consegui abrir a planilha (.xlsx)") from None
        return [(ws.title, [[_txt(c) for c in linha] for linha in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
    if n.endswith(".xls"):
        raise ErroPlanilha("planilha no formato antigo (.xls): abra no Excel e salve como .xlsx")
    if n.endswith((".csv", ".txt")):
        for cod in ("utf-8-sig", "latin-1"):
            try:
                texto = conteudo.decode(cod)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialeto = csv.Sniffer().sniff(texto[:4000], delimiters=",;\t")
        except csv.Error:
            dialeto = csv.excel
        return [("Treino", [[_txt(c) for c in l] for l in csv.reader(io.StringIO(texto), dialeto)])]
    raise ErroPlanilha("mande a planilha em .xlsx ou .csv")


def _cabecalho(linhas):
    """(índice da linha de cabeçalho, {campo: coluna}) ou (None, {})"""
    for i, l in enumerate(linhas[:15]):
        achou = {}
        for j, c in enumerate(l):
            c = _n(c)
            for campo, nomes in COLUNAS.items():
                if campo not in achou and (c in nomes or (campo != "grupo" and any(c.startswith(x + " ") for x in nomes))):
                    achou[campo] = j
                    break
        if "exercicio" in achou and len(achou) >= 2:
            return i, achou
    return None, {}


def _series(serie, reps):
    s, r = serie.strip(), reps.strip()
    if s and r:
        return f"{s}x{r}" if re.fullmatch(r"\d+", s) else f"{s} · {r}"
    return s or r


# ---------- treino colado como texto (Word, PDF, foto lida pelo celular...) ----------
RODAPE = re.compile(r"cref|cel\b|celular|telefone|whats|@|https?://|www\.|instagram|\(\d{2}\)\s*\d|\d{2}/\d{8,9}", re.I)
NUMERO_INICIO = re.compile(r"^(\d+\s*[xX×]\s*\d*\S*|\d+\S*)\s+(.+)$")         # "3x 5 saltos", "200 abd livres"
NUMERO_FIM = re.compile(r"^(.+?)\s+(\d.*)$")       # "Supino 4x10 60kg": nome até o primeiro número, depois séries/carga


def ler_texto(texto, nome_rotina=""):
    """texto colado -> mesmo formato do MFIT. Título de treino: linha em MAIÚSCULAS ou "Treino A", "Dia 1"..."""
    r = {"rotina": nome_rotina or None, "objetivo": None, "nivel": None, "periodo": None, "nome": None, "sessoes": []}
    atual = None
    brutas = [b for b in str(texto or "").splitlines() if b.strip() and not RODAPE.search(b)]

    def e_titulo(l):
        letras = re.sub(r"[^A-Za-zÀ-ú]", "", l)
        return bool((letras and letras.isupper() and len(l.split()) <= 7) or
                    (TITULO.match(l) and len(l.split()) <= 7 and not re.search(r"\d+\s*[xX]", l)))

    for k, bruta in enumerate(brutas):
        l = re.sub(r"[  ]+", " ", bruta).strip()
        if e_titulo(l):
            seguinte = re.sub(r"\s+", " ", brutas[k + 1]).strip() if k + 1 < len(brutas) else ""
            if not r["sessoes"] and seguinte and e_titulo(seguinte):
                r["rotina"] = nome_rotina or (l.title() if l.isupper() else l)   # cabeçalho: vale o último antes do 1º treino
                continue
            atual = {"nome": l.title() if l.isupper() else l, "exercicios": []}
            r["sessoes"].append(atual)
            continue
        if len(l.split()) > 12 and not re.search(r"\d", l):               # frase longa: observação, não exercício
            if atual is not None:
                atual.setdefault("obs", "")
                atual["obs"] = (atual["obs"] + " " + l).strip()
            continue
        if atual is None:
            atual = {"nome": "Treino", "exercicios": []}
            r["sessoes"].append(atual)
        partes = re.split(r"\t+| {2,}", bruta.strip())                     # tabela colada: colunas por tab
        partes = [p.strip() for p in partes if p.strip()]
        if len(partes) >= 2 and not re.match(r"^\d", partes[0]):
            nome, series, obs = partes[0], partes[1], " · ".join(partes[2:])
        elif m := NUMERO_INICIO.match(l):
            series, nome, obs = m.group(1), m.group(2), ""
        elif m := NUMERO_FIM.match(l):
            nome, series, obs = m.group(1), m.group(2).strip(), ""
        else:
            nome, series, obs = l, "", ""
        nome = nome.strip(" -–:;,")
        series = series.strip(" ,;")
        atual["exercicios"].append({"nome": nome, "series": [{"series": series}] if series else [], "instrucoes": obs,
                                    "grupo": None, "substituto": False})
    r["sessoes"] = [s for s in r["sessoes"] if s["exercicios"]]
    if not r["sessoes"]:
        raise ErroPlanilha("não encontrei exercícios no texto")
    return r


def ler(nome, conteudo):
    abas =[(t, [l for l in ls if any(l)]) for t, ls in _abas(nome, conteudo)]
    abas = [(t, ls) for t, ls in abas if ls]
    if not abas:
        raise ErroPlanilha("a planilha está vazia")
    r = {"rotina": re.sub(r"\.(xlsx|xlsm|csv|txt)$", "", nome or "", flags=re.I) or "Treino", "objetivo": None,
         "nivel": None, "periodo": None, "nome": None, "sessoes": []}
    varias_abas = len(abas) > 1

    def sessao(nome_s):
        for s in r["sessoes"]:
            if s["nome"] == nome_s:
                return s
        s = {"nome": nome_s, "exercicios": []}
        r["sessoes"].append(s)
        return s

    for titulo_aba, linhas in abas:
        i, col = _cabecalho(linhas)
        if i is None:
            col, i = {"exercicio": 0}, -1                    # sem cabeçalho: 1ª coluna é o exercício
            for l in linhas[:3]:                             # título da planilha numa linha só, antes de tudo
                if sum(1 for c in l if c) == 1 and not TITULO.match(next(c for c in l if c)) and r["rotina"] == "Treino":
                    r["rotina"] = next(c for c in l if c)
        else:
            for l in linhas[:i]:                             # linhas acima do cabeçalho: nome da rotina / do aluno
                cheias = [c for c in l if c]
                if len(cheias) == 1 and not TITULO.match(cheias[0]):
                    r["rotina"] = cheias[0] if r["rotina"] in ("Treino", re.sub(r"\.\w+$", "", nome or "")) else r["rotina"]
        atual = sessao(titulo_aba if varias_abas else "Treino")
        for l in linhas[i + 1:]:
            g = lambda c: l[col[c]] if c in col and col[c] < len(l) else ""
            cheias = [c for c in l if c]
            ex = g("exercicio")
            if len(cheias) == 1 and (TITULO.match(cheias[0]) or not ex or cheias[0] != ex or "sessao" not in col) and \
                    (TITULO.match(cheias[0]) or cheias[0].isupper()):
                atual = sessao(cheias[0])                     # linha de título: "TREINO A - Peito"
                continue
            if not ex or _n(ex) in COLUNAS["exercicio"]:
                continue
            if "sessao" in col and g("sessao"):
                atual = sessao(g("sessao") + (f" · {g('grupo')}" if g("grupo") and "sessao" in col and False else ""))
            serie = {"series": _series(g("series"), g("reps"))}
            if g("carga"):
                serie["carga"] = g("carga") + (" kg" if re.fullmatch(r"\d+([.,]\d+)?", g("carga")) else "")
            if g("intervalo"):
                serie["intervalo"] = g("intervalo") + ("s" if re.fullmatch(r"\d+", g("intervalo")) else "")
            if not serie["series"] and "series" not in col:     # sem colunas: "3x12" escrito em outra célula
                outro = next((c for c in l if c != ex and re.search(r"\d+\s*[xX]\s*\d+", c)), "")
                serie["series"] = outro
            serie = {k: v for k, v in serie.items() if v}
            obs = " · ".join(x for x in (g("obs"), (g("grupo") if "sessao" in col or varias_abas else "")) if x)
            atual["exercicios"].append({"nome": ex, "series": [serie] if serie else [], "instrucoes": obs,
                                        "grupo": None, "substituto": False})
    r["sessoes"] = [s for s in r["sessoes"] if s["exercicios"]]
    if not r["sessoes"]:
        raise ErroPlanilha("não encontrei exercícios na planilha (precisa de uma coluna “Exercício”, ou dos exercícios "
                           "na primeira coluna)")
    return r
