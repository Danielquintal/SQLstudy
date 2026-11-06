"""Lesões do paciente (aba "Lesões" da ficha): lidas do campo "Cirurgias e lesões" da anamnese mais recente e
marcadas num boneco (frente e costas, masculino ou feminino), com a cor da situação.

  - Região: por palavras (ex.: "LCA", "menisco" -> joelho; "entorse" -> tornozelo; "manguito" -> ombro).
  - Lado: "direito/direita/dir", "esquerdo/esquerda/esq", "bilateral/ambos". Sem lado: marca os dois, avisando.
  - Situação: "tratando/fisioterapia/reabilitação" = em tratamento (amarelo); "dor/aguardando cirurgia/aguda" = ativa
    (vermelho); "recuperado/curado/operado/em 2022/há 3 anos" = recuperada (verde); nada dito = não informada (laranja).
Só o campo de lesões é lido: "cãimbra na panturrilha" em Doenças, por exemplo, não vira lesão.
"""
import html
import re
import unicodedata

CAMPO = "cirurgias"

SITUACOES = {   # chave: (rótulo, cor)
    "ativa": ("Ativa / com dor", "#DC2626"),
    "tratamento": ("Em tratamento", "#EAB308"),
    "nao_informada": ("Situação não informada", "#F97316"),
    "recuperada": ("Recuperada / histórico", "#16A34A"),
}
URGENCIA = ["ativa", "tratamento", "nao_informada", "recuperada"]   # quando a mesma região aparece duas vezes

# região: (nome, tem lado, partes do boneco [(vista, parte)], termos)  — termos sem acento, minúsculos
REGIOES = {
    "joelho": ("Joelho", True, [("f", "joelho"), ("c", "joelho")],
               r"joelho|\blca\b|\blcp\b|\blcm\b|\blcl\b|cruzado|menisco|patela|condromalacia|colateral"),
    "tornozelo": ("Tornozelo", True, [("f", "tornozelo"), ("c", "tornozelo")], r"tornozelo|entorse|talofibular|maleolo"),
    "aquiles": ("Tendão de Aquiles", True, [("c", "tornozelo")], r"aquiles|calcaneo"),
    "pe": ("Pé", True, [("f", "pe"), ("c", "pe")], r"\bpes?\b|fascite|plantar|metatars|hallux|joanete"),
    "canela": ("Canela", True, [("f", "perna")], r"canela|canelite|tibia|periostite"),
    "panturrilha": ("Panturrilha", True, [("c", "perna")], r"panturrilha|gastrocnemi|soleo|batata da perna"),
    "coxa_post": ("Posterior da coxa", True, [("c", "coxa")],
                  r"posterior(es)? da coxa|isquiotibia|isquios|biceps femoral|semitendin|semimembran|\bposteriores\b"),
    "coxa_ant": ("Quadríceps", True, [("f", "coxa")], r"quadriceps|reto femoral|coxa anterior|frente da coxa"),
    "coxa": ("Coxa", True, [("f", "coxa"), ("c", "coxa")], r"\bcoxas?\b"),
    "perna": ("Perna", True, [(v, p) for v in "fc" for p in ("coxa", "joelho", "perna", "tornozelo")], r"\bpernas?\b"),
    "virilha": ("Virilha / adutores", True, [("f", "pelve")], r"virilha|adutor|pubalgia|inguinal"),
    "quadril": ("Quadril", True, [("f", "quadril"), ("c", "quadril")], r"quadril|coxofemoral|trocanter"),
    "gluteo": ("Glúteo", True, [("c", "pelve")], r"glute"),
    "lombar": ("Coluna lombar", False, [("c", "lombar")],
               r"lombar|lombalgia|hernia de disco|hernia discal|ciatic|sacro|\bl[345]\b"),
    "costas": ("Costas (torácica)", False, [("c", "costas")], r"costas|dorsal|toracica|escapula|omoplata"),
    "cervical": ("Coluna cervical", False, [("c", "pescoco"), ("f", "pescoco")], r"cervical|pescoco|torcicolo"),
    "ombro": ("Ombro", True, [("f", "ombro"), ("c", "ombro")],
              r"ombro|manguito|supraespinh|infraespinh|clavicula|acromio|deltoide"),
    "cotovelo": ("Cotovelo", True, [("f", "cotovelo"), ("c", "cotovelo")], r"cotovelo|epicondil|olecrano"),
    "punho": ("Punho / antebraço", True, [("f", "antebraco"), ("c", "antebraco")],
              r"punho|antebraco|tunel do carpo|\bcarpo\b|escafoide"),
    "mao": ("Mão / dedos", True, [("f", "mao"), ("c", "mao")], r"\bmaos?\b|dedos? da mao|polegar|falange"),
    "braco": ("Braço", True, [("f", "braco"), ("c", "braco")], r"\bbracos?\b|\bbiceps\b(?! femoral)|triceps|umero"),
    "peito": ("Peitoral / costelas", False, [("f", "peito")], r"peitoral|costela|esterno|torax"),
    "abdomen": ("Abdômen", False, [("f", "abdomen")], r"abdom|umbilical"),
    "cabeca": ("Cabeça", False, [("f", "cabeca"), ("c", "cabeca")], r"cabeca|concuss|craniano|\bface\b|nariz|mandibula"),
}
LESAO = r"les[aã]o|rupt|romp|bursite|tendin|entorse|fratur|luxa|estiramento|distens|contus|cirurgi|operad|hernia|dor\b"
TRATAMENTO = r"tratand|em tratamento|tratamento|fisio|reabilit|em recuperacao|recuperando|acompanhamento|infiltra|" \
             r"aguardando (a )?libera"
ATIVA = r"\bdor\b|\bdoi\b|dores|aguardando (a )?(cirurgia|operar|operacao)|vai operar|agud|recente|inflam|crise|piorou|limitad"
RECUPERADA = r"recuperad|curad|resolvid|cicatriz|sem dor|liberad|antig|ja tratad|\btratou\b|operad|operou|cirurgia|" \
             r"\bem (19|20)\d\d\b|\bha \d+ anos?\b|anos atras|historico|previa"
DIREITO, ESQUERDO, AMBOS = r"direit|\bdir\b", r"esquerd|\besq\b", r"bilateral|ambos|ambas|os dois|as duas"
LETRA = r"^\s*\(?([DE])\b\)?"      # "cotovelo D", "joelho (E)": letra MAIÚSCULA logo depois da região ("e" é conjunção)
PERNA = {"coxa", "joelho", "perna", "tornozelo", "pe", "quadril"}
BRACO = {"ombro", "braco", "cotovelo", "antebraco", "mao"}


def _sem_acento(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _lado(seg, ini, fim, original=""):
    """lado da região achada em seg[ini:fim]: primeiro logo depois do nome, depois logo antes, depois o do trecho"""
    m = re.match(LETRA, original[fim:]) if len(original) == len(seg) else None
    if m:
        return m.group(1).upper()
    for janela in (seg[fim:fim + 30], seg[max(0, ini - 22):ini], seg):
        if re.search(AMBOS, janela):
            return "ambos"
        d, e = bool(re.search(DIREITO, janela)), bool(re.search(ESQUERDO, janela))
        if d != e:
            return "D" if d else "E"
        if d and e and janela is seg:
            return None
    return None


def _situacao(seg):
    if re.search(TRATAMENTO, seg):
        return "tratamento"
    if re.search(ATIVA, seg):
        return "ativa"
    if re.search(RECUPERADA, seg):
        return "recuperada"
    return "nao_informada"


def ler(texto):
    """texto da anamnese -> (lesões [{regiao, nome, lado, situacao, trecho}], trechos sem região identificada)"""
    achadas, sem_regiao = {}, []
    for original in re.split(r"[;\n]+|\.\s+(?=[A-ZÀ-Ú])", str(texto or "")):
        original = original.strip(" .,-")
        if not original:
            continue
        seg, usadas, aqui = _sem_acento(original), [], []
        for rid, (nome, tem_lado, _, termos) in REGIOES.items():
            ms = [m for m in re.finditer(termos, seg) if not any(a <= m.start() < b for a, b in usadas)]
            if not ms:
                continue                     # (ou já coberto por uma região mais específica, ex.: "posterior da coxa")
            usadas += [(m.start(), m.end()) for m in ms]
            lados = [_lado(seg, m.start(), m.end(), original) for m in ms] if tem_lado else []
            aqui.append((rid, next((x for x in lados if x), None)))   # "epicondilite no cotovelo D": vale o D
        if not aqui:
            if re.search(LESAO, seg) and not re.fullmatch(r"(nao|nenhuma?|sem( lesoes?)?|-)", seg.strip()):
                sem_regiao.append(original)
            continue
        sit = _situacao(seg)
        for rid, lado in aqui:
            for l in (["D", "E"] if lado == "ambos" else [lado]):
                k = (rid, l)
                if k not in achadas or URGENCIA.index(sit) < URGENCIA.index(achadas[k]["situacao"]):
                    achadas[k] = {"regiao": rid, "nome": REGIOES[rid][0], "lado": l, "situacao": sit, "trecho": original,
                                  "bilateral": lado == "ambos"}
    ordem = list(REGIOES)
    return sorted(achadas.values(), key=lambda x: (URGENCIA.index(x["situacao"]), ordem.index(x["regiao"]))), sem_regiao


def da_anamnese(dados):
    return ler((dados or {}).get(CAMPO, ""))


# ---------- boneco ----------

def _partes(sexo):
    """{(parte, lado ou None): forma SVG} de um lado do corpo em coordenadas do boneco (0..220 x 0..470), com o
    lado D desenhado à esquerda (vista de frente). A vista de costas espelha."""
    f = sexo == "F"
    S, W, H = (38, 24, 36) if f else (44, 30, 32)        # meia largura de ombros, cintura e quadril
    braco = 14 if f else 17
    cx = 110
    p = {("cabeca", None): f'<ellipse cx="{cx}" cy="36" rx="{17 if f else 18}" ry="22"/>',
         ("pescoco", None): f'<rect x="{cx - 8}" y="55" width="16" height="16" rx="5"/>',
         ("peito", None): f'<path d="M{cx - S + 4} 72 Q{cx} 66 {cx + S - 4} 72 L{cx + W + 2} 128 L{cx - W - 2} 128 Z"/>',
         ("abdomen", None): f'<path d="M{cx - W - 2} 128 L{cx + W + 2} 128 Q{cx + W - 1} 154 {cx + H - 2} 180 L{cx - H + 2} 180 Q{cx - W + 1} 154 {cx - W - 2} 128 Z"/>'}
    p[("costas", None)], p[("lombar", None)] = p[("peito", None)], p[("abdomen", None)]
    for lado, s in (("D", -1), ("E", 1)):
        X = lambda d: cx + s * d
        xa, xc = S + 7, H / 2 + 3                     # centro do braço e da perna
        p[("pelve", lado)] = f'<path d="M{X(H - 2)} 180 L{cx} 180 L{cx} 214 Q{X(H / 2)} 222 {X(H)} 210 Z"/>'
        p[("quadril", lado)] = f'<circle cx="{X(H - 3)}" cy="197" r="9"/>'
        p[("ombro", lado)] = f'<circle cx="{X(S - 3)}" cy="80" r="{12 if f else 13}"/>'
        p[("braco", lado)] = (f'<path d="M{X(xa - braco / 2)} 90 L{X(xa + braco / 2)} 90 L{X(xa + 2 + braco / 2 - 2)} 150 '
                              f'L{X(xa + 2 - braco / 2 + 2)} 150 Z"/>')
        p[("cotovelo", lado)] = f'<circle cx="{X(xa + 3)}" cy="156" r="{7 if f else 8}"/>'
        p[("antebraco", lado)] = (f'<path d="M{X(xa + 3 - braco / 2 + 1)} 162 L{X(xa + 3 + braco / 2 - 1)} 162 '
                                  f'L{X(xa + 6 + 4)} 218 L{X(xa + 6 - 4)} 218 Z"/>')
        p[("mao", lado)] = f'<ellipse cx="{X(xa + 7)}" cy="232" rx="{7 if f else 8}" ry="13"/>'
        p[("coxa", lado)] = (f'<path d="M{X(xc - 15)} 208 L{X(xc + 15)} 206 Q{X(xc + 14)} 250 {X(xc + 11)} 290 '
                             f'L{X(xc - 11)} 290 Q{X(xc - 13)} 250 {X(xc - 15)} 208 Z"/>')
        p[("joelho", lado)] = f'<ellipse cx="{X(xc)}" cy="300" rx="12" ry="13"/>'
        p[("perna", lado)] = (f'<path d="M{X(xc - 10)} 312 Q{X(xc - 13)} 335 {X(xc - 7)} 380 L{X(xc + 7)} 380 '
                              f'Q{X(xc + 13)} 335 {X(xc + 10)} 312 Z"/>')
        p[("tornozelo", lado)] = f'<ellipse cx="{X(xc)}" cy="387" rx="8" ry="6"/>'
        p[("pe", lado)] = f'<ellipse cx="{X(xc + 3)}" cy="402" rx="12" ry="7"/>'
    return p


def _vista(sexo, vista, cores):
    """SVG de uma vista ("f" frente, "c" costas). cores: {(parte, lado): (cor, forte?, título)}"""
    partes = _partes(sexo)
    nomes_f = {"peito": "Peitoral", "abdomen": "Abdômen", "pelve": "Virilha"}
    nomes_c = {"costas": "Costas", "lombar": "Lombar", "pelve": "Glúteo", "perna": "Panturrilha", "pescoco": "Cervical"}
    pular = {"costas", "lombar"} if vista == "f" else {"peito", "abdomen"}
    saida = []
    for (parte, lado), forma in partes.items():
        if parte in pular:
            continue
        cor = cores.get((vista, parte, lado))
        if cor:
            estilo = f'fill="{cor[0]}" fill-opacity="{1 if cor[1] else .32}" stroke="{cor[0]}"'
        else:
            estilo = 'class="base"'
        titulo = cor[2] if cor and cor[1] else ""
        saida.append(forma.replace("/>", f' {estilo}>{f"<title>{html.escape(titulo)}</title>" if titulo else ""}'
                                         f'</{forma[1:forma.index(" ")]}>', 1))
    corpo = "".join(saida)
    if vista == "c":                                   # de costas, o lado direito fica à direita de quem olha
        corpo = f'<g transform="translate(220 0) scale(-1 1)">{corpo}</g>'
    esq, dir_ = ("D", "E") if vista == "f" else ("E", "D")
    return (f'<svg class="boneco" viewBox="0 0 220 440" role="img" aria-label="{"Frente" if vista == "f" else "Costas"}">'
            f'{corpo}<text x="14" y="430" class="lado">{esq}</text><text x="198" y="430" class="lado">{dir_}</text></svg>')


# ---------- boneco realista: imagem anatômica + pontos das articulações (MediaPipe) ----------
# Imagens em sistema/boneco/ (frente_M, costas_M, frente_F, costas_F), enviadas em Configuração. Os pontos (33 da
# pose, x e y de 0 a 1) ficam em sistema/boneco/pontos.json; sem imagem para a vista, vale o boneco desenhado.
from pathlib import Path
import json

PASTA_IMAGENS = Path(__file__).resolve().parent / "boneco"
PARES = {"ombro": (11, 12), "cotovelo": (13, 14), "punho": (15, 16), "quadril": (23, 24), "joelho": (25, 26),
         "tornozelo": (27, 28), "calcanhar": (29, 30), "ponta": (31, 32)}
VISTAS = {"frente_M": "Masculino · frente", "costas_M": "Masculino · costas", "frente_F": "Feminino · frente",
          "costas_F": "Feminino · costas"}


def imagens():
    try:
        return json.loads((PASTA_IMAGENS / "pontos.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def pontos_validos(p):
    """a pose tem os pontos de que o boneco precisa (ombros, quadril, joelhos, tornozelos, cotovelos, punhos)?"""
    return len(p or []) >= 33 and all(p[i][2] >= .3 for i in (11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28))


def _ancoras(info, vista):
    """{(parte, lado): (x, y, rx, ry)} na imagem: onde acender cada região, e os traços dos membros"""
    w, h, p = info["w"], info["h"], info["p"]
    P = lambda i: (p[i][0] * w, p[i][1] * h)
    lado = {}
    for nome, (a, b) in PARES.items():                  # D/E pela posição na imagem (de frente, D fica à esquerda)
        pa, pb = sorted((P(a), P(b)))
        lado[nome] = {"D": pa, "E": pb} if vista == "f" else {"D": pb, "E": pa}
    mid = lambda u, v, t=.5: (u[0] + (v[0] - u[0]) * t, u[1] + (v[1] - u[1]) * t)
    om, qu = mid(lado["ombro"]["D"], lado["ombro"]["E"]), mid(lado["quadril"]["D"], lado["quadril"]["E"])
    larg = abs(lado["ombro"]["D"][0] - lado["ombro"]["E"][0])
    tronco = qu[1] - om[1]
    r = larg * .14
    a = {}
    nariz = P(0)
    a[("cabeca", None)] = (nariz[0], nariz[1] - larg * .12, larg * .3, larg * .36)
    a[("pescoco", None)] = (*mid(nariz, om, .7), larg * .16, larg * .1)
    a[("peito", None)] = (*mid(om, qu, .27), larg * .42, tronco * .2)
    a[("abdomen", None)] = (*mid(om, qu, .7), larg * .32, tronco * .22)
    a[("costas", None)] = (*mid(om, qu, .3), larg * .42, tronco * .22)
    a[("lombar", None)] = (*mid(om, qu, .68), larg * .3, tronco * .15)
    tracos = {}
    for s in ("D", "E"):
        g = lambda n: lado[n][s]
        S, E, W, H, K, A = g("ombro"), g("cotovelo"), g("punho"), g("quadril"), g("joelho"), g("tornozelo")
        pe = g("ponta") if vista == "f" else g("calcanhar")
        fora = 1 if (H[0] - qu[0]) > 0 else -1
        mao = (W[0] + (W[0] - E[0]) * .45, W[1] + (W[1] - E[1]) * .45)
        a[("ombro", s)] = (*S, r * 1.1, r * 1.1)
        a[("braco", s)] = (*mid(S, E), r * .8, r * 1.4)
        a[("cotovelo", s)] = (*E, r * .85, r * .85)
        a[("antebraco", s)] = (*mid(E, W, .65), r * .7, r * 1.2)
        a[("mao", s)] = (*mao, r * .8, r * 1.0)
        a[("quadril", s)] = (H[0] + fora * larg * .12, H[1], r * 1.0, r * 1.0)
        a[("pelve", s)] = (qu[0] + fora * larg * .14, qu[1] + tronco * (.1 if vista == "f" else .05), r * 1.1, r * 1.0)
        a[("coxa", s)] = (*mid(H, K), r * 1.0, (K[1] - H[1]) * .3)
        a[("joelho", s)] = (*K, r * 1.0, r * 1.05)
        a[("perna", s)] = (*mid(K, A, .42), r * .85, (A[1] - K[1]) * .28)
        a[("tornozelo", s)] = (*A, r * .75, r * .6)
        a[("pe", s)] = (*mid(A, pe, .6), r * .9, r * .65)
        tracos[("perna", s)] = [H, K, A, pe]
        tracos[("braco", s)] = [S, E, W, mao]
    return a, tracos, larg


def _formas(info, vista):
    """{(parte, lado): [formas SVG com {c} no lugar da cor]}: a região inteira (coxa, glúteo, ombro...), que depois é
    recortada pelo contorno do corpo (máscara), para a cor seguir o músculo e não sair um círculo"""
    w, h, p = info["w"], info["h"], info["p"]
    P = lambda i: (p[i][0] * w, p[i][1] * h)
    lado = {}
    for nome, (a, b) in PARES.items():
        pa, pb = sorted((P(a), P(b)))
        lado[nome] = {"D": pa, "E": pb} if vista == "f" else {"D": pb, "E": pa}
    mid = lambda u, v, t=.5: (u[0] + (v[0] - u[0]) * t, u[1] + (v[1] - u[1]) * t)
    pt = lambda q: f"{q[0]:.1f},{q[1]:.1f}"
    om, qu = mid(lado["ombro"]["D"], lado["ombro"]["E"]), mid(lado["quadril"]["D"], lado["quadril"]["E"])
    L = abs(lado["ombro"]["D"][0] - lado["ombro"]["E"][0])
    tronco = qu[1] - om[1]
    linha = lambda u, v, larg: (f'<polyline points="{pt(u)} {pt(v)}" fill="none" stroke="{{c}}" stroke-width="{larg:.1f}" '
                                f'stroke-linecap="round"/>')
    circ = lambda q, r: f'<circle cx="{q[0]:.1f}" cy="{q[1]:.1f}" r="{r:.1f}" fill="{{c}}"/>'
    poli = lambda *qs: f'<polygon points="{" ".join(pt(q) for q in qs)}" fill="{{c}}"/>'
    f = {}
    nariz = P(0)
    f[("cabeca", None)] = [f'<ellipse cx="{nariz[0]:.1f}" cy="{nariz[1] - L * .1:.1f}" rx="{L * .34:.1f}" ry="{L * .44:.1f}" fill="{{c}}"/>']
    f[("pescoco", None)] = [linha(mid(nariz, om, .45), om, L * .3)]
    lx = lambda s, k: (qu[0] + (lado["quadril"][s][0] - qu[0]) * k)
    sd, se = lado["ombro"]["D"], lado["ombro"]["E"]
    meio = lambda t: om[1] + tronco * t
    larg_t = lambda t: L * (.5 - .14 * t)                 # meia largura do tronco, afinando para a cintura
    faixa = lambda t0, t1, k=1: poli((om[0] - larg_t(t0) * k, meio(t0)), (om[0] + larg_t(t0) * k, meio(t0)),
                                     (qu[0] + larg_t(t1) * k, meio(t1)), (qu[0] - larg_t(t1) * k, meio(t1)))
    oval = lambda c, rx, ry: f'<ellipse cx="{c[0]:.1f}" cy="{c[1]:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{{c}}"/>'
    f[("peito", None)] = [faixa(.02, .48)]
    f[("abdomen", None)] = [faixa(.48, 1.0, .85)]
    f[("costas", None)] = [oval(mid(om, qu, .3), L * .5, tronco * .3)]
    f[("lombar", None)] = [oval(mid(om, qu, .8), L * .34, tronco * .2)]
    for s in ("D", "E"):
        g = lambda n: lado[n][s]
        S, E, W, H, K, A = g("ombro"), g("cotovelo"), g("punho"), g("quadril"), g("joelho"), g("tornozelo")
        pe = g("ponta") if vista == "f" else g("calcanhar")
        fora = 1 if (H[0] - qu[0]) > 0 else -1
        mao = (W[0] + (W[0] - E[0]) * .5, W[1] + (W[1] - E[1]) * .5)
        coxa = K[1] - H[1]
        f[("ombro", s)] = [circ(S, L * .2)]
        f[("braco", s)] = [linha(mid(S, E, .2), E, L * .36)]
        f[("cotovelo", s)] = [circ(E, L * .15)]
        f[("antebraco", s)] = [linha(E, W, L * .28)]
        f[("mao", s)] = [linha(W, mao, L * .3)]
        f[("quadril", s)] = [circ((H[0] + fora * L * .12, H[1]), L * .2)]
        if vista == "f":   # virilha / adutores: do meio do quadril para dentro da coxa
            f[("pelve", s)] = [poli((qu[0], qu[1] - tronco * .05), (H[0], H[1]), (H[0] + (K[0] - H[0]) * .35, H[1] + coxa * .4),
                                    (qu[0], qu[1] + coxa * .25))]
        else:              # glúteo: oval sobre a nádega, do meio até a lateral do quadril
            f[("pelve", s)] = [oval((H[0] + fora * L * .04, H[1] + coxa * .1), L * .28, coxa * .32)]
        f[("coxa", s)] = [linha(mid(H, K, .12), mid(H, K, .9), L * .58)]
        f[("joelho", s)] = [circ(K, L * .17)]
        f[("perna", s)] = [linha(mid(K, A, .12), mid(K, A, .92), L * .44)]
        f[("tornozelo", s)] = [circ(A, L * .11)]
        f[("pe", s)] = [linha(A, (A[0] + (pe[0] - A[0]) * 1.25, A[1] + (pe[1] - A[1]) * 1.25), L * .26)]
    return f


def _vista_mascara(info, chave, vista, marcas):
    """vista com a região inteira tingida, recortada pelo contorno do corpo (precisa da máscara da imagem)"""
    w, h = info["w"], info["h"]
    formas = _formas(info, vista)
    fortes, claras = [], []
    for (v, parte, lado), (cor, forte, titulo) in marcas.items():
        if v != vista:
            continue
        k = (parte, lado) if (parte, lado) in formas else (parte, None)
        if k not in formas:
            continue
        el = "".join(x.replace("{c}", cor) for x in formas[k])
        (fortes if forte else claras).append((el, titulo))
    mid = f"mc-{chave}"
    claro = "".join(e for e, _ in claras)
    forte = "".join(e for e, _ in fortes)
    titulos = "".join(f"<title>{html.escape(t)}</title>" for _, t in fortes[:1])
    esq, dir_ = ("D", "E") if vista == "f" else ("E", "D")
    return (f'<svg class="boneco real" viewBox="0 0 {w} {h}" role="img" aria-label="{"Frente" if vista == "f" else "Costas"}">'
            f'{titulos}<defs><mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" width="{w}" height="{h}">'
            f'<image href="/boneco/{info["mascara"]}" width="{w}" height="{h}" preserveAspectRatio="none"/></mask></defs>'
            f'<image href="/boneco/{info["arquivo"]}" width="{w}" height="{h}"/>'
            # tom claro no membro todo, depois a região: "color" tinge mantendo o desenho dos músculos, e uma camada
            # leve por cima dá a intensidade
            # (a máscara vai em cada camada: num grupo em volta, ele isolaria a mistura e a cor sairia chapada)
            f'<g mask="url(#{mid})" style="mix-blend-mode:color" opacity=".35">{claro}</g>'
            f'<g mask="url(#{mid})" style="mix-blend-mode:color">{forte}</g>'
            f'<g mask="url(#{mid})" style="mix-blend-mode:multiply" opacity=".35">{forte}</g>'
            f'<g mask="url(#{mid})" opacity=".12">{forte}</g>'
            f'<text x="{w * .04:.0f}" y="{h * .98:.0f}" class="lado" font-size="{h * .035:.0f}">{esq}</text>'
            f'<text x="{w * .96:.0f}" y="{h * .98:.0f}" class="lado" text-anchor="end" font-size="{h * .035:.0f}">{dir_}</text></svg>')


def _vista_real(sexo, vista, marcas):
    """SVG da imagem anatômica com as lesões acesas; None se não houver imagem para esta vista"""
    chave = ("frente_" if vista == "f" else "costas_") + ("F" if sexo == "F" else "M")
    info = imagens().get(chave)
    if not info or not (PASTA_IMAGENS / info["arquivo"]).exists() or not pontos_validos(info["p"]):
        return None
    if info.get("mascara") and (PASTA_IMAGENS / info["mascara"]).exists():
        return _vista_mascara(info, chave, vista, marcas)
    a, tracos, larg = _ancoras(info, vista)
    w, h = info["w"], info["h"]
    grad, camadas, membros = {}, [], []
    for (v, parte, lado), (cor, forte, titulo) in marcas.items():
        if v != vista:
            continue
        if not forte:                                    # tom claro: traço largo ao longo do membro
            m = ("perna" if parte in PERNA else "braco" if parte in BRACO else None, lado)
            if m[0] and m in tracos and m not in [x[0] for x in membros]:
                membros.append((m, cor))
            continue
        k = (parte, lado) if (parte, lado) in a else (parte, None)
        if k not in a:
            continue
        x, y, rx, ry = a[k]
        gid = grad.setdefault(cor, f"g{len(grad)}")
        camadas.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx * 1.35:.1f}" ry="{ry * 1.35:.1f}" fill="url(#{gid})"/>'
                       f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{cor}" fill-opacity=".45" '
                       f'stroke="{cor}" stroke-width="{max(1.5, larg * .012):.1f}"><title>{html.escape(titulo)}</title></ellipse>')
    defs = "".join(f'<radialGradient id="{g}"><stop offset="0" stop-color="{c}" stop-opacity=".75"/>'
                   f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient>' for c, g in grad.items())
    linhas = "".join(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in tracos[m])}" fill="none" stroke="{cor}" '
                     f'stroke-opacity=".28" stroke-width="{larg * .2:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
                     for m, cor in membros)
    esq, dir_ = ("D", "E") if vista == "f" else ("E", "D")
    return (f'<svg class="boneco real" viewBox="0 0 {w} {h}" role="img" aria-label="{"Frente" if vista == "f" else "Costas"}">'
            f'<defs>{defs}</defs><image href="/boneco/{info["arquivo"]}" width="{w}" height="{h}"/>{linhas}{"".join(camadas)}'
            f'<text x="{w * .04:.0f}" y="{h * .98:.0f}" class="lado" font-size="{h * .035:.0f}">{esq}</text>'
            f'<text x="{w * .96:.0f}" y="{h * .98:.0f}" class="lado" text-anchor="end" font-size="{h * .035:.0f}">{dir_}</text></svg>')


def para_pagina(cur, pid, genero):
    """bloco Lesões da página do paciente: só região, lado e situação (o texto da anamnese é do profissional e fica
    de fora) e o boneco com as imagens embutidas (a página publicada não tem acesso às imagens deste computador).
    None se não houver lesão anotada."""
    import base64
    cur.execute("""SELECT a.dados FROM anamnese a JOIN avaliacao v ON v.id = a.avaliacao_id
                   WHERE a.paciente_id = %s ORDER BY v.data_avaliacao DESC LIMIT 1""", (pid,))
    r = cur.fetchone()
    lista, _ = da_anamnese(r[0] if r else None)
    if not lista:
        return None
    frente, costas = boneco(genero, lista)
    for info in imagens().values():                        # /boneco/arquivo -> data:image/... (dentro da página)
        for nome in (info.get("arquivo"), info.get("mascara")):
            if nome and f'/boneco/{nome}"' in frente + costas and (PASTA_IMAGENS / nome).exists():
                tipo = "image/png" if nome.endswith(".png") else "image/jpeg"
                dado = f'data:{tipo};base64,{base64.b64encode((PASTA_IMAGENS / nome).read_bytes()).decode()}"'
                frente, costas = (x.replace(f'/boneco/{nome}"', dado) for x in (frente, costas))
    lado = {"D": "Direito", "E": "Esquerdo"}
    return {"frente": frente, "costas": costas,
            "legenda": [[rot, cor] for rot, cor in SITUACOES.values()],
            "lista": [{"nome": l["nome"], "lado": lado.get(l["lado"], "—"), "situacao": SITUACOES[l["situacao"]][0],
                       "cor": SITUACOES[l["situacao"]][1]} for l in lista]}


def boneco(sexo, lesoes):
    """duas vistas (frente e costas) com as lesões pintadas; o membro inteiro leva a cor mais clara.
    Com imagem anatômica para a vista (Configuração), usa a imagem; senão, o boneco desenhado."""
    cores = {}
    for l in sorted(lesoes, key=lambda x: -URGENCIA.index(x["situacao"])):   # as mais urgentes pintam por cima
        cor = SITUACOES[l["situacao"]][1]
        titulo = f'{l["nome"]}{" " + {"D": "direito", "E": "esquerdo"}[l["lado"]] if l["lado"] else ""}: {SITUACOES[l["situacao"]][0]}'
        lados = [l["lado"]] if l["lado"] else ["D", "E"]
        for vista, parte in REGIOES[l["regiao"]][2]:
            tem_lado = parte not in ("cabeca", "pescoco", "peito", "abdomen", "costas", "lombar")
            for lado in (lados if tem_lado else [None]):
                membro = PERNA if parte in PERNA else BRACO if parte in BRACO else set()
                for outra in membro:                       # tom claro no membro todo
                    for v in "fc":
                        cores.setdefault((v, outra, lado), (cor, False, ""))
                cores[(vista, parte, lado)] = (cor, True, titulo)
    return (_vista_real(sexo, "f", cores) or _vista(sexo, "f", cores),
            _vista_real(sexo, "c", cores) or _vista(sexo, "c", cores))
