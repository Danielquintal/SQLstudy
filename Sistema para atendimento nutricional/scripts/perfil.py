"""Perfil antropométrico: mais protocolos de % de gordura, somatotipo (Heath-Carter), PVC (Mirwald), Z-score (Phantom) e metas.

Equações publicadas, as mesmas das planilhas "SOFTWARE" de cineantropometria, com três correções:
Petroski masculino com a constante publicada (1,10726863), PVC masculino com a equação dos meninos e
Z-score da massa corporal ajustado pela estatura ao cubo (o % de gordura não é ajustado).
Usa os nomes das colunas da tabela avaliacao. A dobra "crista ilíaca" das planilhas é a suprailíaca do sistema.
"""
import math
import re
from numbers import Number

from calculos import POLLOCK3, POLLOCK7, GUEDES, densidade as densidade_pollock

NOMES = {"dobra_tricipital": "tricipital", "dobra_bicipital": "bicipital", "dobra_subescapular": "subescapular",
         "dobra_toracica": "torácica", "dobra_axilar_media": "axilar média", "dobra_suprailiaca": "suprailíaca",
         "dobra_supraespinhal": "supraespinhal", "dobra_abdominal": "abdominal", "dobra_coxa": "coxa",
         "dobra_panturrilha": "panturrilha", "peso_kg": "peso", "altura_cm": "altura", "altura_sentado_cm": "altura sentado",
         "idade": "idade", "circ_cintura": "circ. cintura", "circ_abdomen": "circ. abdômen", "circ_quadril": "circ. quadril",
         "braco_relaxado": "braço relaxado", "braco_contraido": "braço contraído", "panturrilha": "circ. panturrilha",
         "coxa_medial": "coxa medial", "diametro_umero": "diâmetro do úmero", "diametro_femur": "diâmetro do fêmur",
         "massa_muscular_kg": "massa muscular", "massa_ossea_kg": "massa óssea", "gordura_pct": "% de gordura"}

TRI, BIC, SUB, SI, SE, ABD, CX, PT = ("dobra_tricipital", "dobra_bicipital", "dobra_subescapular", "dobra_suprailiaca",
                                      "dobra_supraespinhal", "dobra_abdominal", "dobra_coxa", "dobra_panturrilha")


def lado(v, base):
    """circunferência de um lado: o esquerdo (como a CMB do sistema) ou, sem ele, o direito"""
    for k in (base + "_e", base + "_d", base):
        if v.get(k) not in (None, ""):
            return float(v[k])
    return None


def _am(x):
    return (x["circ_cintura"] + x["circ_abdomen"]) / 2   # média das circunferências abdominais (Weltman)


# protocolo -> sexo, nome, autor, para quem, dobras somadas, outras medidas, tipo (densidade ou % direto), conta, fórmula escrita
PROTOCOLOS = {
    "pollock7": dict(sexo="MF", nome="Pollock 7 dobras", ref="Jackson & Pollock, 1978; Jackson, Pollock & Ward, 1980",
                     publico="18 a 61 anos", dobras=POLLOCK7, outros=["idade"], tipo="densidade"),
    "pollock3": dict(sexo="MF", nome="Pollock 3 dobras", ref="Jackson & Pollock, 1978; Jackson, Pollock & Ward, 1980",
                     publico="18 a 61 anos", dobras=None, outros=["idade"], tipo="densidade"),
    "guedes": dict(sexo="MF", nome="Guedes", ref="Guedes, 1985", publico="17 a 29 anos · universitários",
                   dobras=None, outros=[], tipo="densidade"),
    "petroski": dict(sexo="M", nome="Petroski", ref="Petroski, 1995", publico="18 a 66 anos · Sul do Brasil",
                     dobras=[SUB, TRI, SI, PT], outros=["idade"], tipo="densidade",
                     conta=lambda S, x: 1.10726863 - 0.00081201 * S + 0.00000212 * S ** 2 - 0.00041761 * x["idade"],
                     formula="1,10726863 − 0,00081201 × S + 0,00000212 × S² − 0,00041761 × idade"),
    "petroski_f": dict(sexo="F", nome="Petroski", ref="Petroski, 1995", publico="18 a 51 anos · Sul do Brasil",
                       dobras=[SUB, TRI, SI, PT], outros=["idade", "peso_kg", "altura_cm"], tipo="densidade",
                       conta=lambda S, x: (1.02902361 - 0.00067159 * S + 0.00000242 * S ** 2 - 0.00026073 * x["idade"]
                                           - 0.00056009 * x["peso_kg"] + 0.00054649 * x["altura_cm"]),
                       formula="1,02902361 − 0,00067159 × S + 0,00000242 × S² − 0,00026073 × idade − 0,00056009 × peso + 0,00054649 × altura"),
    "durnin": dict(sexo="M", nome="Durnin & Womersley", ref="Durnin & Womersley, 1974", publico="17 a 72 anos",
                   dobras=[TRI, BIC, SUB, SI], outros=[], tipo="densidade",
                   conta=lambda S, x: 1.1765 - 0.0744 * math.log10(S), formula="1,1765 − 0,0744 × log₁₀(S)"),
    "durnin_f": dict(sexo="F", nome="Durnin & Womersley", ref="Durnin & Womersley, 1974", publico="16 a 68 anos",
                     dobras=[TRI, BIC, SUB, SI], outros=[], tipo="densidade",
                     conta=lambda S, x: 1.1567 - 0.0717 * math.log10(S), formula="1,1567 − 0,0717 × log₁₀(S)"),
    "jackson4": dict(sexo="M", nome="Jackson & Pollock 4 dobras", ref="Jackson & Pollock, 1985", publico="18 a 61 anos",
                     dobras=[ABD, SI, TRI, CX], outros=["idade"], tipo="gordura",
                     conta=lambda S, x: 0.29288 * S - 0.0005 * S ** 2 + 0.15845 * x["idade"] - 5.76377,
                     formula="0,29288 × S − 0,0005 × S² + 0,15845 × idade − 5,76377"),
    "faulkner": dict(sexo="M", nome="Faulkner", ref="Faulkner, 1968", publico="estudantes de educação física",
                     dobras=[TRI, SUB, SI, ABD], outros=[], tipo="gordura",
                     conta=lambda S, x: 5.783 + 0.153 * S, formula="5,783 + 0,153 × S"),
    "katch": dict(sexo="M", nome="Katch & McArdle", ref="Katch & McArdle, 1973", publico="19 a 21 anos · estudantes",
                  dobras=[TRI, SUB, ABD], outros=[], tipo="densidade",
                  conta=lambda S, x: 1.09665 - 0.00103 * x[TRI] - 0.00056 * x[SUB] - 0.00054 * x[ABD],
                  formula="1,09665 − 0,00103 × tricipital − 0,00056 × subescapular − 0,00054 × abdominal"),
    "withers": dict(sexo="M", nome="Withers", ref="Withers et al., 1987", publico="15 a 39 anos · atletas de elite",
                    dobras=[TRI, SUB, BIC, SE, ABD, CX, PT], outros=[], tipo="densidade",
                    conta=lambda S, x: 1.0988 - 0.0004 * S, formula="1,0988 − 0,0004 × S"),
    "weltman": dict(sexo="M", nome="Weltman (circunferências)", ref="Weltman et al., 1987", publico="24 a 68 anos · obesos",
                    dobras=[], outros=["circ_cintura", "circ_abdomen", "peso_kg"], tipo="gordura",
                    conta=lambda S, x: 0.31457 * _am(x) - 0.10969 * x["peso_kg"] + 10.8336,
                    formula="0,31457 × média (cintura, abdômen) − 0,10969 × peso + 10,8336"),
    "tran_weltman": dict(sexo="F", nome="Tran & Weltman (circunferências)", ref="Tran & Weltman, 1989", publico="15 a 79 anos",
                         dobras=[], outros=["circ_cintura", "circ_abdomen", "circ_quadril", "altura_cm", "idade"], tipo="densidade",
                         conta=lambda S, x: (1.168297 - 0.002824 * _am(x) + 0.0000122098 * _am(x) ** 2 - 0.000733128 * x["circ_quadril"]
                                             + 0.000510477 * x["altura_cm"] - 0.000216161 * x["idade"]),
                         formula="1,168297 − 0,002824 × M + 0,0000122098 × M² − 0,000733128 × quadril + 0,000510477 × altura − 0,000216161 × idade (M = média cintura e abdômen)"),
    "weltman_f": dict(sexo="F", nome="Weltman (circunferências)", ref="Weltman et al., 1988", publico="20 a 60 anos · obesas",
                      dobras=[], outros=["circ_cintura", "circ_abdomen", "altura_cm", "peso_kg"], tipo="gordura",
                      conta=lambda S, x: 0.11077 * _am(x) - 0.17666 * x["altura_cm"] + 0.14354 * x["peso_kg"] + 51.03301,
                      formula="0,11077 × média (cintura, abdômen) − 0,17666 × altura + 0,14354 × peso + 51,03301"),
    "lewis": dict(sexo="F", nome="Lewis", ref="Lewis et al., 1978", publico="30 a 59 anos · corredoras",
                  dobras=[TRI, SUB], outros=["altura_cm", "braco_relaxado"], tipo="densidade",
                  conta=lambda S, x: 0.97845 - 0.0002 * x[TRI] + 0.00088 * x["altura_cm"] - 0.00122 * x[SUB] - 0.00234 * x["braco_relaxado"],
                  formula="0,97845 − 0,0002 × tricipital + 0,00088 × altura − 0,00122 × subescapular − 0,00234 × braço relaxado"),
    "thorland": dict(sexo="F", nome="Thorland", ref="Thorland et al., 1984", publico="jovens atletas de elite",
                     dobras=[TRI, SUB, SI], outros=[], tipo="densidade",
                     conta=lambda S, x: 1.0987 - 0.00122 * S + 0.00000263 * S ** 2, formula="1,0987 − 0,00122 × S + 0,00000263 × S²"),
    "slaughter": dict(sexo="M", nome="Slaughter", ref="Slaughter et al., 1988", publico="8 a 17 anos · meninos",
                      dobras=[TRI, PT], outros=[], tipo="gordura", conta=lambda S, x: 0.735 * S + 1.0, formula="0,735 × S + 1,0"),
    "slaughter_f": dict(sexo="F", nome="Slaughter", ref="Slaughter et al., 1988", publico="8 a 17 anos · meninas",
                        dobras=[TRI, PT], outros=[], tipo="gordura", conta=lambda S, x: 0.61 * S + 5.1, formula="0,61 × S + 5,1"),
    "yuhasz": dict(sexo="M", nome="Yuhasz", ref="Yuhasz, 1974", publico="jovens",
                   dobras=[TRI, SUB, SE, ABD, CX, PT], outros=[], tipo="gordura", conta=lambda S, x: 0.1051 * S + 2.585, formula="0,1051 × S + 2,585"),
    "yuhasz_f": dict(sexo="F", nome="Yuhasz", ref="Yuhasz, 1974", publico="jovens",
                     dobras=[TRI, SUB, SE, ABD, CX, PT], outros=[], tipo="gordura", conta=lambda S, x: 0.1548 * S + 3.58, formula="0,1548 × S + 3,58"),
}


def do_sexo(genero):
    return [k for k, p in PROTOCOLOS.items() if genero in p["sexo"]] if genero in ("M", "F") else list(PROTOCOLOS)


def dobras(prot, genero):
    p = PROTOCOLOS.get(prot)
    if not p:
        return []
    if prot == "pollock3":
        return POLLOCK3.get(genero, [])
    if prot == "guedes":
        return GUEDES.get(genero, [])
    return p["dobras"]


def nome(prot):
    p = PROTOCOLOS.get(prot)
    return p["nome"] if p else prot


def _valores(v, idade):
    x = {k: float(val) for k, val in v.items() if isinstance(val, Number) and not isinstance(val, bool)}
    if idade is not None:
        x["idade"] = idade
    for base in ("braco_relaxado", "braco_contraido", "panturrilha", "coxa_medial"):
        val = lado(v, base)
        if val is not None:
            x[base] = val
    return x


def gordura(prot, v, genero, idade, eq="siri"):
    """% de gordura por um protocolo: {gc, densidade, soma} ou {falta: [...]} ou None (protocolo de outro sexo)"""
    p = PROTOCOLOS.get(prot)
    if not p or genero not in p["sexo"]:
        return None
    x = _valores(v, idade)
    if prot in ("pollock7", "pollock3", "guedes"):
        ds = dobras(prot, genero)
        falta = [NOMES[k] for k in ds if k not in x] + (["idade"] if prot != "guedes" and idade is None else [])
        if falta:
            return {"falta": falta}
        d, s = densidade_pollock(prot, genero, idade, x)
    else:
        falta = [NOMES[k] for k in p["dobras"] + p["outros"] if k not in x]
        if falta:
            return {"falta": falta}
        s = sum(x[k] for k in p["dobras"]) if p["dobras"] else None
        r = p["conta"](s, x)
        if p["tipo"] == "gordura":
            return {"gc": r, "densidade": None, "soma": s}
        d = r
    if not d:
        return {"falta": ["dados"]}
    gc = 495 / d - 450 if eq != "brozek" else 457 / d - 414.2
    return {"gc": gc, "densidade": d, "soma": s}


def comparar(v, genero, idade, eq="siri"):
    """todos os protocolos do sexo do paciente para a mesma avaliação"""
    saida = []
    for k in do_sexo(genero):
        p, r = PROTOCOLOS[k], gordura(k, v, genero, idade, eq) or {}
        faixa = re.search(r"(\d+) a (\d+) anos", p["publico"])
        fora = bool(faixa and idade is not None and not int(faixa.group(1)) <= idade <= int(faixa.group(2)))
        saida.append({"protocolo": k, "nome": p["nome"], "ref": p["ref"], "publico": p["publico"], "fora_idade": fora,
                      "gc": r.get("gc"), "densidade": r.get("densidade"), "falta": r.get("falta", [])})
    return saida


# ---------- somatotipo (Heath-Carter) ----------
def somatotipo(v):
    x = _valores(v, None)
    precisa = [TRI, SUB, SE, PT, "diametro_umero", "diametro_femur", "braco_contraido", "panturrilha", "altura_cm", "peso_kg"]
    falta = [NOMES[k] for k in precisa if k not in x]
    if falta:
        return {"falta": falta}
    h = x["altura_cm"]
    s3 = (x[TRI] + x[SUB] + x[SE]) * 170.18 / h
    endo = -0.7182 + 0.1451 * s3 - 0.00068 * s3 ** 2 + 0.0000014 * s3 ** 3
    meso = (0.858 * x["diametro_umero"] + 0.601 * x["diametro_femur"] + 0.188 * (x["braco_contraido"] - x[TRI] / 10)
            + 0.161 * (x["panturrilha"] - x[PT] / 10) - 0.131 * h + 4.5)
    hwr = h / x["peso_kg"] ** (1 / 3)
    ecto = 0.732 * hwr - 28.58 if hwr >= 40.75 else 0.463 * hwr - 17.63 if hwr > 38.25 else 0.1
    endo, meso, ecto = (max(c, 0.1) for c in (endo, meso, ecto))
    return {"endo": endo, "meso": meso, "ecto": ecto, "hwr": hwr, "x": ecto - endo, "y": 2 * meso - (endo + ecto),
            "classe": classe_somatotipo(endo, meso, ecto)}


def classe_somatotipo(endo, meso, ecto):
    """13 categorias de Carter & Heath (1990): diferenças de meia unidade contam como iguais"""
    c = {"endo": endo, "meso": meso, "ecto": ecto}
    subst = {"endo": "Endomorfo", "meso": "Mesomorfo", "ecto": "Ectomorfo"}
    adj = {"endo": "endomórfico", "meso": "mesomórfico", "ecto": "ectomórfico"}
    ordem = sorted(c, key=c.get, reverse=True)
    a, b, d = ordem
    if c[a] - c[d] <= 1:
        return "Central"
    if c[a] - c[b] <= 0.5:
        par = sorted((a, b), key=["endo", "meso", "ecto"].index)
        return f"{subst[par[0]]}-{subst[par[1]].lower()}"
    if c[b] - c[d] <= 0.5:
        return f"{subst[a]} equilibrado"
    return f"{subst[a]} {adj[b]}"


# ---------- pico de velocidade de crescimento (Mirwald et al., 2002) ----------
APHV_MEDIA = {"M": 13.8, "F": 11.8}


def pvc(v, genero, nascimento, data):
    if genero not in ("M", "F") or not nascimento or not data:
        return None
    idade = (data - nascimento).days / 365.25
    if idade >= 18:
        return None
    x = _valores(v, idade)
    falta = [NOMES[k] for k in ("peso_kg", "altura_cm", "altura_sentado_cm") if k not in x]
    if falta:
        return {"falta": falta, "idade": idade}
    p, h, s = x["peso_kg"], x["altura_cm"], x["altura_sentado_cm"]
    perna = h - s
    if genero == "M":
        off = (-9.236 + 0.0002708 * perna * s - 0.001663 * idade * perna + 0.007216 * idade * s + 0.02292 * (p / h * 100))
    else:
        off = (-9.376 + 0.0001882 * perna * s + 0.0022 * idade * perna + 0.005841 * idade * s - 0.002658 * idade * p
               + 0.07693 * (p / h * 100))
    aphv = idade - off
    media = APHV_MEDIA[genero]
    fase = "Antes do pico" if off < -1 else "Perto do pico" if off <= 1 else "Depois do pico"
    momento = "precoce" if aphv < media - 1 else "tardia" if aphv > media + 1 else "na média"
    return {"offset": off, "idade": idade, "idade_pvc": aphv, "fase": fase, "momento": momento, "media": media,
            "fora": not (8 <= idade <= 17)}


# ---------- Z-score de proporcionalidade (Phantom, Ross & Wilson, 1974) ----------
# (grupo, nome, chave, média do Phantom, desvio, expoente do ajuste pela estatura)
PHANTOM = [
    ("Básicas", "Massa corporal", "peso_kg", 64.58, 8.60, 3),
    ("Básicas", "Altura sentado", "altura_sentado_cm", 89.92, 4.50, 1),
    ("Dobras", "Tricipital", TRI, 15.4, 4.47, 1), ("Dobras", "Subescapular", SUB, 17.2, 5.07, 1),
    ("Dobras", "Bicipital", BIC, 8.0, 2.0, 1), ("Dobras", "Suprailíaca (crista ilíaca)", SI, 22.4, 6.80, 1),
    ("Dobras", "Supraespinhal", SE, 15.4, 4.47, 1), ("Dobras", "Abdominal", ABD, 25.4, 7.78, 1),
    ("Dobras", "Coxa", CX, 27.0, 8.33, 1), ("Dobras", "Panturrilha", PT, 16.0, 4.67, 1),
    ("Perímetros", "Pescoço", "circ_pescoco", 34.91, 1.73, 1),
    ("Perímetros", "Braço relaxado", "braco_relaxado", 26.89, 2.33, 1), ("Perímetros", "Braço contraído", "braco_contraido", 29.41, 2.37, 1),
    ("Perímetros", "Antebraço", "antebraco", 25.13, 1.41, 1), ("Perímetros", "Tórax", "circ_torax", 87.86, 5.18, 1),
    ("Perímetros", "Cintura", "circ_cintura", 71.91, 4.45, 1), ("Perímetros", "Quadril", "circ_quadril", 94.67, 5.58, 1),
    ("Perímetros", "Coxa proximal", "coxa_proximal", 55.82, 4.23, 1), ("Perímetros", "Coxa medial", "coxa_medial", 53.20, 4.56, 1),
    ("Perímetros", "Panturrilha", "panturrilha", 35.25, 2.30, 1),
    ("Diâmetros", "Úmero", "diametro_umero", 6.48, 0.35, 1), ("Diâmetros", "Fêmur", "diametro_femur", 9.52, 0.48, 1),
    ("Diâmetros", "Punho", "diametro_punho", 5.21, 0.28, 1),
    ("Composição", "% de gordura", "gordura_pct", 18.78, 5.20, 0),
]


def zscores(v):
    x = _valores(v, None)
    for base in ("antebraco", "coxa_proximal"):
        val = lado(v, base)
        if val is not None:
            x[base] = val
    h = x.get("altura_cm")
    if not h:
        return []
    return [{"grupo": g, "nome": n, "valor": x[k], "z": (x[k] * (170.18 / h) ** d - m) / s}
            for g, n, k, m, s, d in PHANTOM if k in x]


# ---------- metas ----------
def massa_muscular_lee(v, genero, idade):
    """Lee et al., 2000 (sem o ajuste de etnia)"""
    x = _valores(v, idade)
    precisa = ["altura_cm", "braco_relaxado", TRI, "coxa_medial", CX, "panturrilha", PT, "idade"]
    if genero not in ("M", "F") or any(k not in x for k in precisa):
        return None
    cag = x["braco_relaxado"] - math.pi * x[TRI] / 10
    ctg = x["coxa_medial"] - math.pi * x[CX] / 10
    ccg = x["panturrilha"] - math.pi * x[PT] / 10
    return (x["altura_cm"] / 100 * (0.00744 * cag ** 2 + 0.00088 * ctg ** 2 + 0.00441 * ccg ** 2)
            + 2.4 * (genero == "M") - 0.048 * x["idade"] + 7.8)


def metas(v, genero, idade, alvo_gc=None, alvo_imo=None):
    x = _valores(v, idade)
    out = {"alvo_gc": alvo_gc, "alvo_imo": alvo_imo}
    peso, gc = x.get("peso_kg"), x.get("gordura_pct")
    mm, mo = x.get("massa_muscular_kg"), x.get("massa_ossea_kg")
    if mm and mo:
        out["imo"] = mm / mo
    lee = massa_muscular_lee(v, genero, idade)
    if lee:
        out["muscular_lee"] = lee
    if alvo_gc and peso and gc is not None and 0 < alvo_gc < 60:
        mlg = peso * (1 - gc / 100)
        sugerido = mlg * 100 / (100 - alvo_gc)
        out.update(peso_sugerido=sugerido, gordura_a_perder=peso - sugerido, gordura_alvo_kg=sugerido * alvo_gc / 100)
    if alvo_imo and mm and mo:
        out.update(muscular_alvo=mo * alvo_imo, muscular_a_ganhar=mo * alvo_imo - mm)
    return out


def perfil(v, genero, nascimento, data, alvo_gc=None, alvo_imo=None, eq="siri"):
    from calculos import idade_em
    idade = idade_em(nascimento, data)
    return {"protocolos": comparar(v, genero, idade, eq), "somatotipo": somatotipo(v), "pvc": pvc(v, genero, nascimento, data),
            "z": zscores(v), "metas": metas(v, genero, idade, alvo_gc, alvo_imo)}


def _r(d, casas=2):
    return {k: round(x, casas) if isinstance(x, float) else x for k, x in d.items()}


def para_pagina(avs, genero, nascimento, alvo_gc=None, alvo_imo=None):
    """somatotipo e PVC de cada avaliação, Z-score e metas da mais recente (avs: linhas da tabela avaliacao)"""
    from calculos import idade_em
    som, pvcs = [], []
    for a in avs:
        d = a["data_avaliacao"]
        s = somatotipo(a)
        if "endo" in s:
            som.append(dict(_r({k: s[k] for k in ("endo", "meso", "ecto", "x", "y")}), data=d.strftime("%d/%m/%Y"), classe=s["classe"]))
        p = pvc(a, genero, nascimento, d)
        if p and "offset" in p:
            pvcs.append(dict(_r({k: p[k] for k in ("offset", "idade", "idade_pvc", "media")}), data=d.strftime("%d/%m/%Y"),
                             fase=p["fase"], momento=p["momento"]))
    ult = avs[-1] if avs else None
    z = [_r(x) for x in zscores(ult)] if ult else []
    m = _r(metas(ult, genero, idade_em(nascimento, ult["data_avaliacao"]), alvo_gc, alvo_imo), 1) if ult else {}
    return {"somatotipo": som, "pvc": pvcs, "z": z if len(z) >= 5 else [],
            "data": ult["data_avaliacao"].strftime("%d/%m/%Y") if ult else "", "metas": m}
