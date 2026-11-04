"""Check-in semanal: busca as respostas do Formulário Google (pelo script sistema/checkin_google.gs) e grava no banco.

O paciente recebe pelo WhatsApp (ou por e-mail, enviado pelo próprio script do Google) um link do formulário com o nome
dele já preenchido; a resposta é ligada ao paciente pelo nome. Quando o nome não bate com ninguém (ou bate com dois),
a resposta fica na tela Check-ins para você escolher.
"""
import json, re, time, unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from psycopg.types.json import Jsonb

SCRIPT = Path(__file__).resolve().parent / "checkin_google.gs"
NUMEROS = {"peso_kg", "cintura_cm"}
ESCALAS = {"adesao", "fome", "sono", "energia", "treino_sensacao"}
TEXTOS = {"nome_informado", "dificuldades", "intestino", "agua", "comentario"}
COLUNAS = ["peso_kg", "cintura_cm", "adesao", "dificuldades", "fome", "sono", "energia", "intestino", "agua",
           "treinos", "treino_sensacao", "comentario"]
CAMPOS_CHECKIN = ["id", "paciente_id", "nome", "respondido_em", "nome_informado"] + COLUNAS
# alerta quando a nota (1 a 5) fica nisto ou abaixo
NOTAS_BAIXAS = {"adesao": "seguiu pouco o plano", "fome": "muita fome", "sono": "sono ruim", "energia": "pouca energia"}

_ultima_busca = 0.0
aviso_email = None   # último problema do e-mail automático, mostrado na tela Check-ins
VERSAO_SCRIPT = 2    # versão do checkin_google.gs que tem o e-mail automático

# pacientes que recebem o pedido de check-in: consulta nos últimos N dias ou retorno marcado, sem pausa nem bloqueio
ATIVOS = """NOT p.whatsapp_bloqueado AND NOT p.checkin_pausado
    AND (p.retorno_em >= %(hoje)s OR EXISTS (SELECT 1 FROM avaliacao a WHERE a.paciente_id = p.id
                                             AND a.data_avaliacao >= %(desde)s))"""


class ErroGoogle(Exception):
    pass


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def configurado(cfg):
    c = cfg.get("checkin", {})
    return bool(c.get("url") and c.get("chave") and c.get("formulario"))


def link_formulario(cfg, nome):
    """link do formulário com o nome do paciente já preenchido"""
    c = cfg.get("checkin", {})
    if not c.get("formulario"):
        return None
    return c["formulario"].replace(c.get("marca") or "NOME_DO_PACIENTE", quote(nome.strip()))


def email_valido(e):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", (e or "").strip()))


def usa_email(cfg):
    c = cfg.get("checkin", {})
    return configurado(cfg) and bool(c.get("email_ativo")) and int(c.get("versao") or 0) >= VERSAO_SCRIPT


def link_paciente(cur, cfg, pid, nome):
    """link do check-in para a aba da página do paciente; nenhum com o check-in desligado ou pausado para ele"""
    if not configurado(cfg):
        return None
    cur.execute("SELECT checkin_pausado FROM paciente WHERE id = %s", (pid,))
    r = cur.fetchone()
    return None if not r or r[0] else link_formulario(cfg, nome)


def limpar_chave(texto):
    """a chave são 32 letras/números; tira o que vier junto ao copiar do registro (ex.: "CHAVE (cole no sistema): ...")"""
    m = re.search(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", texto or "", re.I)
    return m.group().lower() if m else (texto or "").strip()


def _chamar(url, chave, **params):
    try:
        with urlopen(f"{url}?{urlencode(dict(chave=chave, **params))}", timeout=20) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise ErroGoogle(f"Não consegui falar com o script do Google ({e}). Confira a URL e a internet.")
    return _resposta(dados)


def _postar(url, corpo):
    # o Google responde ao POST com um redirecionamento; o urlopen segue com GET, que é o que o Google espera
    req = Request(url, data=json.dumps(corpo).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise ErroGoogle(f"Não consegui mandar a lista de e-mails ao script do Google ({e}). "
                         "Se você ainda não atualizou o código do script, veja Configuração > Check-in.")
    return _resposta(dados)


def _resposta(dados):
    if dados.get("erro") == "chave":
        raise ErroGoogle("O script do Google recusou a chave. A chave tem 32 letras e números e precisa ser do mesmo "
                         "projeto da URL: abra o projeto que você implantou, rode a função mostrar e copie a chave "
                         "que aparece no registro.")
    return dados


def info(url, chave):
    """título e link do formulário, versão do script e estado do e-mail automático"""
    return _chamar(url, chave, acao="info")


def testar(url, chave):
    """confere a URL e a chave; devolve o link do formulário e quantas respostas ele já tem"""
    url = url.strip()
    if not re.match(r"https://script\.google(usercontent)?\.com/", url):
        raise ErroGoogle("A URL deve ser a do app da Web, começando com https://script.google.com/")
    d = info(url, chave.strip())
    if not d.get("link"):
        raise ErroGoogle("O script respondeu, mas sem o link do formulário. Rode a função criar de novo.")
    return d


def _numero(v):
    m = re.search(r"\d+(?:[.,]\d+)?", str(v or ""))
    return float(m.group().replace(",", ".")) if m else None


def _converter(itens):
    linha = {"nome_informado": (itens.get("nome") or "").strip() or None}
    for c in COLUNAS:
        v = itens.get(c)
        if isinstance(v, list):
            v = ", ".join(map(str, v))
        if v in (None, ""):
            linha[c] = None
        elif c in NUMEROS:
            linha[c] = _numero(v)
        elif c in ESCALAS or c == "treinos":
            n = _numero(v)
            linha[c] = int(n) if n is not None else None
        else:
            linha[c] = str(v).strip()
    # peso digitado em gramas (72500) ou com erro grosseiro não entra como número
    if linha["peso_kg"] is not None and not 20 <= linha["peso_kg"] <= 400:
        linha["peso_kg"] = None
    if linha["cintura_cm"] is not None and not 30 <= linha["cintura_cm"] <= 250:
        linha["cintura_cm"] = None
    return linha


def _achar_paciente(cur, nome):
    if not nome:
        return None
    cur.execute("SELECT id, nome FROM paciente")
    achados = [i for i, n in cur.fetchall() if norm(n) == norm(nome)]
    return achados[0] if len(achados) == 1 else None


def sincronizar(cur, cfg):
    """busca as respostas novas; devolve (novas, sem_paciente)"""
    global _ultima_busca
    c = cfg.get("checkin", {})
    if not (c.get("url") and c.get("chave")):
        raise ErroGoogle("O check-in ainda não foi ligado ao Google. Veja Configuração > Check-in.")
    cur.execute("SELECT max(respondido_em) FROM checkin")   # inclui as excluídas: o google_id delas impede que voltem
    ultimo = cur.fetchone()[0]
    # um dia de folga para trás: respostas repetidas são puladas pelo google_id
    desde = (ultimo - timedelta(days=1)).astimezone().isoformat() if ultimo else None
    dados = _chamar(c["url"], c["chave"], **({"desde": desde} if desde else {}))
    _ultima_busca = time.time()
    novas = sem = 0
    for r in dados.get("respostas", []):
        linha = _converter(r.get("itens", {}))
        quando = datetime.fromisoformat(r["quando"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        pid = _achar_paciente(cur, linha["nome_informado"])
        cols = ["google_id", "paciente_id", "respondido_em", "nome_informado"] + COLUNAS + ["respostas"]
        vals = [r["id"], pid, quando, linha["nome_informado"]] + [linha[k] for k in COLUNAS] + [Jsonb(r)]
        cur.execute(f"INSERT INTO checkin ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                    "ON CONFLICT (google_id) DO NOTHING", vals)
        if cur.rowcount:
            novas += 1
            sem += pid is None
    atualizar_emails(cur, cfg)
    return novas, sem


def enviar_lista(cur, cfg, hoje=None):
    """manda ao script quem recebe o e-mail e o texto; com o e-mail desligado, manda a lista vazia (o script para de enviar).
    Devolve (pacientes na lista, estado do e-mail no Google)."""
    c = cfg["checkin"]
    hoje = hoje or datetime.now().date()
    lista = []
    if usa_email(cfg):
        cur.execute(f"SELECT p.id, p.nome, p.email FROM paciente p WHERE {ATIVOS} ORDER BY p.nome",
                    {"hoje": hoje, "desde": hoje - timedelta(days=int(c.get("ativo_dias", 90)))})
        lista = [{"id": i, "nome": n, "email": e.strip()} for i, n, e in cur.fetchall() if email_valido(e)]
    config = {"ativo": usa_email(cfg), "dias": int(c.get("dias", 7)), "assunto": c.get("email_assunto", ""),
              "texto": c.get("email_texto", ""), "remetente": c.get("email_remetente", "")}
    r = _postar(c["url"], {"chave": c["chave"], "acao": "pacientes", "lista": lista, "config": config})
    return len(lista), r.get("emails", {})


def registrar_envios(cur, estado):
    """grava os e-mails enviados pelo script como contatos (tipo checkin_email), sem repetir"""
    n = 0
    for e in estado.get("envios", []):
        if e.get("erro"):
            continue
        quando = datetime.fromisoformat(e["quando"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        cur.execute("""INSERT INTO contato (paciente_id, tipo, referencia, feito_em)
                       SELECT %s, 'checkin_email', %s, %s WHERE EXISTS (SELECT 1 FROM paciente WHERE id = %s)
                         AND NOT EXISTS (SELECT 1 FROM contato WHERE paciente_id = %s AND tipo = 'checkin_email'
                                         AND referencia = %s)""",
                    (e["id"], e["quando"], quando, e["id"], e["id"], e["quando"]))
        n += cur.rowcount
    return n


def atualizar_emails(cur, cfg):
    """lista para o script e envios de volta; problemas ficam em aviso_email, sem atrapalhar as respostas"""
    global aviso_email
    if int(cfg["checkin"].get("versao") or 0) < VERSAO_SCRIPT:
        return
    try:
        _, estado = enviar_lista(cur, cfg)
        registrar_envios(cur, estado)
        erros = [e for e in estado.get("envios", [])[:10] if e.get("erro")]
        aviso_email = (f"O Google não conseguiu enviar {len(erros)} e-mail(s) recentes: {erros[0]['erro']}" if erros
                       else None if not usa_email(cfg) or estado.get("gatilho")
                       else "O e-mail automático está ligado aqui, mas falta rodar a função ativarEmails no script do Google.")
    except ErroGoogle as e:
        aviso_email = str(e)


def sincronizar_se_preciso(con, cfg, minutos=10):
    """busca sozinho ao abrir as telas, no máximo a cada N minutos; falha em silêncio (a tela Check-ins mostra o erro)"""
    if not configurado(cfg) or time.time() - _ultima_busca < minutos * 60:
        return None
    try:
        r = sincronizar(con.cursor(), cfg)
        con.commit()
        return r
    except ErroGoogle:
        globals()["_ultima_busca"] = time.time()   # não tenta de novo a cada clique
        return None


def lista(cur, onde, args, limite):
    cur.execute(f"""SELECT k.id, k.paciente_id, p.nome, k.respondido_em, k.nome_informado, {', '.join('k.' + c for c in COLUNAS)}
                    FROM checkin k LEFT JOIN paciente p ON p.id = k.paciente_id
                    WHERE NOT k.excluido AND {onde} ORDER BY k.respondido_em DESC LIMIT {int(limite)}""", args)
    return [dict(zip(CAMPOS_CHECKIN, r)) for r in cur.fetchall()]


def com_alertas(checkins):
    """acrescenta a variação de peso desde o check-in anterior e os alertas de cada resposta (lista do mais novo ao mais antigo)"""
    for i, k in enumerate(checkins):
        anterior = next((o for o in checkins[i + 1:] if o["peso_kg"] is not None and o["paciente_id"] == k["paciente_id"]), None)
        k["var_peso"] = float(k["peso_kg"] - anterior["peso_kg"]) if k["peso_kg"] is not None and anterior else None
        alertas = [txt for c, txt in NOTAS_BAIXAS.items() if k[c] is not None and k[c] <= 2]
        if k["intestino"] and not k["intestino"].lower().startswith("normal"):
            alertas.append("intestino " + k["intestino"].split(" (")[0].lower())
        if k["agua"] and k["agua"].lower().startswith("menos"):
            alertas.append("pouca água")
        if k["var_peso"] is not None and abs(k["var_peso"]) >= 1.5:
            alertas.append(f"peso {'+' if k['var_peso'] > 0 else '−'}{abs(k['var_peso']):.1f} kg".replace(".", ","))
        k["alertas"] = alertas
    return checkins


def grafico_peso(checkins, largura=600, altura=140):
    """pontos do gráfico de peso (SVG) dos check-ins, do mais antigo ao mais novo"""
    pts = [(k["respondido_em"], float(k["peso_kg"])) for k in reversed(checkins) if k["peso_kg"] is not None]
    if len(pts) < 2:
        return None
    lo, hi = min(p for _, p in pts), max(p for _, p in pts)
    if hi - lo < 1:
        lo, hi = lo - 0.5, hi + 0.5
    m = 28
    xs = [m + i * (largura - 2 * m) / (len(pts) - 1) for i in range(len(pts))]
    ys = [altura - 24 - (p - lo) / (hi - lo) * (altura - 52) for _, p in pts]
    return {"largura": largura, "altura": altura, "linha": " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys)),
            "pontos": [{"x": x, "y": y, "peso": p, "data": d} for x, y, (d, p) in zip(xs, ys, pts)]}
