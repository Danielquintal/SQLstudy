"""Exames laboratoriais (referências em sistema/exames.json) e testes de desempenho."""
import json, math, re
from pathlib import Path

CATALOGO = Path(__file__).with_name("exames.json")
_cache = {}


def carregar():
    """tabela de referências (relida quando o arquivo muda)"""
    m = CATALOGO.stat().st_mtime
    if _cache.get("mtime") != m:
        _cache.update(mtime=m, dados=json.loads(CATALOGO.read_text(encoding="utf-8")))
    return _cache["dados"]


def gravar(dados):
    CATALOGO.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    _cache.clear()


def itens():
    """{id: item} na ordem da tabela, com o nome do grupo em cada item"""
    return {i["id"]: dict(i, grupo=g["nome"]) for g in carregar()["grupos"] for i in g["itens"]}


def ler_numero(s):
    """número digitado do laudo: 4,52 · 4.52 · 6.500 · 250.000 · 1.234,5"""
    s = str(s or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


# laudos escrevem algumas contagens em outra escala: converte para a unidade da tabela
ESCALA = {"hemacias": lambda v: v / 1e6 if v > 100 else v,
          "leucocitos": lambda v: v * 1000 if v < 100 else v,
          "neutrofilos": lambda v: v * 1000 if v < 100 else v,
          "plaquetas": lambda v: v * 1000 if v < 2000 else v,
          "hematocrito": lambda v: v * 100 if v < 1 else v,
          "rdw": lambda v: v * 100 if v < 1 else v}


def normalizar(item, v):
    return ESCALA[item](v) if item in ESCALA and v is not None else v


def ler_ref(texto):
    """referência do laudo -> (mínimo, máximo): "0,4 a 4,5", "até 190", "acima de 40", "< 5", "> 40", "4-10" """
    t = str(texto or "").lower().replace(" ", "")
    if not t:
        return None
    nums = [ler_numero(n) for n in re.findall(r"\d+(?:[.,]\d+)*", t)]
    nums = [n for n in nums if n is not None]
    if not nums:
        return None
    if re.match(r"^(até|ate|<|≤|inferiora|menorque|abaixode)", t):
        return (None, nums[0])
    if re.match(r"^(acimade|>|≥|superiora|maiorque|maiorouiguala)", t):
        return (nums[0], None)
    if len(nums) >= 2:
        return (nums[0], nums[1])
    return None


def ref_padrao(item, genero):
    r = item.get(genero) or item.get("ref")
    return tuple(r) if r else None


def fmt(v, casas=None):
    if v is None:
        return ""
    if casas is None:
        casas = 0 if abs(v) >= 1000 or float(v).is_integer() else 2 if abs(v) < 10 else 1
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s.rstrip("0").rstrip(",") if "," in s else s


def texto_ref(r):
    if not r:
        return ""
    lo, hi = r
    if lo is not None and hi is not None:
        return f"{fmt(lo)} a {fmt(hi)}"
    return f"até {fmt(hi)}" if hi is not None else f"acima de {fmt(lo)}"


def classificar(item, valor, genero, ref_laudo=None):
    """{"nivel": ok | baixo | alto | atencao | "" (sem referência), "rotulo", "ref"}"""
    r = ler_ref(ref_laudo)
    if r is None and item.get("faixas"):
        f = next(f for f in item["faixas"] if f["ate"] is None or valor < f["ate"])
        return {"nivel": f["nivel"], "rotulo": f["rotulo"], "ref": texto_ref(ref_padrao(item, genero))}
    r = r or ref_padrao(item, genero)
    if not r:
        return {"nivel": "", "rotulo": "", "ref": ""}
    lo, hi = r
    nivel = "baixo" if lo is not None and valor < lo else "alto" if hi is not None and valor > hi else "ok"
    return {"nivel": nivel, "rotulo": {"baixo": "Baixo", "alto": "Alto", "ok": "Normal"}[nivel],
            "ref": texto_ref(r) + (" (laudo)" if ler_ref(ref_laudo) else "")}


def calcular_indices(v):
    """índices a partir dos valores do exame ({id: valor}); só os que têm o que precisam"""
    out = {}
    g, ins, tg = v.get("glicose"), v.get("insulina"), v.get("triglicerides")
    if g and ins:
        out["homa_ir"] = g * ins / 405
    if g and tg:
        out["tyg"] = math.log(tg * g / 2)
    if v.get("colesterol_total") and v.get("hdl"):
        out["nao_hdl"] = v["colesterol_total"] - v["hdl"]
    leuc, linf = v.get("leucocitos"), v.get("linfocitos")
    linf_abs = leuc * linf / 100 if leuc and linf else None
    if linf_abs and v.get("neutrofilos"):
        neut = v["neutrofilos"] + (leuc * v["bastonetes"] / 100 if v.get("bastonetes") else 0)
        out["nlr"] = neut / linf_abs
    if linf and v.get("monocitos"):
        out["mlr"] = v["monocitos"] / linf
    if linf_abs and v.get("plaquetas"):
        out["plr"] = v["plaquetas"] / linf_abs
    return out


def _exames(cur, pid, limite=None):
    cur.execute("SELECT id, data, laboratorio, observacao FROM exame WHERE paciente_id = %s ORDER BY data", (pid,))
    exames = [dict(zip(["id", "data", "laboratorio", "observacao"], r)) for r in cur.fetchall()]
    if limite:
        exames = exames[-limite:]
    cur.execute("SELECT exame_id, item, valor, ref_laudo FROM exame_valor WHERE exame_id = ANY(%s)", ([e["id"] for e in exames],))
    por = {}
    for eid, item, valor, ref in cur.fetchall():
        por.setdefault(eid, {})[item] = (float(valor), ref)
    for e in exames:
        e["valores"] = por.get(e["id"], {})
        for k, val in calcular_indices({i: x[0] for i, x in e["valores"].items()}).items():
            e["valores"][k] = (val, None)
    return exames


def historico(cur, pid, genero, limite=None):
    """exames do mais antigo ao mais novo e, por grupo, as linhas com o valor e a classificação de cada data"""
    exames = _exames(cur, pid, limite)
    grupos = []
    for g in carregar()["grupos"]:
        linhas = []
        for it in g["itens"]:
            vals = []
            for e in exames:
                x = e["valores"].get(it["id"])
                vals.append(x and dict(classificar(it, x[0], genero, x[1]), valor=x[0], ref_laudo=x[1] or ""))
            if any(vals):
                linhas.append({"item": it, "valores": vals, "ref": texto_ref(ref_padrao(it, genero))})
        if linhas:
            grupos.append({"nome": g["nome"], "linhas": linhas})
    return exames, grupos


_GRAVIDADE = {"ok": 0, "atencao": 1, "baixo": 2, "alto": 2}


def _fora(item, x, genero):
    """quanto o valor está fora da referência (0 = dentro), relativo ao tamanho da faixa"""
    r = ler_ref(x.get("ref_laudo")) or ref_padrao(item, genero)
    if not r:
        return 0
    lo, hi = r
    escala = (hi - lo) if lo is not None and hi is not None and hi > lo else (hi or lo or 1)
    if lo is not None and x["valor"] < lo:
        return (lo - x["valor"]) / escala
    if hi is not None and x["valor"] > hi:
        return (x["valor"] - hi) / escala
    return 0


def comparar(grupos, ia, ib, genero):
    """compara a coleta ia (antes) com a ib (depois) em cada exame: valores, variação e se melhorou em relação
    à referência ("melhorou" = chegou mais perto ou entrou na faixa; dentro da faixa nas duas = "estavel")"""
    saida, resumo = [], {"melhorou": 0, "piorou": 0, "entrou": 0, "saiu": 0, "estavel": 0, "comparados": 0}
    for g in grupos:
        linhas = []
        for l in g["linhas"]:
            a, b = l["valores"][ia], l["valores"][ib]
            if not a and not b:
                continue
            linha = {"item": l["item"], "a": a, "b": b, "dif": None, "pct": None, "tend": ""}
            if a and b:
                resumo["comparados"] += 1
                linha["dif"] = b["valor"] - a["valor"]
                linha["pct"] = linha["dif"] / a["valor"] * 100 if a["valor"] else None
                ga, gb = _GRAVIDADE.get(a["nivel"]), _GRAVIDADE.get(b["nivel"])
                if ga is None or gb is None:
                    tend = ""                                   # sem referência: só a variação
                elif gb < ga:
                    tend = "melhorou"
                elif gb > ga:
                    tend = "piorou"
                elif ga == 0:
                    tend = "estavel"
                else:
                    fa, fb = _fora(l["item"], a, genero), _fora(l["item"], b, genero)
                    tend = "melhorou" if fb < fa - 1e-9 else "piorou" if fb > fa + 1e-9 else "estavel"
                linha["tend"] = tend
                if tend:
                    resumo[tend] += 1
                if a["nivel"] in ("alto", "baixo", "atencao") and b["nivel"] == "ok":
                    resumo["entrou"] += 1
                if a["nivel"] == "ok" and b["nivel"] in ("alto", "baixo", "atencao"):
                    resumo["saiu"] += 1
            linhas.append(linha)
        if linhas:
            saida.append({"nome": g["nome"], "linhas": linhas})
    return saida, resumo


def alertas(grupos):
    """o que ficou fora da referência no exame mais recente, com as possíveis causas"""
    saida = []
    for g in grupos:
        for l in g["linhas"]:
            x = l["valores"][-1]
            if x and x["nivel"] in ("alto", "baixo", "atencao"):
                causa = l["item"].get("baixo" if x["nivel"] == "baixo" else "alto") or ""
                saida.append({"nome": l["item"]["nome"], "valor": x["valor"], "unidade": l["item"].get("unidade", ""),
                              "nivel": x["nivel"], "rotulo": x["rotulo"], "ref": x["ref"], "causas": causa})
    return saida


def para_pagina(cur, pid, genero, limite=6):
    """exames para a página do paciente: valor, referência e classificação (sem as possíveis causas)"""
    exames, grupos = historico(cur, pid, genero, limite)
    return {"datas": [e["data"].strftime("%d/%m/%Y") for e in exames],
            "grupos": [{"nome": g["nome"], "linhas": [{"nome": l["item"]["nome"], "unidade": l["item"].get("unidade", ""),
                                                        "ref": next((x["ref"] for x in reversed(l["valores"]) if x), l["ref"]),
                                                        "valores": [x and [round(x["valor"], 3), x["nivel"], x["rotulo"]] for x in l["valores"]]}
                                                       for l in g["linhas"]]} for g in grupos]}


# ---------- testes de desempenho ----------
# sugestões ao digitar o nome do teste: (nome, unidade, melhor, dois lados)
TESTES = [
    ("Supino reto", "kg", "maior", False), ("Supino inclinado", "kg", "maior", False), ("Agachamento livre", "kg", "maior", False),
    ("Levantamento terra", "kg", "maior", False), ("Leg press", "kg", "maior", False), ("Remada", "kg", "maior", False),
    ("Puxada", "kg", "maior", False), ("Desenvolvimento", "kg", "maior", False), ("Cadeira extensora", "kg", "maior", False),
    ("Cadeira flexora", "kg", "maior", False), ("Elevação lateral", "kg", "maior", False),
    ("Dinamometria (preensão manual)", "kg", "maior", True), ("Salto vertical (CMJ)", "cm", "maior", False),
    ("Salto horizontal", "cm", "maior", False), ("Sprint 10 m", "s", "menor", False), ("Sprint 20 m", "s", "menor", False),
    ("Sprint 30 m", "s", "menor", False), ("Agilidade (T-test)", "s", "menor", False), ("Yo-Yo IR1", "m", "maior", False),
    ("Teste de Cooper (12 min)", "m", "maior", False), ("Corrida 5 km", "min", "menor", False), ("VO2máx", "mL/kg/min", "maior", False),
    ("Flexões de braço", "repetições", "maior", False), ("Barra fixa", "repetições", "maior", False),
    ("Abdominais em 1 min", "repetições", "maior", False), ("Prancha", "s", "maior", False),
    ("Frequência cardíaca de repouso", "bpm", "menor", False),
]


def variacao(atual, ref):
    return (atual - ref) / ref * 100 if ref else None


def desempenho(cur, pid):
    """testes agrupados pelo nome, cada um com os registros do mais antigo ao mais novo e a evolução"""
    cur.execute("SELECT id, data, teste, unidade, melhor, valor, valor_esq, observacao FROM desempenho WHERE paciente_id = %s "
                "ORDER BY lower(teste), data, id", (pid,))
    testes = {}
    for r in cur.fetchall():
        d = dict(zip(["id", "data", "teste", "unidade", "melhor", "valor", "valor_esq", "observacao"], r))
        d["valor"] = float(d["valor"])
        d["valor_esq"] = float(d["valor_esq"]) if d["valor_esq"] is not None else None
        t = testes.setdefault(d["teste"].strip().lower(), {"teste": d["teste"], "registros": []})
        t["unidade"], t["melhor"] = d["unidade"], d["melhor"]   # vale o do registro mais recente
        t["registros"].append(d)
    saida = []
    for t in testes.values():
        regs = t["registros"]
        t["bilateral"] = any(r["valor_esq"] is not None for r in regs)
        for i, r in enumerate(regs):
            ant = regs[i - 1] if i else None
            r["var_ant"] = variacao(r["valor"], ant["valor"]) if ant else None
            r["var_ant_esq"] = variacao(r["valor_esq"], ant["valor_esq"]) if ant and r["valor_esq"] is not None and ant["valor_esq"] else None
            r["assimetria"] = (abs(r["valor"] - r["valor_esq"]) / max(r["valor"], r["valor_esq"]) * 100
                               if r["valor_esq"] is not None and max(r["valor"], r["valor_esq"]) else None)
        prim, ult = regs[0], regs[-1]
        t["var_total"] = variacao(ult["valor"], prim["valor"]) if len(regs) > 1 else None
        t["var_total_esq"] = (variacao(ult["valor_esq"], prim["valor_esq"])
                              if len(regs) > 1 and ult["valor_esq"] is not None and prim["valor_esq"] else None)
        # melhorou = andou na direção boa do teste (carga subiu, tempo de sprint desceu)
        sinal = 1 if t["melhor"] == "maior" else -1
        t["melhorou"] = None if t["var_total"] is None else t["var_total"] * sinal > 0
        saida.append(t)
    return saida


def desempenho_pagina(cur, pid):
    out = []
    for t in desempenho(cur, pid):
        out.append({"teste": t["teste"], "unidade": t["unidade"], "melhor": t["melhor"], "bilateral": t["bilateral"],
                    "var_total": t["var_total"] and round(t["var_total"], 1), "var_total_esq": t["var_total_esq"] and round(t["var_total_esq"], 1),
                    "registros": [{"data": r["data"].strftime("%d/%m/%Y"), "valor": r["valor"], "esq": r["valor_esq"],
                                   "assimetria": r["assimetria"] and round(r["assimetria"], 1), "obs": r["observacao"] or ""}
                                  for r in t["registros"]]})
    return out


def extras_pagina(cur, pid):
    """o que a página do paciente mostra além das avaliações e do plano: check-ins, RED-S, exames e desempenho"""
    import checkin, reds
    cur.execute("SELECT genero FROM paciente WHERE id = %s", (pid,))
    genero = (cur.fetchone() or [None])[0]
    import perfil
    from atualizar_paciente import avaliacoes_do_banco
    cur.execute("SELECT data_nascimento, meta_gordura_pct, meta_imo, meta_passos FROM paciente WHERE id = %s", (pid,))
    nasc, alvo_gc, alvo_imo, passos = cur.fetchone() or (None, None, None, None)
    return {"passos": passos, "checkins": checkin.para_pagina(cur, pid), "reds": reds.para_pagina(cur, pid),
            "exames": para_pagina(cur, pid, genero), "desempenho": desempenho_pagina(cur, pid),
            "perfil": perfil.para_pagina(avaliacoes_do_banco(cur, pid), genero, nasc,
                                         alvo_gc and float(alvo_gc), alvo_imo and float(alvo_imo))}


def tem_extras(e):
    return bool(e["checkins"] or e["reds"]["leafq"] or e["reds"]["energia"] or e["exames"]["datas"] or e["desempenho"])
