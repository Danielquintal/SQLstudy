"""Cálculos da avaliação antropométrica, iguais aos do App Naive (conferidos com as 1297 avaliações do banco).

calcular(valores, genero, nascimento, data) devolve o que dá para calcular com o que foi medido:
IMC e classificação, peso ideal, RCQ e risco, CMB e adequação, somatório de dobras, densidade, % de gordura,
massas (gordura, livre de gordura, residual, óssea, muscular) e a classificação do % de gordura (dobras e bioimpedância).
Um valor já preenchido nunca é trocado; ele entra no lugar do calculado nas contas seguintes.
"""
import math

# Pollock 7 dobras: as mesmas para os dois sexos
POLLOCK7 = ["dobra_toracica", "dobra_axilar_media", "dobra_tricipital", "dobra_subescapular",
            "dobra_abdominal", "dobra_suprailiaca", "dobra_coxa"]
POLLOCK3 = {"M": ["dobra_toracica", "dobra_abdominal", "dobra_coxa"],
            "F": ["dobra_tricipital", "dobra_suprailiaca", "dobra_coxa"]}
GUEDES = {"M": ["dobra_tricipital", "dobra_suprailiaca", "dobra_abdominal"],
          "F": ["dobra_subescapular", "dobra_suprailiaca", "dobra_coxa"]}

# % de gordura: 8 classes e os pontos de corte (abaixo do 1º corte = 1ª classe), por sexo e idade até
CLASSES_GORDURA = ["Excessivamente baixa", "Excelente", "Adequada", "Elevada", "Moderadamente alta", "Alta",
                   "Muito alta", "Excessivamente alta"]
CORTES_GORDURA = {
    "M": [(25, [4, 6, 10, 13, 16, 20, 24]),
          (35, [8, 11, 15, 18, 20, 22, 24]),
          (45, [10, 14, 18, 21, 23, 26, 29]),
          (55, [12, 17, 20, 23, 25, 26.4, 30]),
          (999, [15, 19, 22, 24, 26, 27, 28])],      # poucas avaliações nessa idade: cortes estimados
    "F": [(25, [13, 16, 19, 22, 25, 28, 31]),
          (35, [14, 16, 20, 23, 25, 29, 33]),
          (45, [16, 19, 22.5, 26, 29, 32, 36]),
          (55, [18, 22, 24, 28, 31, 35, 36.5]),      # dois primeiros cortes estimados
          (999, [18, 23, 26, 29.5, 33, 36, 38.5])],  # poucas avaliações nessa idade: cortes estimados
}
IDADE_MINIMA_GORDURA = 15

# RCQ (Bray): abaixo do 1º corte risco baixo, depois moderado, alto e muito alto, por sexo e idade até
RISCOS_RCQ = ["Risco baixo", "Risco moderado", "Risco alto", "Risco muito alto"]
CORTES_RCQ = {
    "M": [(29, [.83, .89, .94]), (39, [.84, .91, .96]), (49, [.88, .96, 1.00]), (59, [.90, .97, 1.02]),
          (999, [.91, .99, 1.03])],
    "F": [(29, [.71, .78, .82]), (39, [.72, .79, .84]), (49, [.73, .80, .87]), (59, [.74, .82, .88]),
          (999, [.76, .84, .90])],
}

# CMB: percentil 50 (Frisancho) por sexo e idade até
CMB_P50 = {
    "M": [(13, 21.1), (14, 22.1), (15, 23.7), (16, 24.9), (17, 25.8), (18, 26.4), (25, 27.3), (35, 27.9),
          (45, 28.6), (55, 28.1), (65, 27.8), (999, 26.8)],
    "F": [(14, 20.1), (16, 20.2), (17, 20.5), (18, 20.2), (25, 20.7), (35, 21.2), (45, 21.8), (55, 22.0),
          (999, 22.5)],
}


def idade_em(nascimento, data):
    if not nascimento or not data:
        return None
    return data.year - nascimento.year - ((data.month, data.day) < (nascimento.month, nascimento.day))


def faixa(tabela, idade):
    return next(v for ate, v in tabela if idade <= ate)


def classe(valor, cortes, nomes):
    return nomes[sum(valor >= c for c in cortes)]


def classificar_imc(imc, idade=None):
    imc = round(imc, 1)  # o App Naive classifica o IMC já arredondado
    if not 8 <= imc <= 100:
        return "Verifique altura e peso"
    if idade is not None and idade >= 60:  # idosos: Lipschitz
        return classe(imc, [22, 27.01], ["Baixo peso", "Peso adequado", "Sobrepeso"])
    return classe(imc, [18.5, 25, 30, 35, 40], ["Baixo peso", "Eutrófico", "Sobrepeso", "Obesidade grau 1",
                                                "Obesidade grau 2", "Obesidade grau 3"])


def classificar_gordura(gc, genero, idade):
    if genero not in CORTES_GORDURA or idade is None:
        return None
    if idade < IDADE_MINIMA_GORDURA:
        return "N/D Verif. Idade mínima"
    return classe(gc, faixa(CORTES_GORDURA[genero], idade), CLASSES_GORDURA)


def classificar_cmb(pct):
    return classe(pct, [70, 80, 90], ["Desnutrição Grave", "Desnutrição Moderada", "Desnutrição Leve", "Eutrófico"])


def densidade(protocolo, genero, idade, dobras):
    """densidade corporal e somatório das dobras do protocolo; None se faltar alguma dobra"""
    if protocolo == "pollock7":
        chaves = POLLOCK7
    elif protocolo == "pollock3":
        chaves = POLLOCK3.get(genero)
    elif protocolo == "guedes":
        chaves = GUEDES.get(genero)
    else:
        return None, None
    if not chaves or any(dobras.get(k) is None for k in chaves):
        return None, None
    s = sum(dobras[k] for k in chaves)
    if protocolo == "guedes":
        return (1.1714 - 0.0671 * math.log10(s) if genero == "M" else 1.1665 - 0.0706 * math.log10(s)), s
    if idade is None:
        return None, s
    if protocolo == "pollock7":
        d = (1.112 - 0.00043499 * s + 0.00000055 * s ** 2 - 0.00028826 * idade if genero == "M"
             else 1.097 - 0.00046971 * s + 0.00000056 * s ** 2 - 0.00012828 * idade)
    else:
        d = (1.10938 - 0.0008267 * s + 0.0000016 * s ** 2 - 0.0002574 * idade if genero == "M"
             else 1.0994921 - 0.0009929 * s + 0.0000023 * s ** 2 - 0.0001392 * idade)
    return d, s


def calcular(v, genero, nascimento, data):
    """v: valores do formulário (números já convertidos, None = em branco). Devolve só o que calculou."""
    idade = idade_em(nascimento, data)
    novo = {}

    def tem(k):
        return v.get(k) not in (None, "")

    def pegar(k):
        return v[k] if tem(k) else novo.get(k)

    def por(k, valor):
        # só preenche o que está em branco; o valor exato (sem arredondar) segue para as contas seguintes
        if not tem(k) and valor is not None:
            novo[k] = valor
        return v[k] if tem(k) else valor

    peso, alt = v.get("peso_kg"), v.get("altura_cm")
    if peso and alt:
        m2 = (alt / 100) ** 2
        imc = por("imc", peso / m2)
        por("classificacao_imc", classificar_imc(imc, idade))
        lim = (22, 27) if idade is not None and idade >= 60 else (18.5, 24.9)
        por("peso_ideal", f"{lim[0] * m2:.1f} a {lim[1] * m2:.1f}Kg")

    cin, qua = v.get("circ_cintura"), v.get("circ_quadril")
    if cin and qua:
        rcq = por("rcq", cin / qua)
        if genero in CORTES_RCQ and idade is not None:
            por("risco_rcq", classe(rcq, faixa(CORTES_RCQ[genero], idade), RISCOS_RCQ))

    braco, tri = v.get("braco_relaxado_e"), v.get("dobra_tricipital")
    if braco and tri is not None:
        cmb = por("cmb_cm", braco - math.pi * tri / 10)
        if genero in CMB_P50 and idade is not None and idade >= 13:
            pct = por("cmb_adequacao_pct", cmb / faixa(CMB_P50[genero], idade) * 100)
            por("classificacao_cmb", classificar_cmb(pct))

    d, soma = densidade(v.get("protocolo_dobras"), genero, idade, v)
    por("somatorio_dobras_mm", soma)
    d = por("densidade_corporal", d)
    if d:
        eq = v.get("equacao_gordura") or "siri"
        por("gordura_pct", 495 / d - 450 if eq == "siri" else 457 / d - 414.2)
    gc = pegar("gordura_pct")
    if gc is not None:
        por("classificacao_gordura", classificar_gordura(gc, genero, idade))
        if peso:
            mg = por("massa_gordura_kg", peso * gc / 100)
            por("mlg_kg", peso - mg)
    if peso and genero in ("M", "F"):
        por("massa_residual_kg", peso * (0.241 if genero == "M" else 0.209))
    punho, femur = v.get("diametro_punho"), v.get("diametro_femur")
    if alt and punho and femur:
        por("massa_ossea_kg", 3.02 * ((alt / 100) ** 2 * (punho / 100) * (femur / 100) * 400) ** 0.712)
    mg, mo, mr = pegar("massa_gordura_kg"), pegar("massa_ossea_kg"), pegar("massa_residual_kg")
    if peso and None not in (mg, mo, mr):
        por("massa_muscular_kg", peso - mg - mo - mr)

    if v.get("bia_gordura_pct") is not None:
        por("bia_classificacao_gordura", classificar_gordura(v["bia_gordura_pct"], genero, idade))

    return {k: arredondar(k, x) for k, x in novo.items()}


CASAS = {"rcq": 2, "densidade_corporal": 3}


def arredondar(k, x):
    if isinstance(x, float):
        return round(x, CASAS.get(k, 1))
    return x
