"""Cálculos da avaliação antropométrica, iguais aos do App Naive (conferidos com as 1297 avaliações do banco).

calcular(valores, genero, nascimento, data, passos=None) devolve o que dá para calcular com o que foi medido
(e, se receber a lista passos, anota em cada conta a fórmula com os números usados, para mostrar na tela):
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


NOMES_DOBRAS = {"dobra_toracica": "torácica", "dobra_axilar_media": "axilar média", "dobra_tricipital": "tricipital",
                "dobra_subescapular": "subescapular", "dobra_abdominal": "abdominal", "dobra_suprailiaca": "suprailíaca",
                "dobra_coxa": "coxa"}
SEXO = {"M": "homem", "F": "mulher"}


def br(x, casas=1):
    """número no jeito brasileiro: 1234.5 -> 1.234,5"""
    if x is None:
        return "–"
    s = f"{x:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return s[:-2] if casas == 1 and s.endswith(",0") else s     # 81,0 -> 81


def faixa_idade(tabela, idade):
    """texto da faixa de idade da tabela: "26 a 35 anos" """
    ant = None
    for ate, _ in tabela:
        if idade <= ate:
            if ant is None:
                return f"até {ate} anos"
            return f"{ant + 1} a {ate} anos" if ate < 999 else f"{ant + 1} anos ou mais"
        ant = ate


NOME_PROTOCOLO = {"pollock7": "Pollock 7 dobras", "pollock3": "Pollock 3 dobras", "guedes": "Guedes"}
COEF_POLLOCK = {("pollock7", "M"): (1.112, 0.00043499, 0.00000055, 0.00028826),      # Jackson & Pollock, 1978
                ("pollock7", "F"): (1.097, 0.00046971, 0.00000056, 0.00012828),      # Jackson, Pollock & Ward, 1980
                ("pollock3", "M"): (1.10938, 0.0008267, 0.0000016, 0.0002574),
                ("pollock3", "F"): (1.0994921, 0.0009929, 0.0000023, 0.0001392)}


def dobras_do_protocolo(prot, genero):
    """dobras que entram no protocolo (Pollock 3 e Guedes mudam com o sexo)"""
    if prot == "pollock7":
        return POLLOCK7
    return {"pollock3": POLLOCK3, "guedes": GUEDES}.get(prot, {}).get(genero, [])


def formula_densidade(prot, genero):
    """(fórmula escrita, função que monta a conta com o somatório e a idade)"""
    if prot == "guedes":
        a, b = (1.1714, 0.0671) if genero == "M" else (1.1665, 0.0706)
        return (f"{br(a, 4)} − {br(b, 4)} × log₁₀(S)   (S = somatório das dobras)",
                lambda S, idade: f"{br(a, 4)} − {br(b, 4)} × log₁₀({S})")
    k = COEF_POLLOCK[(prot, genero)]
    n = lambda x: f"{x:.8f}".rstrip("0").replace(".", ",")
    return (f"{n(k[0])} − {n(k[1])} × S + {n(k[2])} × S² − {n(k[3])} × idade   (S = somatório das dobras)",
            lambda S, idade: f"{n(k[0])} − {n(k[1])} × {S} + {n(k[2])} × {S}² − {n(k[3])} × {idade}")


def juntar(itens):
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def calcular(v, genero, nascimento, data, passos=None):
    """v: valores do formulário (números já convertidos, None = em branco). Devolve só o que calculou."""
    idade = idade_em(nascimento, data)
    novo = {}

    def anotar(campo, titulo, formula, conta, resultado, regra=None):
        if passos is not None:
            passos.append({"campo": campo, "titulo": titulo, "formula": formula, "conta": conta, "resultado": resultado,
                           "regra": regra, "digitado": v.get(campo) not in (None, "")})

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
        anotar("imc", "IMC", "peso (kg) ÷ altura (m)²", f"{br(peso)} ÷ {br(alt / 100, 2)}²", f"{br(imc)} kg/m²")
        cl = por("classificacao_imc", classificar_imc(imc, idade))
        idoso = idade is not None and idade >= 60
        anotar("classificacao_imc", "Classificação do IMC",
               "Lipschitz (60 anos ou mais)" if idoso else "OMS (adultos)",
               "< 22 baixo peso · 22 a 27 adequado · > 27 sobrepeso" if idoso else
               "< 18,5 baixo peso · 18,5 a 24,9 eutrófico · 25 a 29,9 sobrepeso · 30 a 34,9 obesidade I · "
               "35 a 39,9 obesidade II · ≥ 40 obesidade III", cl)
        lim = (22, 27) if idade is not None and idade >= 60 else (18.5, 24.9)
        por("peso_ideal", f"{lim[0] * m2:.1f} a {lim[1] * m2:.1f}Kg")
        anotar("peso_ideal", "Faixa de peso ideal", f"IMC {br(lim[0])} e {br(lim[1])} × altura (m)²",
               f"{br(lim[0])} × {br(alt / 100, 2)}² a {br(lim[1])} × {br(alt / 100, 2)}²",
               f"{br(lim[0] * m2)} a {br(lim[1] * m2)} kg")

    cin, qua = v.get("circ_cintura"), v.get("circ_quadril")
    if cin and qua:
        rcq = por("rcq", cin / qua)
        anotar("rcq", "Relação cintura/quadril (RCQ)", "cintura (cm) ÷ quadril (cm)", f"{br(cin)} ÷ {br(qua)}", br(rcq, 2))
        if genero in CORTES_RCQ and idade is not None:
            cortes = faixa(CORTES_RCQ[genero], idade)
            r = por("risco_rcq", classe(rcq, cortes, RISCOS_RCQ))
            anotar("risco_rcq", "Risco pela RCQ", f"Bray, {SEXO[genero]}, {faixa_idade(CORTES_RCQ[genero], idade)}",
                   f"< {br(cortes[0], 2)} baixo · até {br(cortes[1], 2)} moderado · até {br(cortes[2], 2)} alto · acima muito alto", r)

    braco, tri = v.get("braco_relaxado_e"), v.get("dobra_tricipital")
    if braco and tri is not None:
        cmb = por("cmb_cm", braco - math.pi * tri / 10)
        anotar("cmb_cm", "Circunferência muscular do braço (CMB)", "braço relaxado (cm) − π × dobra tricipital (mm) ÷ 10",
               f"{br(braco)} − 3,1416 × {br(tri)} ÷ 10", f"{br(cmb)} cm")
        if genero in CMB_P50 and idade is not None and idade >= 13:
            p50 = faixa(CMB_P50[genero], idade)
            pct = por("cmb_adequacao_pct", cmb / p50 * 100)
            anotar("cmb_adequacao_pct", "Adequação da CMB",
                   f"CMB ÷ percentil 50 (Frisancho, {SEXO[genero]}, {faixa_idade(CMB_P50[genero], idade)}) × 100",
                   f"{br(cmb)} ÷ {br(p50)} × 100", f"{br(pct)}%")
            c = por("classificacao_cmb", classificar_cmb(pct))
            anotar("classificacao_cmb", "Classificação da CMB", "Blackburn",
                   "< 70% desnutrição grave · 70 a 79% moderada · 80 a 89% leve · ≥ 90% eutrófico", c)

    prot = v.get("protocolo_dobras")
    d, soma = densidade(prot, genero, idade, v)
    por("somatorio_dobras_mm", soma)
    chaves = dobras_do_protocolo(prot, genero)
    if soma is not None and chaves:
        anotar("somatorio_dobras_mm", f"Somatório das dobras ({NOME_PROTOCOLO[prot]})",
               " + ".join(NOMES_DOBRAS[k] for k in chaves), " + ".join(br(v[k]) for k in chaves), f"{br(soma)} mm")
    d = por("densidade_corporal", d)
    eq = v.get("equacao_gordura") or "siri"
    nome_eq, f_gc = ("Siri", "495 ÷ densidade − 450") if eq == "siri" else ("Brozek", "457 ÷ densidade − 414,2")
    if prot in NOME_PROTOCOLO:
        if genero not in ("M", "F"):
            anotar("densidade_corporal", f"Densidade corporal ({NOME_PROTOCOLO[prot]})",
                   "a equação muda com o sexo", "Falta o sexo no cadastro do paciente", "–")
        else:
            titulo = f"Densidade corporal ({NOME_PROTOCOLO[prot]}, {SEXO[genero]})"
            formula, conta = formula_densidade(prot, genero)
            if d and soma is not None:
                anotar("densidade_corporal", titulo, formula, conta(br(soma), idade), br(d, 4))
            elif not tem("densidade_corporal"):
                faltam = [NOMES_DOBRAS[k] for k in chaves if v.get(k) is None]
                motivo = (f"Faltam as dobras: {juntar(faltam)}" if faltam
                          else "Falta a idade (data de nascimento no cadastro)" if idade is None else "")
                anotar("densidade_corporal", titulo, formula, motivo, "–")
    if d:
        gc_calc = por("gordura_pct", 495 / d - 450 if eq == "siri" else 457 / d - 414.2)
        anotar("gordura_pct", f"% de gordura ({nome_eq})", f_gc,
               f"495 ÷ {br(d, 4)} − 450" if eq == "siri" else f"457 ÷ {br(d, 4)} − 414,2", f"{br(gc_calc)}%")
    elif prot in NOME_PROTOCOLO and not tem("gordura_pct"):
        anotar("gordura_pct", f"% de gordura ({nome_eq})", f_gc, "Aguarda a densidade corporal", "–")
    gc = pegar("gordura_pct")
    if gc is not None:
        cg = por("classificacao_gordura", classificar_gordura(gc, genero, idade))
        if genero in CORTES_GORDURA and idade is not None and idade >= IDADE_MINIMA_GORDURA:
            ct = faixa(CORTES_GORDURA[genero], idade)
            anotar("classificacao_gordura", "Classificação do % de gordura",
                   f"{SEXO[genero]}, {faixa_idade(CORTES_GORDURA[genero], idade)}",
                   " · ".join(f"{'< ' + br(ct[0], 1) if i == 0 else br(ct[i - 1], 1) + ' a ' + br(ct[i], 1) if i < len(ct) else '≥ ' + br(ct[-1], 1)} {n_.lower()}"
                              for i, n_ in enumerate(CLASSES_GORDURA)), cg)
        if peso:
            mg = por("massa_gordura_kg", peso * gc / 100)
            anotar("massa_gordura_kg", "Massa de gordura", "peso × % de gordura ÷ 100", f"{br(peso)} × {br(gc)} ÷ 100", f"{br(mg)} kg")
            mlg = por("mlg_kg", peso - mg)
            anotar("mlg_kg", "Massa livre de gordura", "peso − massa de gordura", f"{br(peso)} − {br(mg)}", f"{br(mlg)} kg")
    if peso and genero in ("M", "F"):
        fr = 0.241 if genero == "M" else 0.209
        mres = por("massa_residual_kg", peso * fr)
        anotar("massa_residual_kg", "Massa residual (Würch)", f"peso × {br(fr, 3)} ({SEXO[genero]})", f"{br(peso)} × {br(fr, 3)}", f"{br(mres)} kg")
    punho, femur = v.get("diametro_punho"), v.get("diametro_femur")
    if alt and punho and femur:
        mos = por("massa_ossea_kg", 3.02 * ((alt / 100) ** 2 * (punho / 100) * (femur / 100) * 400) ** 0.712)
        anotar("massa_ossea_kg", "Massa óssea (Von Döbeln, modificada por Rocha)",
               "3,02 × (altura² × diâmetro do punho × diâmetro do fêmur × 400)^0,712, medidas em metros",
               f"3,02 × ({br(alt / 100, 2)}² × {br(punho / 100, 3)} × {br(femur / 100, 3)} × 400)^0,712", f"{br(mos)} kg")
    mg, mo, mr = pegar("massa_gordura_kg"), pegar("massa_ossea_kg"), pegar("massa_residual_kg")
    if peso and None not in (mg, mo, mr):
        mm = por("massa_muscular_kg", peso - mg - mo - mr)
        anotar("massa_muscular_kg", "Massa muscular", "peso − massa de gordura − massa óssea − massa residual",
               f"{br(peso)} − {br(mg)} − {br(mo)} − {br(mr)}", f"{br(mm)} kg")

    if v.get("bia_gordura_pct") is not None:
        cb = por("bia_classificacao_gordura", classificar_gordura(v["bia_gordura_pct"], genero, idade))
        anotar("bia_classificacao_gordura", "Classificação do % de gordura (bioimpedância)",
               "mesma tabela do % de gordura por dobras", f"{br(v['bia_gordura_pct'])}%", cb)

    return {k: arredondar(k, x) for k, x in novo.items()}


CASAS = {"rcq": 2, "densidade_corporal": 3}


def arredondar(k, x):
    if isinstance(x, float):
        return round(x, CASAS.get(k, 1))
    return x
