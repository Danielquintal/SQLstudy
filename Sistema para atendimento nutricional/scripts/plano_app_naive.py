"""Lê o PDF de plano alimentar exportado pelo App Naive e monta o plano estruturado da aba Plano alimentar
(refeições, opção principal, substituições, observações, macros por refeição, micronutrientes, lista de compras
e receitas).

O App Naive exporta em dois modelos, e a leitura usa a fonte, a cor e a posição do texto:
- cartões: horário (15pt, azul), nome da refeição na coluna da esquerda, alimento principal
  (9,8pt escuro) e quantidade (cinza), substituições na coluna da direita ("ou Nome → quantidade"), observações;
- lista: nome da refeição como título (13,5pt negrito, às vezes com o horário: "07:30 - Café da manhã") e,
  conforme a exportação, alimento e quantidade em colunas ou "• Alimento - quantidade" com as trocas logo abaixo
  ("Ou Outro - quantidade;"); blocos "• Opções de substituição para X:" com as opções separadas por "- ou -";
  pode ter lista de compras, receitas e refeição sem alimentos (ex.: refeição livre). A exportação completa traz as
  refeições numa tabela "Opção principal / Opção de substituição" (7,5pt), a meta de água e a "Lista de substituição"
  com os grupos de alimentos e suas porções (várias páginas).
- tabela (2026): refeição como título (12pt negrito) com o horário à direita, colunas "OPÇÃO PRINCIPAL" (alimento e
  quantidade em cinza) e "OPÇÃO DE SUBSTITUIÇÃO" ("ou nome → quantidade" e "Ou escolha N porções do grupo (X) (Nome)"),
  observações que podem trazer uma receita, meta de água, lista de substituição com a porção na mesma linha do
  alimento, relatório de nutrientes e lista de compras.
- lista compacta (2026): refeição como título centralizado ("09:00 - Pré-treino [1]") e cada alimento numa linha
  "- Nome - quantidade - ou - Outro - quantidade" (nomes em negrito, a linha pode quebrar); refeição sem alimentos
  com texto livre (vira observação), meta de água, relatório, lista de compras e receitas ("Receita culinária").
Todos têm a página "Relatório de nutrientes". ler(dados) devolve o plano ou None se não reconhecer o PDF.

Uso para conferir: python scripts/plano_app_naive.py "arquivo.pdf"
"""
import ctypes, json, re, sys, unicodedata
from datetime import datetime

import pypdfium2
import pypdfium2.raw as pdfium

TOPO, RODAPE = 770, 30        # cabeçalho da clínica fica fora; o rodapé sai pelo texto (RODAPE_TEXTO)
RODAPE_TEXTO = re.compile(r"^(Acesse o|app|e veja o|conteúdo completo|da sua consulta\.?)$")
COLUNA_SUBS = 345              # x a partir do qual começa "Opção de substituição"
COLUNA_REFEICAO = 120          # x até onde vai a coluna do horário e do nome da refeição


def _trechos(pagina):
    """texto da página em trechos de mesmo estilo e mesma linha: dict(texto, x, y, cinza, tam, negrito, verde)"""
    tp = pagina.get_textpage()
    trechos, atual, chave = [], None, None
    for i in range(tp.count_chars()):
        ch = tp.get_text_range(i, 1)
        if ch in "\r\n":
            chave = None
            continue
        r, g, b, a = (ctypes.c_uint() for _ in range(4))
        pdfium.FPDFText_GetFillColor(tp.raw, i, r, g, b, a)
        cor = (r.value, g.value, b.value)
        tam = round(pdfium.FPDFText_GetFontSize(tp.raw, i), 1)
        peso = pdfium.FPDFText_GetFontWeight(tp.raw, i)
        nova = (cor, tam, peso)
        if nova != chave or atual is None:
            esq, baixo, dir_, cima = tp.get_charbox(i)
            atual = {"texto": "", "x": esq, "y": cima, "tam": tam, "negrito": peso >= 600, "cor": cor,
                     "cinza": sum(cor) / 3 > 120 and cor[2] > 150, "verde": cor[1] > 150 and cor[0] < 100,
                     "azul": cor == (43, 76, 111)}
            trechos.append(atual)
            chave = nova
        atual["texto"] += ch
    for t in trechos:
        t["texto"] = re.sub(r"\s+", " ", t["texto"]).strip()
    return [t for t in trechos if t["texto"] and ("Prescrito em" in t["texto"] or (
        RODAPE < t["y"] < TOPO and not (t["y"] < 75 and RODAPE_TEXTO.match(t["texto"]))))]


def _num(s):
    m = re.search(r"-?\d+(?:[.,]\d+)?", s or "")
    return float(m.group().replace(",", ".")) if m else None


def _nome_refeicao(nome):
    m = re.match(r"(.*?)\s*\[(\d+)\](.*)$", nome)
    return f"{m.group(1)} · opção {m.group(2)}{m.group(3)}" if m else nome


def _prescrito(textos):
    for t in textos:
        m = re.search(r"Prescrito em:\s*(\d{2}/\d{2}/\d{4})", t)
        if m:
            return m.group(1)
    return None


def ler(dados):
    try:
        pdf = pypdfium2.PdfDocument(dados)
    except pypdfium2.PdfiumError:
        return None
    paginas = [_trechos(pg) for pg in pdf]
    # o modelo em cartões também tem "OPÇÃO PRINCIPAL", mas o horário dele é azul e grande
    cartoes = any(t["azul"] and re.fullmatch(r"\d{1,2}:\d{2}", t["texto"]) for pg in paginas for t in pg)
    if not cartoes and any(t["texto"] == "OPÇÃO PRINCIPAL" for pg in paginas for t in pg):
        return _ler_tabela(paginas)
    if any(_marca_item(pg, i) for pg in paginas for i in range(len(pg))):
        return _ler_compacta(paginas)
    return _ler_cartoes(paginas) or _ler_lista(paginas)


def _plano(titulo, prescrito, refeicoes, nutrientes, micros, compras=(), receitas=(), agua=None, grupos=()):
    if not refeicoes or not any(r["itens"] for r in refeicoes):
        return None
    usados = set()
    for r in refeicoes:
        r["nome"] = _nome_refeicao(r["nome"])
        i = next((i for i, (nome, _) in enumerate(nutrientes) if nome == r["nome"] and i not in usados), None)
        if i is not None:
            usados.add(i)
            r.update(nutrientes[i][1])
    plano = {"titulo": titulo or "Plano alimentar", "prescrito": prescrito or datetime.now().strftime("%d/%m/%Y"),
             "profissional": "Daniel Quintal · Nutricionista · CRN3 54937", "refeicoes": refeicoes,
             "receitas": list(receitas), "micros": micros, "compras": list(compras)}
    if agua:
        plano["agua"] = agua
    if grupos:
        plano["grupos"] = [g for g in grupos if g["itens"]]
    total = next((v for nome, v in nutrientes if nome == "Total das refeições"), None)
    if total:
        plano["totais"] = {"kcal": total["kcal"], "p": total["p"], "l": total["l"], "c": total["c"]}
    return plano


def _ler_cartoes(paginas):
    """modelo em cartões: horário, coluna principal e coluna de substituições"""
    titulo, prescrito, refeicoes, nutrientes, micros = None, None, [], [], []
    ref = item = sub = rotulos_pend = None
    for trechos in paginas:
        textos = [t["texto"] for t in trechos]
        prescrito = _prescrito(textos) or prescrito
        if any(t == "Relatório de nutrientes" for t in textos):
            nutrientes, micros, rotulos_pend = _relatorio(trechos)
            continue
        if rotulos_pend:
            _, mais, rotulos_pend = _relatorio(trechos, rotulos_pend)
            micros += mais
            if mais:
                continue
        modo, ultimo = None, None
        for t in trechos:
            s = t["texto"]
            if "Prescrito em" in s or t["verde"] or re.fullmatch(r"\d+ REFEIÇÕES", s):
                continue
            if t["tam"] >= 16:
                titulo = s
            elif t["azul"] and re.fullmatch(r"\d{1,2}:\d{2}", s):
                ref = {"hora": s, "nome": "", "itens": [], "obs": ""}
                refeicoes.append(ref)
                modo = "refeicao"
            elif t["negrito"] and t["x"] < COLUNA_REFEICAO and ref is not None and modo == "refeicao":
                ref["nome"] = (ref["nome"] + " " + s).strip()
            elif ref is None:
                continue
            elif s == "Observações:":
                modo = "obs"
            elif modo == "obs" and t["tam"] >= 10.5 and not t["negrito"]:
                ref["obs"] = (ref["obs"] + " " + s).strip()
            elif t["x"] < COLUNA_SUBS and t["tam"] >= 9.5:
                # coluna da opção principal: nome (escuro) e quantidade (cinza), podendo quebrar linha
                if t["cinza"]:
                    item["qtd"] = (item["qtd"] + " " + s).strip()
                    ultimo = "qtd"
                elif ultimo == "nome" and item is not None and not item["qtd"]:
                    item["nome"] += " " + s
                else:
                    item = {"nome": s, "qtd": "", "subs": []}
                    ref["itens"].append(item)
                    ultimo = "nome"
                modo = "itens"
            elif t["x"] >= COLUNA_SUBS - 5 and item is not None:
                # coluna das substituições: "ou" + nome (negrito) + "→ quantidade" (cinza)
                if s == "ou":
                    ultimo = "ou"
                elif t["cinza"]:
                    sub["qtd"] = (sub["qtd"] + " " + s.lstrip("→ ").strip()).strip() if sub else ""
                    ultimo = "subqtd"
                elif t["negrito"]:
                    if ultimo == "subnome" and sub is not None and not sub["qtd"]:
                        sub["nome"] += " " + s
                    else:
                        sub = {"nome": s, "qtd": ""}
                        item["subs"].append(sub)
                    ultimo = "subnome"
    return _plano(titulo, prescrito, refeicoes, nutrientes, micros)


def _cinza(t):
    """cinza neutro (140, 140, 140) das quantidades no modelo em tabela"""
    return all(110 <= c <= 190 for c in t["cor"]) and max(t["cor"]) - min(t["cor"]) < 20


def _ler_tabela(paginas):
    """modelo em tabela (2026): título da refeição com horário à direita e colunas principal / substituição"""
    titulo, prescrito, refeicoes, nutrientes, micros, compras, receitas = None, None, [], [], [], [], []
    grupos, agua, rotulos_pend = [], [], None
    ref = item = sub = escolha = rec = None
    modo = ultimo = None

    def fechar_escolha():
        nonlocal escolha
        if escolha and item is not None:
            op = _grupo_escolha(escolha) or {"nome": _limpa(escolha), "qtd": ""}
            if op not in item["subs"]:
                item["subs"].append(op)
        escolha = None

    for trechos in paginas:
        textos = [t["texto"] for t in trechos]
        prescrito = _prescrito(textos) or prescrito
        if "Relatório de nutrientes" in textos:
            fechar_escolha()
            nutrientes, micros, rotulos_pend = _relatorio(trechos)
            modo = None
            continue
        if rotulos_pend:
            _, mais, rotulos_pend = _relatorio(trechos, rotulos_pend)
            micros += mais
            if mais:
                continue
        if "Lista de compras" in textos:
            fechar_escolha()
            # fica de fora o título e o subtítulo da página (o nome do plano)
            topo = min(t["y"] for t in trechos if t["texto"] == "Lista de compras")
            compras += _compras([t for t in trechos if t["y"] < topo - 25], tam_max=11.5)
            modo = None
            continue
        if "Lista de substituição" in textos:
            fechar_escolha()
            modo = "grupos"
        if modo == "grupos":
            _grupos_linha(trechos, grupos)
            continue
        horas = [t for t in trechos if t["negrito"] and t["x"] > 400 and re.fullmatch(r"\d{1,2}:\d{2}", t["texto"])]
        for t in trechos:
            s = t["texto"]
            if "Prescrito em" in s or t["verde"] or t in horas:
                continue
            if t["negrito"] and t["tam"] >= 16 and modo not in ("obs", "ingredientes", "preparo"):
                titulo = titulo or s   # (dentro das observações, letra grande é o nome de uma receita)
            elif t["negrito"] and 11.5 <= t["tam"] < 16 and t["x"] < 300:
                fechar_escolha()
                if s == "Meta de ingestão hídrica":
                    modo = "agua"
                    continue
                hora = next((h["texto"] for h in horas if abs(h["y"] - t["y"]) < 5), None)
                ref = {"hora": hora, "nome": s, "itens": [], "obs": ""}
                refeicoes.append(ref)
                item = sub = rec = None
                modo = "itens"
            elif ref is None:
                continue
            elif modo == "agua":
                agua.append(s)
            elif s == "Observações:":
                fechar_escolha()
                modo = "obs"
            elif modo in ("obs", "ingredientes", "preparo"):
                if t["negrito"] and t["tam"] >= 16:
                    rec = {"nome": s[:1] + s[1:].lower() if s.isupper() else s, "ingredientes": [], "preparo": []}
                    receitas.append(rec)
                    ref["receitas"] = True
                elif s == "Ingredientes:" and rec is not None:
                    modo = "ingredientes"
                elif s in ("Modo de preparo:", "Forma de preparo:") and rec is not None:
                    modo = "preparo"
                elif modo == "ingredientes":
                    rec["ingredientes"].append(_limpa(s))
                elif modo == "preparo":
                    if re.match(r"\d+\s*[-.)]", s) or not rec["preparo"]:
                        rec["preparo"].append(_limpa(re.sub(r"^\d+\s*[-.)]\s*", "", s)))
                    else:
                        rec["preparo"][-1] += " " + _limpa(s)
                else:
                    ref["obs"] = (ref["obs"] + " " + s).strip()
            elif t["x"] < 300:
                # opção principal: nome (escuro) e quantidade (cinza), que pode quebrar linha
                fechar_escolha()
                if _cinza(t) and item is not None:
                    item["qtd"] = (item["qtd"] + " " + s).strip()
                    ultimo = "qtd"
                elif ultimo == "nome" and item is not None and not item["qtd"]:
                    item["nome"] += " " + s
                else:
                    item = {"nome": _limpa(s), "qtd": "", "subs": []}
                    ref["itens"].append(item)
                    ultimo = "nome"
                sub = None
            elif item is not None:
                # substituições: "ou" + nome (negrito) + "→ quantidade" (cinza); "Ou escolha ... do grupo (X)"
                if s.lower().startswith("ou escolha"):
                    fechar_escolha()
                    escolha = s
                elif escolha is not None and _cinza(t) and t["tam"] < 8.8:
                    escolha += " " + s
                elif s == "ou":
                    fechar_escolha()
                    sub = None
                elif t["negrito"]:
                    fechar_escolha()
                    if sub is not None and not sub["qtd"]:
                        sub["nome"] += " " + s
                    else:
                        sub = {"nome": _limpa(s[:1].upper() + s[1:]), "qtd": ""}
                        item["subs"].append(sub)
                elif sub is not None:
                    sub["qtd"] = _limpa((sub["qtd"] + " " + s.lstrip("→ ").strip()).strip())
    fechar_escolha()
    return _plano(titulo, prescrito, refeicoes, nutrientes, micros, compras, receitas, _texto_agua(agua), grupos)


def _marca_item(trechos, i):
    """o "-" sozinho na margem esquerda, seguido do nome em negrito, que abre cada alimento na lista compacta"""
    t = trechos[i]
    return (t["texto"] == "-" and not t["negrito"] and t["x"] < 50 and i + 1 < len(trechos)
            and trechos[i + 1]["negrito"] and trechos[i + 1]["tam"] == t["tam"])


def _item_compacto(partes):
    """[(negrito, texto), ...] de uma linha "- Nome - qtd - ou - Outro - qtd" -> {nome, qtd, subs}"""
    texto, antes = "", None
    for negrito, t in partes:
        if negrito:
            texto += (" " + t if antes else " \x01" + t)   # nome que quebrou linha continua no mesmo negrito
        else:
            texto += ("\x02 " if antes else " ") + t
        antes = negrito
    if antes:
        texto += "\x02"
    opcoes = []
    for op in re.split(r"\s*-\s*ou\s*-\s*", texto.strip()):
        m = re.match(r"\s*\x01(.*?)\x02\s*(?:-\s*)?(.*)$", op, re.S)
        if m:
            opcoes.append({"nome": _limpa(m.group(1)), "qtd": _limpa(m.group(2).rstrip(" -"))})
        elif op.strip(" -"):
            opcoes.append(_alimento(op.replace("\x01", "").replace("\x02", "")))
    if not opcoes:
        return None
    item = opcoes[0]
    item["subs"] = opcoes[1:]
    return item


def _ler_compacta(paginas):
    """modelo em lista compacta: título da refeição e uma linha por alimento, com as trocas na mesma linha"""
    titulo, prescrito, refeicoes, nutrientes, micros, compras, receitas = None, None, [], [], [], [], []
    agua, rotulos_pend = [], None
    ref, partes, lendo_agua = None, None, False

    def fechar_item():
        nonlocal partes
        if partes and ref is not None:
            item = _item_compacto(partes)
            if item:
                ref["itens"].append(item)
        partes = None

    for trechos in paginas:
        textos = [t["texto"] for t in trechos]
        prescrito = _prescrito(textos) or prescrito
        if "Relatório de nutrientes" in textos:
            fechar_item()
            nutrientes, micros, rotulos_pend = _relatorio(trechos)
            continue
        if rotulos_pend:
            _, mais, rotulos_pend = _relatorio(trechos, rotulos_pend)
            micros += mais
            if mais:
                continue
        if "Lista de compras" in textos:
            fechar_item()
            compras += _compras(trechos)
            continue
        if "Receita culinária" in textos:
            fechar_item()
            receitas.append(_receita(trechos))
            continue
        for i, t in enumerate(trechos):
            s, prox = t["texto"], trechos[i + 1] if i + 1 < len(trechos) else None
            if "Prescrito em" in s:
                continue
            if t["negrito"] and t["tam"] >= 13:
                fechar_item()
                lendo_agua = False
                if titulo is None and prox and prox["tam"] == 10.5 and not prox["negrito"]:
                    titulo = s          # título do documento (o subtítulo logo abaixo fica de fora)
                    continue
                m = re.match(r"(\d{1,2}:\d{2})\s*-\s*(.+)", s)
                ref = {"hora": m.group(1) if m else None, "nome": m.group(2) if m else s, "itens": [], "obs": ""}
                refeicoes.append(ref)
            elif titulo is not None and ref is None and t["tam"] == 10.5:
                continue
            elif s == "Meta de ingestão hídrica":
                fechar_item()
                lendo_agua = True
            elif lendo_agua:
                agua.append(s)
            elif ref is None:
                continue
            elif _marca_item(trechos, i) and partes and re.search(r"-\s*ou$", partes[-1][1]):
                partes.append((False, "-"))   # "- ou" no fim da linha + "-" na outra: a troca continua (não é outro alimento)
            elif _marca_item(trechos, i):
                fechar_item()
                partes = []
            elif partes is not None:
                partes.append((t["negrito"], s))
            else:
                # refeição sem alimentos com texto (ex.: refeição livre): vira observação. A linha que só quebrou
                # continua a frase; tópico ("* ..."), título em negrito, "ou" e fim de frase começam outra linha
                ant = ref.pop("_ant", None)
                novo = (ant is None or t["negrito"] or ant[0] or s.startswith(("*", "•", "-")) or s == "ou"
                        or ant[1] == "ou" or re.search(r"[.:!?;)]$", ant[1]) or re.search(r"\s-\s[\d½¼¾]", s))
                ref["obs"] = (ref["obs"] + ("\n" if novo else " ") + s).strip()
                ref["_ant"] = (t["negrito"], s)
    fechar_item()
    for r in refeicoes:
        r.pop("_ant", None)
    # refeição só com o título (sem alimentos nem texto) não aparece
    refeicoes = [r for r in refeicoes if r["itens"] or r["obs"]]
    return _plano(titulo, prescrito, refeicoes, nutrientes, micros, compras, receitas, _texto_agua(agua))


def _grupos_linha(trechos, grupos):
    """lista de substituição do modelo em tabela: "Grupo N: nome", e cada alimento com a porção (cinza) na mesma linha"""
    linhas = sorted((t for t in trechos if "Prescrito em" not in t["texto"]), key=lambda t: (-round(t["y"]), t["x"]))
    for t in linhas:
        s = t["texto"]
        if t["negrito"] and re.match(r"Grupo \d+", s):
            grupos.append({"nome": s, "itens": []})
        elif grupos and not t["negrito"] and not _cinza(t) and t["x"] < 300 and t["tam"] < 13:
            qtd = next((o["texto"] for o in linhas if _cinza(o) and o["x"] >= 300 and abs(o["y"] - t["y"]) < 4), "")
            grupos[-1]["itens"].append({"nome": _limpa(s), "qtd": _limpa(qtd)})


def _limpa(s):
    s = re.sub(r"\s+", " ", s.replace("\ufffe", "-")).strip()
    return "À vontade" if re.fullmatch(r"1 A vontade \(0g\)", s) else s


def _alimento(texto):
    """"Nome - quantidade" -> {nome, qtd}; o nome pode ter " - " (ex.: "Filé Mignon Suíno - Swift - 150g")"""
    texto = _limpa(texto)
    nome, _, qtd = texto.rpartition(" - ")
    return {"nome": nome, "qtd": qtd} if nome else {"nome": texto, "qtd": ""}


def _ler_lista(paginas):
    """modelo em lista: título da refeição, alimentos em duas colunas e blocos de substituição"""
    titulo, prescrito, refeicoes, nutrientes, micros, compras, receitas = None, None, [], [], [], [], []
    rotulos_pend = None       # nomes de micronutrientes cujos valores ficaram na página seguinte
    ref, bloco = None, None   # bloco: [item, textos] das opções de substituição sendo lidas
    ultimo = None             # último "• alimento", para juntar as trocas "Ou ..." e as linhas quebradas
    tabela = []               # linhas da tabela "Opção principal / Opção de substituição" da refeição atual
    agua, grupos, em_grupos, lendo_agua = [], [], False, False

    def fechar_tabela():
        nonlocal tabela
        if tabela and ref is not None:
            _tabela_refeicao(ref, tabela)
        tabela = []

    def fechar_bloco():
        nonlocal bloco
        if bloco:
            item, partes = bloco
            for op in " ".join(partes).split("\x00"):
                op = _alimento(op) if op.strip() else None
                if op and op not in item["subs"]:   # o App Naive às vezes repete a mesma opção
                    item["subs"].append(op)
        bloco = None

    for trechos in paginas:
        textos = [t["texto"] for t in trechos]
        prescrito = _prescrito(textos) or prescrito
        fechar_tabela()
        if "Lista de substituição" in textos:
            em_grupos = True
        if any(x in textos for x in ("Relatório de nutrientes", "Lista de compras", "Receita culinária")):
            em_grupos = False
        if em_grupos:
            fechar_bloco()
            _grupos(trechos, grupos)
            continue
        if "Relatório de nutrientes" in textos:
            fechar_bloco()
            nutrientes, micros, rotulos_pend = _relatorio(trechos)
            continue
        if rotulos_pend:
            _, mais, rotulos_pend = _relatorio(trechos, rotulos_pend)
            micros += mais
            if mais:
                continue
        if "Lista de compras" in textos:
            fechar_bloco()
            compras += _compras(trechos)
            continue
        if "Receita culinária" in textos:
            fechar_bloco()
            receitas.append(_receita(trechos))
            continue
        i, ult_titulo = 0, None
        while i < len(trechos):
            t, s = trechos[i], trechos[i]["texto"]
            prox = trechos[i + 1] if i + 1 < len(trechos) else None
            i += 1
            if "Prescrito em" in s:
                continue
            if 7 <= t["tam"] < 8.5 and not t["negrito"] and ref is not None:
                tabela.append(t)          # linha da tabela de opções: processada junto, pela posição
                continue
            if t["tam"] < 7 and s in ("Opção principal", "Opção de substituição"):
                continue
            fechar_tabela()
            if s == "Meta de ingestão hídrica":
                lendo_agua = True
                continue
            if lendo_agua and not (t["negrito"] and t["tam"] >= 13):
                agua.append(s)
                continue
            lendo_agua = False
            if t["negrito"] and t["tam"] >= 13:
                fechar_bloco()
                if prox and prox["tam"] == 10.5 and not prox["negrito"]:   # título do documento + subtítulo
                    titulo = titulo or s
                    i += 1
                    continue
                if ref is not None and not ref["itens"] and ult_titulo is not None and 0 < ult_titulo - t["y"] < 20:
                    ref["nome"] += " " + s      # o título continuou na linha de baixo
                    ult_titulo = t["y"]
                    continue
                m = re.match(r"(\d{1,2}:\d{2})\s*-\s*(.+)", s)
                ref = {"hora": m.group(1) if m else None, "nome": m.group(2) if m else s, "itens": [], "obs": ""}
                refeicoes.append(ref)
                ultimo = None
                ult_titulo = t["y"]
            elif ref is None:
                continue
            elif t["negrito"] and s.startswith("• Opções de substituição para"):
                fechar_bloco()
                alvo = s.split("para", 1)[1].rstrip(":").strip().lower()
                item = next((x for x in reversed(ref["itens"]) if x["nome"].lower() == alvo), None)
                bloco = [item, []] if item else None
            elif t["negrito"] and s.startswith("•"):
                fechar_bloco()
                ultimo = {"_txt": s.lstrip("• ").strip(), "subs": []}
                ultimo.update(_alimento(ultimo["_txt"]))
                ref["itens"].append(ultimo)
            elif not t["negrito"] and s.startswith("Ou ") and ultimo is not None and bloco is None:
                ultimo["subs"].append(_alimento(s[3:].rstrip(";")))
            elif t["negrito"] and ultimo is not None and bloco is None and not ultimo["subs"]:
                ultimo["_txt"] += " " + s      # nome ou quantidade que quebrou linha, ex.: "(240ml)"
                ultimo.update(_alimento(ultimo["_txt"]))
            elif bloco is not None:
                # "- ou -" (às vezes partido em "-" no fim da linha e "ou -" no começo da outra) separa as opções
                bloco[1].append("\x00" if t["negrito"] and re.fullmatch(r"-?\s*(ou)?\s*-?", s) else s)
            elif not t["negrito"] and t["x"] < 60:
                qtd = ""
                if prox and not prox["negrito"] and prox["x"] > 100 and abs(prox["y"] - t["y"]) < 3:
                    qtd = prox["texto"]
                    i += 1
                ref["itens"].append({"nome": _limpa(s), "qtd": _limpa(qtd), "subs": []})
    fechar_tabela()
    fechar_bloco()
    for r in refeicoes:
        for item in r["itens"]:
            item.pop("_txt", None)
    return _plano(titulo, prescrito, refeicoes, nutrientes, micros, compras, receitas, _texto_agua(agua), grupos)


def _texto_agua(partes):
    """meta de água: "Aproximadamente 8 copos de 300ml" + "2359 ml durante o dia." vira uma frase só"""
    if not partes:
        return None
    total = next((x for x in partes if re.search(r"\d\s*ml durante", x)), None)
    resto = [x for x in partes if x != total]
    if total and resto:
        return f"{total.rstrip('.')} ({resto[0][0].lower() + resto[0][1:]})"
    return " ".join(partes)


def _grupo_escolha(texto):
    """"Ou escolha 1.5 porções do grupo 4 da lista de substituição." -> troca que aponta para o grupo"""
    m = re.search(r"escolha\s+([\d.,]+)\s+(porç\w*)\s+do\s+grupo\s+\(?(\d+)\)?(?:\s*\(([^)]+)\))?", texto, re.I)
    if not m:
        return None
    nome = f"{m.group(1).replace('.', ',')} {m.group(2)} do Grupo {m.group(3)}" + (f" ({m.group(4)})" if m.group(4) else "")
    return {"nome": nome, "qtd": "lista de substituição", "grupo": int(m.group(3))}


def _tabela_refeicao(ref, linhas):
    """tabela "Opção principal / Opção de substituição": a principal fica na altura do meio das suas trocas, e cada
    bloco de trocas termina em "Ou escolha N porções do grupo X"""
    def juntar(col):
        # uma linha a menos de 13pt da anterior, na mesma coluna, é continuação (o texto quebrou)
        saida = []
        for t in sorted(col, key=lambda t: -t["y"]):
            if saida and saida[-1]["y_fim"] - t["y"] < 13:
                saida[-1]["texto"] += " " + t["texto"]
                saida[-1]["y_fim"] = t["y"]
            else:
                saida.append({"texto": t["texto"], "y": t["y"], "y_fim": t["y"]})
        return saida
    principais = juntar([t for t in linhas if t["x"] < 200])
    trocas = juntar([t for t in linhas if t["x"] >= 200])
    itens = []
    for pr in principais:
        item = _alimento(pr["texto"])
        item["subs"], item["y"] = [], pr["y"]
        itens.append(item)
        ref["itens"].append(item)
    if not itens:
        return
    blocos, atual = [], []
    for tr in trocas:
        atual.append(tr)
        if tr["texto"].lower().startswith("ou escolha"):
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)
    for bloco in blocos:
        meio = sum((b["y"] + b["y_fim"]) / 2 for b in bloco) / len(bloco)
        dono = min(itens, key=lambda i: abs(i["y"] - meio))
        for b in bloco:
            op = _grupo_escolha(b["texto"]) or _alimento(b["texto"])
            if op not in dono["subs"]:
                dono["subs"].append(op)
    for item in itens:
        item.pop("y", None)


def _grupos(trechos, grupos):
    """páginas da lista de substituição: "Grupo N: nome" e, em duas colunas, nome do alimento (negrito) com a porção
    logo abaixo; um grupo pode continuar na página seguinte"""
    linhas = sorted((t for t in trechos if "Prescrito em" not in t["texto"]), key=lambda t: (-round(t["y"]), t["x"]))
    pendentes = {}   # coluna -> alimento esperando a porção
    for t in linhas:
        s = t["texto"]
        if t["negrito"] and t["tam"] >= 10 and re.match(r"Grupo \d+", s):
            grupos.append({"nome": s, "itens": []})
            pendentes = {}
            continue
        if t["tam"] >= 10 or not grupos:   # títulos da página
            continue
        col = 0 if t["x"] < 200 else 1
        if t["negrito"]:
            ant = pendentes.get(col)
            if ant and not ant["qtd"] and ant["_y"] - t["y"] < 30:
                ant["nome"] += " " + _limpa(s)        # nome que quebrou linha (ainda sem a porção embaixo)
            else:
                pendentes[col] = {"nome": _limpa(s), "qtd": "", "_y": t["y"]}
                grupos[-1]["itens"].append(pendentes[col])
            pendentes[col]["_y"] = t["y"]
        elif pendentes.get(col) is not None:
            item = pendentes[col]
            item["qtd"] = (item["qtd"] + " " + _limpa(s)).strip()
    for g in grupos:
        for item in g["itens"]:
            item.pop("_y", None)


def _compras(trechos, tam_max=10):
    """itens da lista de compras; em colunas, um nome que quebra linha continua logo abaixo, na mesma coluna"""
    itens = [t for t in trechos if not t["negrito"] and t["tam"] < tam_max and "Prescrito em" not in t["texto"]]
    itens.sort(key=lambda t: (round(t["x"] / 40), -t["y"]))
    saida, anterior = [], None
    for t in itens:
        texto = _limpa(t["texto"].lstrip("◯").strip())
        if (anterior and round(anterior["x"] / 40) == round(t["x"] / 40) and 0 < anterior["y"] - t["y"] < 14
                and not t["texto"].startswith("◯")):
            saida[-1] += " " + texto
        else:
            saida.append(texto)
        anterior = t
    return sorted(saida, key=lambda x: unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower())


def _receita(trechos):
    nome, ingredientes, preparo, parte = [], [], [], "titulo"
    for t in trechos:
        s = t["texto"]
        if "Prescrito em" in s or s == "Receita culinária":
            parte = "info" if s == "Receita culinária" else parte
            continue
        if parte == "titulo" and t["negrito"] and t["tam"] >= 13:
            nome.append(s)
        elif s == "Ingredientes:":
            parte = "ingredientes"
        elif s == "Forma de preparo:":
            parte = "preparo"
        elif parte == "ingredientes":
            ingredientes.append(_limpa(s))
        elif parte == "preparo":
            if re.match(r"\d+\.", s) or not preparo:
                preparo.append(_limpa(re.sub(r"^\d+\.\s*", "", s)))
            else:
                preparo[-1] += " " + _limpa(s)
    return {"nome": " ".join(nome), "ingredientes": ingredientes, "preparo": preparo}


def _relatorio(trechos, rotulos=None):
    """tabela de macros por refeição e grade de micronutrientes da última página"""
    # agrupa em linhas: trechos com até 4pt de diferença de altura são da mesma linha
    linhas = []
    for t in sorted(trechos, key=lambda t: -t["y"]):
        if linhas and linhas[-1][0]["y"] - t["y"] <= 4:
            linhas[-1].append(t)
        else:
            linhas.append([t])
    macros, micros = [], []
    for n, ts in enumerate(linhas):
        ts.sort(key=lambda t: t["x"])
        textos = [t["texto"] for t in ts]
        if len(ts) == 4 and re.search(r"Kcal$", textos[-1]) and ts[0]["x"] > 250:
            vizinhas = [l for l in linhas[max(0, n - 1):n + 2] if len(l) == 1 and l[0]["x"] < 250
                        and abs(l[0]["y"] - ts[0]["y"]) < 9]
            if vizinhas:
                nome = " ".join(l[0]["texto"] for l in sorted(vizinhas, key=lambda l: -l[0]["y"]))
                ts, textos = [None] + ts, [nome] + textos
        if len(ts) == 5 and re.search(r"Kcal$", textos[-1]):
            macros.append((_nome_refeicao(textos[0]), {"p": _num(textos[1]), "l": _num(textos[2]),
                                                      "c": _num(textos[3]), "kcal": int(round(_num(textos[4])))}))
        elif all(t["negrito"] for t in ts) and textos[0] not in ("Refeição", "Total de vitaminas, minerais e tipos de gordura"):
            rotulos = textos
        elif rotulos and len(textos) == len(rotulos) and all(re.match(r"-?\d", x) for x in textos):
            micros += [[k, v] for k, v in zip(rotulos, textos)]
            rotulos = None
    return macros, micros, rotulos


if __name__ == "__main__":
    plano = ler(open(sys.argv[1], "rb").read())
    print(json.dumps(plano, ensure_ascii=False, indent=1) if plano else "Não é um PDF de plano do App Naive.")
