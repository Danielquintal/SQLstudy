"""Lê o PDF de plano alimentar exportado pelo App Naive e monta o plano estruturado da aba Plano alimentar
(refeições, opção principal, substituições, observações, macros por refeição, micronutrientes, lista de compras
e receitas).

O App Naive exporta em dois modelos, e a leitura usa a fonte, a cor e a posição do texto:
- cartões: horário (15pt, azul), nome da refeição na coluna da esquerda, alimento principal
  (9,8pt escuro) e quantidade (cinza), substituições na coluna da direita ("ou Nome → quantidade"), observações;
- lista: nome da refeição como título (13,5pt negrito), alimento e quantidade em colunas, e blocos
  "• Opções de substituição para X:" com as opções separadas por "- ou -"; tem lista de compras e receitas.
Os dois têm a página "Relatório de nutrientes". ler(dados) devolve o plano ou None se não reconhecer o PDF.

Uso para conferir: python scripts/plano_app_naive.py "arquivo.pdf"
"""
import ctypes, json, re, sys
from datetime import datetime

import pypdfium2
import pypdfium2.raw as pdfium

TOPO, RODAPE = 770, 75        # cabeçalho da clínica e rodapé (QR code, página) ficam fora
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
            atual = {"texto": "", "x": esq, "y": cima, "tam": tam, "negrito": peso >= 600,
                     "cinza": sum(cor) / 3 > 120 and cor[2] > 150, "verde": cor[1] > 150 and cor[0] < 100,
                     "azul": cor == (43, 76, 111)}
            trechos.append(atual)
            chave = nova
        atual["texto"] += ch
    for t in trechos:
        t["texto"] = re.sub(r"\s+", " ", t["texto"]).strip()
    return [t for t in trechos if t["texto"] and RODAPE < t["y"] < TOPO or (t["texto"] and "Prescrito em" in t["texto"])]


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
    return _ler_cartoes(paginas) or _ler_lista(paginas)


def _plano(titulo, prescrito, refeicoes, nutrientes, micros, compras=(), receitas=()):
    if not refeicoes or not all(r["itens"] for r in refeicoes):
        return None
    for r in refeicoes:
        r["nome"] = _nome_refeicao(r["nome"])
        n = nutrientes.get(r["nome"])
        if n:
            r.update(n)
    plano = {"titulo": titulo or "Plano alimentar", "prescrito": prescrito or datetime.now().strftime("%d/%m/%Y"),
             "profissional": "Daniel Quintal · Nutricionista · CRN3 54937", "refeicoes": refeicoes,
             "receitas": list(receitas), "micros": micros, "compras": list(compras)}
    total = nutrientes.get("Total das refeições")
    if total:
        plano["totais"] = {"kcal": total["kcal"], "p": total["p"], "l": total["l"], "c": total["c"]}
    return plano


def _ler_cartoes(paginas):
    """modelo em cartões: horário, coluna principal e coluna de substituições"""
    titulo, prescrito, refeicoes, nutrientes, micros = None, None, [], {}, []
    ref = item = sub = None
    for trechos in paginas:
        textos = [t["texto"] for t in trechos]
        prescrito = _prescrito(textos) or prescrito
        if any(t == "Relatório de nutrientes" for t in textos):
            nutrientes, micros = _relatorio(trechos)
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
    titulo, prescrito, refeicoes, nutrientes, micros, compras, receitas = None, None, [], {}, [], [], []
    ref, bloco = None, None   # bloco: [item, textos] das opções de substituição sendo lidas

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
        if "Relatório de nutrientes" in textos:
            fechar_bloco()
            nutrientes, micros = _relatorio(trechos)
            continue
        if "Lista de compras" in textos:
            fechar_bloco()
            compras += [_limpa(s[1:]) for s in textos if s.startswith("◯")]
            continue
        if "Receita culinária" in textos:
            fechar_bloco()
            receitas.append(_receita(trechos))
            continue
        i = 0
        while i < len(trechos):
            t, s = trechos[i], trechos[i]["texto"]
            prox = trechos[i + 1] if i + 1 < len(trechos) else None
            i += 1
            if "Prescrito em" in s:
                continue
            if t["negrito"] and t["tam"] >= 13:
                fechar_bloco()
                if prox and prox["tam"] == 10.5 and not prox["negrito"]:   # título do documento + subtítulo
                    titulo = titulo or s
                    i += 1
                    continue
                ref = {"hora": None, "nome": s, "itens": [], "obs": ""}
                refeicoes.append(ref)
            elif ref is None:
                continue
            elif t["negrito"] and s.startswith("• Opções de substituição para"):
                fechar_bloco()
                alvo = s.split("para", 1)[1].rstrip(":").strip().lower()
                item = next((x for x in reversed(ref["itens"]) if x["nome"].lower() == alvo), None)
                bloco = [item, []] if item else None
            elif bloco is not None:
                # "- ou -" (às vezes partido em "-" no fim da linha e "ou -" no começo da outra) separa as opções
                bloco[1].append("\x00" if t["negrito"] and re.fullmatch(r"-?\s*(ou)?\s*-?", s) else s)
            elif not t["negrito"] and t["x"] < 60:
                qtd = ""
                if prox and not prox["negrito"] and prox["x"] > 100 and abs(prox["y"] - t["y"]) < 3:
                    qtd = prox["texto"]
                    i += 1
                ref["itens"].append({"nome": _limpa(s), "qtd": _limpa(qtd), "subs": []})
    fechar_bloco()
    return _plano(titulo, prescrito, refeicoes, nutrientes, micros, compras, receitas)


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


def _relatorio(trechos):
    """tabela de macros por refeição e grade de micronutrientes da última página"""
    # agrupa em linhas: trechos com até 4pt de diferença de altura são da mesma linha
    linhas = []
    for t in sorted(trechos, key=lambda t: -t["y"]):
        if linhas and linhas[-1][0]["y"] - t["y"] <= 4:
            linhas[-1].append(t)
        else:
            linhas.append([t])
    macros, micros, rotulos = {}, [], None
    for ts in linhas:
        ts.sort(key=lambda t: t["x"])
        textos = [t["texto"] for t in ts]
        if len(ts) == 5 and re.search(r"Kcal$", textos[-1]):
            nome = _nome_refeicao(textos[0])
            macros[nome] = {"p": _num(textos[1]), "l": _num(textos[2]), "c": _num(textos[3]),
                            "kcal": int(round(_num(textos[4])))}
        elif all(t["negrito"] for t in ts) and textos[0] not in ("Refeição", "Total de vitaminas, minerais e tipos de gordura"):
            rotulos = textos
        elif rotulos and len(textos) == len(rotulos) and all(re.match(r"-?\d", x) for x in textos):
            micros += [[k, v] for k, v in zip(rotulos, textos)]
            rotulos = None
    return macros, micros


if __name__ == "__main__":
    plano = ler(open(sys.argv[1], "rb").read())
    print(json.dumps(plano, ensure_ascii=False, indent=1) if plano else "Não é um PDF de plano do App Naive.")
