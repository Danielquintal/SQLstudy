"""Aba "Resumo" da ficha do paciente: o painel com os indicadores da última avaliação, a variação e os gráficos.

Os gráficos saem prontos em SVG (coordenadas calculadas aqui), sem biblioteca de gráficos na tela do sistema.
"""

# (coluna, rótulo, unidade, o que é melhorar: "desce", "sobe" ou None quando depende do objetivo)
INDICADORES = [
    ("peso_kg", "Peso", "kg", None),
    ("gordura_pct", "% de gordura", "%", "desce"),
    ("massa_muscular_kg", "Massa muscular", "kg", "sobe"),
    ("massa_gordura_kg", "Massa de gordura", "kg", "desce"),
    ("circ_cintura", "Cintura", "cm", "desce"),
    ("somatorio_dobras_mm", "Soma das dobras", "mm", "desce"),
    ("imc", "IMC", "", None),
    ("mlg_kg", "Massa livre de gordura", "kg", "sobe"),
]

# linhas do gráfico de composição corporal (todas em kg, mesma escala)
COMPOSICAO = [("peso_kg", "Peso", "c1"), ("mlg_kg", "Massa livre de gordura", "c2"),
              ("massa_muscular_kg", "Massa muscular", "c6"), ("massa_gordura_kg", "Massa de gordura", "c3")]


def _f(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _tom(dif, melhor):
    if dif is None or melhor is None or abs(dif) < 1e-9:
        return "flat"
    return "good" if (dif < 0) == (melhor == "desce") else "bad"


def _mini(vals, w=120, h=34):
    """pontos da linha pequena (sparkline) de uma série; None nos buracos"""
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    amp = (hi - lo) or 1
    n = len(vals) - 1 or 1
    return " ".join(f"{i / n * w:.1f},{h - 3 - (v - lo) / amp * (h - 6):.1f}" for i, v in pts)


def indicadores(avs):
    """avs em ordem de data (a mais antiga primeiro)"""
    if not avs:
        return []
    saida = []
    for col, rot, un, melhor in INDICADORES:
        serie = [_f(a.get(col)) for a in avs]
        ult = next((v for v in reversed(serie) if v is not None), None)
        if ult is None:
            continue
        validos = [v for v in serie if v is not None]
        ant = validos[-2] if len(validos) > 1 else None
        pri = validos[0] if len(validos) > 1 else None
        saida.append({"rotulo": rot, "unidade": un, "valor": ult,
                      "dif_ant": None if ant is None else ult - ant, "tom_ant": _tom(None if ant is None else ult - ant, melhor),
                      "dif_pri": None if pri is None else ult - pri, "tom_pri": _tom(None if pri is None else ult - pri, melhor),
                      "mini": _mini(serie)})
    return saida


def grafico_composicao(avs, w=640, h=220):
    """variação (kg) de peso, massa livre de gordura, massa muscular e massa de gordura desde a primeira avaliação:
    com tudo na mesma escala absoluta (50 kg de peso e 10 kg de gordura) as mudanças sumiriam"""
    if len(avs) < 2:
        return None
    series = []
    for col, rot, cor in COMPOSICAO:
        brutos = [_f(a.get(col)) for a in avs]
        base = next((v for v in brutos if v is not None), None)
        if sum(v is not None for v in brutos) >= 2:
            series.append((rot, cor, [None if v is None else v - base for v in brutos], brutos))
    if not series:
        return None
    todos = [v for _, _, vs, _ in series for v in vs if v is not None] + [0]
    lo, hi = min(todos), max(todos)
    pad = (hi - lo) * 0.12 or 1
    lo, hi = lo - pad, hi + pad
    esq, dir_, top, base = 44, 12, 12, 28
    n = len(avs) - 1
    x = lambda i: esq + i / n * (w - esq - dir_)
    y = lambda v: top + (hi - v) / (hi - lo) * (h - top - base)
    linhas = []
    for rot, cor, vals, brutos in series:
        pts = [(x(i), y(v), v, brutos[i]) for i, v in enumerate(vals) if v is not None]
        linhas.append({"rotulo": rot, "cor": cor, "pontos": " ".join(f"{a:.1f},{b:.1f}" for a, b, _, _ in pts),
                       "marcas": [{"x": round(a, 1), "y": round(b, 1), "v": bruto, "dif": v} for a, b, v, bruto in pts],
                       "ultimo": vals[-1] if vals[-1] is not None else None})
    passo = (hi - lo) / 4
    grade = [{"y": round(y(lo + k * passo), 1), "v": lo + k * passo} for k in range(5)]
    datas = [{"x": round(x(i), 1), "d": a["data_avaliacao"]} for i, a in enumerate(avs)]
    return {"w": w, "h": h, "linhas": linhas, "grade": grade, "datas": datas, "esq": esq, "dir": w - dir_, "base": h - base,
            "zero": round(y(0), 1)}


METODOS = [("gordura_pct", "Dobras cutâneas", "c1"), ("bia_gordura_pct", "Bioimpedância", "c6"),
           ("foto_gordura_pct", "Foto (IA)", "c3")]


def metodos(avs, w=640, h=200):
    """% de gordura de cada método (dobras, bioimpedância, foto) por avaliação: tabela + gráfico.
    Só aparece quando há pelo menos dois métodos em alguma avaliação."""
    linhas = [{"data": a["data_avaliacao"], "protocolo": a.get("protocolo_dobras"), "app": a.get("foto_app"),
               "v": {col: _f(a.get(col)) for col, _, _ in METODOS}} for a in avs]
    linhas = [l for l in linhas if any(v is not None for v in l["v"].values())]
    if not any(sum(v is not None for v in l["v"].values()) >= 2 for l in linhas):
        return None
    for l in linhas:
        f = l["v"]["foto_gordura_pct"]
        l["dif"] = {col: (None if f is None or l["v"][col] is None else l["v"][col] - f) for col, _, _ in METODOS[:2]}
    todos = [v for l in linhas for v in l["v"].values() if v is not None]
    lo, hi = min(todos), max(todos)
    pad = (hi - lo) * 0.15 or 2
    lo, hi = max(0, lo - pad), hi + pad
    esq, dir_, top, base = 44, 12, 12, 28
    n = max(len(linhas) - 1, 1)
    x = lambda i: esq + (i / n if len(linhas) > 1 else 0.5) * (w - esq - dir_)
    y = lambda v: top + (hi - v) / (hi - lo) * (h - top - base)
    series = []
    for col, rot, cor in METODOS:
        pts = [(x(i), y(l["v"][col]), l["v"][col]) for i, l in enumerate(linhas) if l["v"][col] is not None]
        if pts:
            series.append({"rotulo": rot, "cor": cor, "pontos": " ".join(f"{a:.1f},{b:.1f}" for a, b, _ in pts),
                           "marcas": [{"x": round(a, 1), "y": round(b, 1), "v": v} for a, b, v in pts]})
    passo = (hi - lo) / 4
    grafico = {"w": w, "h": h, "series": series, "esq": esq, "dir": w - dir_,
               "grade": [{"y": round(y(lo + k * passo), 1), "v": lo + k * passo} for k in range(5)],
               "datas": [{"x": round(x(i), 1), "d": l["data"]} for i, l in enumerate(linhas)]}
    return {"linhas": linhas, "grafico": grafico, "tem_foto": any(l["v"]["foto_gordura_pct"] is not None for l in linhas)}


def grafico_gordura(avs, meta=None, w=640, h=160):
    """% de gordura por avaliação, em barras, com a linha da meta (se houver)"""
    vals = [(a["data_avaliacao"], _f(a.get("gordura_pct"))) for a in avs]
    vals = [(d, v) for d, v in vals if v is not None]
    if len(vals) < 2:
        return None
    hi = max([v for _, v in vals] + ([meta] if meta else [])) * 1.15
    esq, dir_, top, base = 44, 12, 12, 28
    larg = (w - esq - dir_) / len(vals)
    barras = [{"x": round(esq + i * larg + larg * 0.2, 1), "w": round(larg * 0.6, 1),
               "y": round(top + (hi - v) / hi * (h - top - base), 1), "h": round(v / hi * (h - top - base), 1),
               "v": v, "d": d, "cx": round(esq + i * larg + larg / 2, 1)} for i, (d, v) in enumerate(vals)]
    linha_meta = meta and round(top + (hi - meta) / hi * (h - top - base), 1)
    return {"w": w, "h": h, "barras": barras, "meta": meta, "y_meta": linha_meta, "esq": esq, "dir": w - dir_, "base": h - base}
