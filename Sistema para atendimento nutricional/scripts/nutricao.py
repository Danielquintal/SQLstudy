"""Cálculos do editor de planos: necessidade energética e nutrientes dos alimentos (tabela alimento, por 100 g).

Fórmulas da taxa metabólica basal (TMB), como o profissional usa:
- Harris-Benedict (1919): população adulta;
- Mifflin-St Jeor (1990): obesidade (IMC >= 30);
- FAO/OMS (1985): pacientes acamados (por faixa de idade, só com o peso).
Gasto energético total (GET) = TMB x fator atividade; meta = GET + ajuste (ex.: -500 kcal).
Meta de água = peso x ml/kg da diretriz escolhida (padrão 33 ml/kg, base adulta), ou o valor digitado.
O editor (sistema/templates/editor_plano.html) repete estas contas em JavaScript para mostrar enquanto se digita;
ao salvar, o servidor refaz tudo aqui, com os nutrientes tirados do banco.
"""
import math
from datetime import date

FORMULAS = {"harris": "Harris-Benedict", "mifflin": "Mifflin-St Jeor", "fao": "FAO/OMS"}
# diretrizes de água (ml por kg de peso por dia)
DIRETRIZES_AGUA = {25: "25 ml/kg · idosos", 30: "30 ml/kg", 33: "33 ml/kg · base adulta", 35: "35 ml/kg · adultos ativos",
                   40: "40 ml/kg · atletas e muito suor"}
COPO_ML = 300

# FAO/OMS 1985: (idade até, homem (a, b), mulher (a, b)) -> TMB = a x peso + b
FAO = [(18, (17.5, 651), (12.2, 746)), (30, (15.3, 679), (14.7, 496)), (60, (11.6, 879), (8.7, 829)),
       (999, (13.5, 487), (10.5, 596))]

MACROS = [("kcal", "kcal"), ("proteina_g", "p"), ("carboidrato_g", "c"), ("lipidios_g", "l")]
# nutrientes mostrados no total do dia (como no relatório do plano): coluna, rótulo, unidade
MICROS = [("ag_monoinsaturados_g", "AG Monoinsat.", "g"), ("ag_poliinsaturados_g", "AG Poliinsat.", "g"),
          ("ag_saturados_g", "AG Saturada", "g"), ("ag_trans_g", "AG Trans", "g"), ("colesterol_mg", "Colesterol", "mg"),
          ("fibra_g", "Fibras", "g"), ("calcio_mg", "Cálcio", "mg"), ("magnesio_mg", "Magnésio", "mg"),
          ("fosforo_mg", "Fósforo", "mg"), ("ferro_mg", "Ferro", "mg"), ("sodio_mg", "Sódio", "mg"),
          ("potassio_mg", "Potássio", "mg"), ("cobre_mg", "Cobre", "mg"), ("zinco_mg", "Zinco", "mg"),
          ("manganes_mg", "Manganês", "mg"), ("vit_a_re_mcg", "Vit. A (RE)", "mcg"),
          ("vit_a_rae_mcg", "Vit. A (RAE)", "mcg"), ("tiamina_mg", "Tiamina", "mg"),
          ("riboflavina_mg", "Riboflavina", "mg"), ("piridoxina_mg", "Piridoxina", "mg"),
          ("niacina_mg", "Niacina", "mg"), ("vit_c_mg", "Vit. C", "mg")]
COLUNAS = list(dict.fromkeys([c for c, _ in MACROS] + [c for c, _, _ in MICROS]))


def tmb(formula, sexo, peso, altura, idade):
    """taxa metabólica basal em kcal/dia; None se faltar dado"""
    if not peso or idade is None or sexo not in ("M", "F"):
        return None
    homem = sexo == "M"
    if formula == "fao":
        a, b = next(h if homem else m for ate, h, m in FAO if idade < ate)
        return a * peso + b
    if not altura:
        return None
    if formula == "mifflin":
        return 10 * peso + 6.25 * altura - 5 * idade + (5 if homem else -161)
    return (66.47 + 13.75 * peso + 5.003 * altura - 6.755 * idade if homem
            else 655.1 + 9.563 * peso + 1.850 * altura - 4.676 * idade)


def formula_sugerida(imc, acamado=False):
    if acamado:
        return "fao"
    return "mifflin" if imc and imc >= 30 else "harris"


def energia(e):
    """dados do editor -> {tmb, get, meta} (kcal/dia, arredondados) ou {} se faltar dado"""
    def num(k):
        try:
            return float(str(e.get(k)).replace(",", ".")) if e.get(k) not in (None, "") else None   # aceita "1,55"
        except (TypeError, ValueError):
            return None
    t = tmb(e.get("formula"), e.get("sexo"), num("peso"), num("altura"), num("idade"))
    if t is None:
        return {}
    fa = num("fa") or 1.0
    get = t * fa
    return {"tmb": round(t), "get": round(get), "meta": round(get + (num("ajuste") or 0))}


def _numero(v):
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def agua(editor):
    """meta de água do plano: (ml por dia, copos de 300 ml); None se desligada ou sem peso"""
    a = editor.get("agua") or {}
    if a.get("exibir") is False:
        return None
    ml = _numero(a.get("ml"))      # valor digitado pelo profissional; vazio = calcular pelo peso
    if not ml:
        peso = _numero((editor.get("energia") or {}).get("peso"))
        ml = peso * (_numero(a.get("ml_kg")) or 33) if peso else None
    if not ml:
        return None
    ml = round(ml)
    return ml, math.ceil(ml / COPO_ML)


def nutrientes(alimento, gramas):
    """nutrientes de uma porção: alimento tem os valores por 100 g; None continua None"""
    f = (gramas or 0) / 100
    return {c: (alimento[c] * f if alimento.get(c) is not None else None) for c in COLUNAS}


def somar(partes):
    total = {}
    for p in partes:
        for c, v in p.items():
            if v is not None:
                total[c] = total.get(c, 0) + v
    return total


def fmt(v):
    """1.0 -> "1", 1.25 -> "1,25" """
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def texto_quantidade(item):
    """"2 Colher de sopa cheia (50 g)" ou "50 g\""""
    g = float(item.get("gramas") or 0)
    m = item.get("medida")
    if m and m.get("nome") and m.get("qtd"):
        return f"{fmt(float(m['qtd']))} {m['nome']} ({fmt(g)} g)"
    return f"{fmt(g)} g"


def idade_em(nascimento, ref=None):
    if not nascimento:
        return None
    ref = ref or date.today()
    return ref.year - nascimento.year - ((ref.month, ref.day) < (nascimento.month, nascimento.day))


def plano_para_paciente(editor, alimentos, profissional):
    """editor (refeições com alimento_id e gramas) + nutrientes do banco -> plano no formato da aba Plano alimentar"""
    refeicoes, partes_dia, compras = [], [], []
    for r in editor.get("refeicoes", []):
        itens, partes = [], []
        for it in r.get("itens", []):
            a = alimentos.get(it.get("alimento_id"))
            if not a:
                continue
            n = nutrientes(a, float(it.get("gramas") or 0))
            partes.append(n)
            nome = (it.get("nome") or a["nome"]).strip()
            compras.append(nome)
            subs = [{"nome": (s.get("nome") or alimentos[s["alimento_id"]]["nome"]).strip(), "qtd": texto_quantidade(s)}
                    for s in it.get("subs", []) if s.get("alimento_id") in alimentos]
            itens.append({"nome": nome, "qtd": texto_quantidade(it), "subs": subs})
        if not itens:
            continue          # refeição que ficou sem alimento não vai para o paciente
        t = somar(partes)
        partes_dia += partes
        refeicoes.append({"hora": (r.get("hora") or None), "nome": (r.get("nome") or "Refeição").strip(),
                          "itens": itens, "obs": (r.get("obs") or "").strip(),
                          "kcal": round(t.get("kcal", 0)), "p": round(t.get("proteina_g", 0), 1),
                          "c": round(t.get("carboidrato_g", 0), 1), "l": round(t.get("lipidios_g", 0), 1)})
    dia = somar(partes_dia)
    prescrito = date.fromisoformat(editor["prescrito"]) if editor.get("prescrito") else date.today()
    meta_agua = agua(editor)
    suplementos = [{"nome": (s.get("nome") or "").strip(), "dose": (s.get("dose") or "").strip(),
                    "horario": (s.get("horario") or "").strip(), "obs": (s.get("obs") or "").strip()}
                   for s in (editor.get("suplementacao") or {}).get("itens", []) if (s.get("nome") or "").strip()]
    if suplementos:
        extra_supl = {"suplementos": suplementos}
    else:
        extra_supl = {}
    extra = {"agua": f"{meta_agua[0]} ml durante o dia (aproximadamente {meta_agua[1]} copos de {COPO_ML}ml)"} if meta_agua else {}
    return {"titulo": (editor.get("titulo") or "Plano alimentar").strip(), "prescrito": prescrito.strftime("%d/%m/%Y"),
            "profissional": profissional, "refeicoes": refeicoes, **extra, **extra_supl,
            "totais": {"kcal": round(dia.get("kcal", 0)), "p": round(dia.get("proteina_g", 0), 1),
                       "l": round(dia.get("lipidios_g", 0), 1), "c": round(dia.get("carboidrato_g", 0), 1)},
            "micros": [[rot, f"{fmt(round(dia[c], 1))}{un}"] for c, rot, un in MICROS if c in dia],
            "compras": sorted(set(compras), key=str.lower), "receitas": []}
