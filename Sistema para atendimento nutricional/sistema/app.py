"""Sistema local: pacientes e avaliações no navegador, gravando direto no banco de dados.

Uso:  python sistema/app.py   (ou dois cliques em "Abrir sistema.bat")  ->  http://localhost:5000
Só atende este computador (127.0.0.1). Depois de gravar uma avaliação, gera de novo a planilha e a página do paciente.
"""
import base64, json, os, shutil, sys, webbrowser
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlparse

import psycopg
from flask import Flask, abort, flash, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from atualizar_paciente import (CONEXAO, PAGINAS, TEMPLATE, achar_planilha, avaliacoes_do_banco, converter,
                                mostrar, norm, para_pagina)
from calculos import calcular
from campos import CAMPOS, TEXTO
from montar_pagina import gerar_html, montar
from planilha_paciente import SECTIONS, build, safe_name
import agenda
import checkin
import reds
import exames
import perfil as antropo
import contatos
import links
import plano as planos
import plano_pdf
import nutricao

PORTA = 5000
COLUNA = {v: k for k, v in CAMPOS.items()}
# seções do formulário: [(título, [(coluna, rótulo), ...])], na mesma ordem da planilha
SECOES = [(titulo, [(COLUNA[chave], rotulo) for rotulo, chave in itens]) for titulo, itens in SECTIONS]
# campos que o sistema calcula sozinho (scripts/calculos.py)
CALCULADOS = {"imc", "classificacao_imc", "peso_ideal", "rcq", "risco_rcq", "cmb_cm", "cmb_adequacao_pct",
              "classificacao_cmb", "somatorio_dobras_mm", "densidade_corporal", "gordura_pct",
              "classificacao_gordura", "massa_gordura_kg", "mlg_kg", "massa_residual_kg", "massa_ossea_kg",
              "massa_muscular_kg", "bia_classificacao_gordura"}
OPCOES_FIXAS = {"protocolo_dobras": ["pollock7", "pollock3", "guedes"], "equacao_gordura": ["siri", "brozek"]}

app = Flask(__name__)
app.secret_key = os.urandom(16)


def conectar():
    return psycopg.connect(CONEXAO)


@app.before_request
def so_deste_computador():
    # um site aberto em outra aba não pode mandar formulários para cá
    if request.method == "POST":
        origem = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if urlparse(origem).hostname not in ("localhost", "127.0.0.1"):
            abort(403)


@app.template_filter("br")
def data_br(d):
    return d.strftime("%d/%m/%Y") if d else ""


@app.template_filter("num")
def numero(v):
    return "" if v is None else mostrar(v).replace(".", ",")


def idade(nasc, ref=None):
    if not nasc:
        return None
    ref = ref or date.today()
    return ref.year - nasc.year - ((ref.month, ref.day) < (nasc.month, nasc.day))


CAMPOS_PACIENTE = ["id", "nome", "genero", "data_nascimento", "telefone", "email", "retorno_em",
                   "whatsapp_bloqueado", "checkin_pausado", "meta_gordura_pct", "meta_imo"]


def buscar_paciente(cur, pid):
    cur.execute(f"SELECT {', '.join(CAMPOS_PACIENTE)} FROM paciente WHERE id = %s", (pid,))
    r = cur.fetchone()
    if not r:
        abort(404)
    return dict(zip(CAMPOS_PACIENTE, r))


@app.context_processor
def contagem_contatos():
    # número de lembretes do dia, no botão Contatos do menu
    try:
        with conectar() as con:
            cur = con.cursor()
            n = len(contatos.pendencias(cur, contatos.carregar()))
            cur.execute("SELECT count(*) FROM checkin WHERE paciente_id IS NULL AND NOT excluido")
            sem = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM consulta WHERE inicio::date = current_date AND status <> 'cancelada'")
            hoje = cur.fetchone()[0]
    except psycopg.Error:
        n = sem = hoje = 0
    return {"n_contatos": n, "n_pedidos": len(links.pedidos()), "n_checkin_sem": sem, "n_consultas_hoje": hoje}


def ler_formulario(form):
    valores, erros = {}, []
    rotulos = {c: r for _, campos in SECOES for c, r in campos}
    for col in CAMPOS:
        try:
            valores[col] = converter(col, form.get(col))
        except ValueError:
            erros.append(f"{rotulos.get(col, col)}: \"{form.get(col)}\" não é número")
    try:
        d = date.fromisoformat(form.get("data_avaliacao", ""))
    except ValueError:
        d = None
        erros.append("Informe a data da avaliação")
    return d, valores, erros


def gerar_arquivos(cur, pid, nome):
    """gera de novo a planilha e a página do paciente; devolve avisos para mostrar na tela"""
    banco = avaliacoes_do_banco(cur, pid)
    if not banco:
        return []
    avs = [para_pagina(r) for r in banco]
    cur.execute("SELECT nome FROM paciente WHERE id <> %s", (pid,))
    homonimo = any(norm(n) == norm(nome) for n, in cur.fetchall())
    _, destino = achar_planilha(nome, {r["data_avaliacao"] for r in banco}, homonimo)
    avisos = []
    try:
        build(nome.strip(), [dict(a) for a in avs], str(destino))
    except PermissionError:
        avisos.append("A planilha está aberta no Excel e não foi atualizada. Feche o Excel e clique em "
                      "\"Gerar planilha e página\".")
    PAGINAS.mkdir(parents=True, exist_ok=True)
    montar(str(TEMPLATE), nome, avs, planos.plano_do_banco(cur, pid), str(PAGINAS / f"{safe_name(nome)}.html"),
           checkin.link_paciente(cur, contatos.carregar(), pid, nome), exames.extras_pagina(cur, pid))
    return avisos


def opcoes_texto(cur):
    """valores já usados em cada campo de texto, para sugerir no formulário"""
    ops = {}
    for col in TEXTO:
        if col in OPCOES_FIXAS:
            ops[col] = OPCOES_FIXAS[col]
            continue
        cur.execute(f"SELECT {col} FROM avaliacao WHERE {col} IS NOT NULL AND {col} !~ '^[0-9]' "
                    f"GROUP BY 1 ORDER BY count(*) DESC LIMIT 15")
        ops[col] = [r[0] for r in cur.fetchall()]
    return ops


@app.route("/")
def inicio():
    with conectar() as con:
        cur = con.cursor()
        cur.execute("""SELECT p.id, p.nome, p.genero, p.data_nascimento, count(a.id), max(a.data_avaliacao)
                       FROM paciente p LEFT JOIN avaliacao a ON a.paciente_id = p.id
                       GROUP BY p.id ORDER BY max(a.data_avaliacao) DESC NULLS LAST, p.nome""")
        pacientes = [dict(id=i, nome=n, genero=g, idade=idade(nasc), n=q, ultima=u, busca=norm(n))
                     for i, n, g, nasc, q, u in cur.fetchall()]
    return render_template("inicio.html", pacientes=pacientes)


@app.route("/paciente/novo", methods=["GET", "POST"])
def novo_paciente():
    dados, erros = request.form, []
    if request.method == "POST":
        nome = " ".join(dados.get("nome", "").split())
        genero = dados.get("genero") or None
        try:
            nasc = date.fromisoformat(dados["data_nascimento"]) if dados.get("data_nascimento") else None
        except ValueError:
            nasc = None
            erros.append("Data de nascimento inválida")
        if not nome:
            erros.append("Informe o nome")
        if not erros:
            with conectar() as con:
                cur = con.cursor()
                cur.execute("INSERT INTO paciente (nome, genero, data_nascimento, telefone, email, criado_em) "
                            "VALUES (%s, %s, %s, %s, %s, now()) RETURNING id",
                            (nome, genero, nasc, dados.get("telefone") or None, dados.get("email") or None))
                pid = cur.fetchone()[0]
            flash(f"Paciente {nome} cadastrado.")
            return redirect(url_for("paciente", pid=pid))
    return render_template("novo_paciente.html", dados=dados, erros=erros)


@app.route("/paciente/<int:pid>")
def paciente(pid):
    cfg = contatos.carregar()
    with conectar() as con:
        checkin.sincronizar_se_preciso(con, cfg)
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        checkins = checkin.com_alertas(checkin.lista(cur, "k.paciente_id = %s", (pid,), 26))
        consultas = agenda.lista(cur, "c.paciente_id = %s", (pid,))
        cur.execute("SELECT data, total FROM reds_leafq WHERE paciente_id = %s ORDER BY data DESC, id DESC LIMIT 1", (pid,))
        ult_leafq = cur.fetchone()
        cur.execute("SELECT data, ingestao_kcal, gasto_exercicio_kcal, mlg_kg FROM reds_energia WHERE paciente_id = %s "
                    "ORDER BY data DESC, id DESC LIMIT 1", (pid,))
        ult_ed = cur.fetchone()
        lista_ex, grupos_ex = exames.historico(cur, pid, p["genero"], 1)
        ult_exame = lista_ex and {"data": lista_ex[-1]["data"], "n": sum(1 for g in grupos_ex for l in g["linhas"] if l["valores"][-1] and not l["item"].get("calculado")),
                                  "alertas": exames.alertas(grupos_ex)}
        testes = exames.desempenho(cur, pid)
        avs = avaliacoes_do_banco(cur, pid)
        perfil_pac = antropo.para_pagina(avs, p["genero"], p["data_nascimento"],
                                        p["meta_gordura_pct"] and float(p["meta_gordura_pct"]), p["meta_imo"] and float(p["meta_imo"]))
        cur.execute("SELECT tipo, feito_em FROM contato WHERE paciente_id = %s ORDER BY feito_em DESC LIMIT 6", (pid,))
        historico = cur.fetchall()
        cur.execute("SELECT id, titulo, prescrito, nome_arquivo, enviado_em, jsonb_array_length(plano->'paginas'), "
                    "jsonb_array_length(plano->'refeicoes'), (plano->'totais'->>'kcal')::int, editor IS NOT NULL, "
                    "pdf IS NOT NULL FROM plano_alimentar WHERE paciente_id = %s ORDER BY id", (pid,))
        planos_paciente = [dict(zip(["id", "titulo", "prescrito", "nome_arquivo", "enviado_em", "paginas", "refeicoes",
                                     "kcal", "montado", "tem_pdf"], r)) for r in cur.fetchall()]
    p["idade"] = idade(p["data_nascimento"])
    art = links.artefato(pid, p["nome"])
    url = art and art.get("url")
    primeira, ultima = (avs[0], avs[-1]) if avs else (None, None)
    extra = {"{link_evolucao}": url,
             "{data_avaliacao}": ultima["data_avaliacao"].strftime("%d/%m/%Y") if ultima else None}
    # mensagens que fazem sentido para este paciente agora
    tipos = (["livre"] + (["evolucao"] if url and ultima else [])
             + (["retorno"] if p["retorno_em"] and p["retorno_em"] >= date.today() else [])
             + (["checkin"] if checkin.configurado(cfg) and not p["checkin_pausado"] else []))
    mensagens = [(t, contatos.TITULOS[t], contatos.mensagem(cfg, t, p, extra)) for t in tipos]
    # a página do paciente tem conteúdo com avaliação, plano alimentar ou check-in (paciente novo já pode ter link)
    tem_pagina = bool(avs or planos_paciente or (checkin.configurado(cfg) and not p["checkin_pausado"])
                      or ult_exame or testes or ult_leafq or ult_ed)
    return render_template("paciente.html", p=p, avs=list(reversed(avs)), primeira=primeira, ultima=ultima,
                           url=url, art=art, pedido=links.pedido(pid), historico=historico, mensagens=mensagens,
                           planos=planos_paciente, checkins=checkins, grafico=checkin.grafico_peso(checkins),
                           checkin_ligado=checkin.configurado(cfg), checkin_email=checkin.usa_email(cfg), tem_pagina=tem_pagina,
                           proximas=[c for c in consultas if c["fim"] >= datetime.now()],
                           reds_leafq=ult_leafq and {"data": ult_leafq[0], "total": ult_leafq[1], "risco": ult_leafq[1] >= reds.RISCO_LEAFQ},
                           reds_ed=ult_ed and (lambda ed: {"data": ult_ed[0], "ed": ed, "classe": reds.classe_ed(ed)})(
                               reds.energia_disponivel(*ult_ed[1:])),
                           ult_exame=ult_exame, testes=testes, perfil=perfil_pac,
                           passadas=[c for c in consultas if c["fim"] < datetime.now()][-3:][::-1], status_consulta=agenda.STATUS,
                           email_ok=checkin.email_valido(p["email"]),
                           tem_whatsapp=bool(contatos.telefone_whatsapp(p["telefone"])), titulos=contatos.ROTULOS)


@app.route("/paciente/<int:pid>/evolucao")
def evolucao(pid):
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        avs = [para_pagina(r) for r in avaliacoes_do_banco(cur, pid)]
        plano = planos.plano_do_banco(cur, pid)
        link_ck = checkin.link_paciente(cur, contatos.carregar(), pid, p["nome"])
        extras = exames.extras_pagina(cur, pid)
    if not (avs or plano or link_ck or exames.tem_extras(extras)):
        flash("A página deste paciente ainda não tem conteúdo: lance uma avaliação ou um plano alimentar.")
        return redirect(url_for("paciente", pid=pid))
    return gerar_html(str(TEMPLATE), p["nome"], avs, plano, link_ck, extras)


@app.route("/paciente/<int:pid>/gerar", methods=["POST"])
def gerar(pid):
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        avisos = gerar_arquivos(cur, pid, p["nome"])
    for a in avisos:
        flash(a, "aviso")
    if not avisos:
        flash("Planilha e página geradas de novo.")
    return redirect(url_for("paciente", pid=pid))


@app.route("/paciente/<int:pid>/planilha", methods=["POST"])
def abrir_planilha(pid):
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        cur.execute("SELECT nome FROM paciente WHERE id <> %s", (pid,))
        homonimo = any(norm(n) == norm(p["nome"]) for n, in cur.fetchall())
        datas = {r["data_avaliacao"] for r in avaliacoes_do_banco(cur, pid)}
    arq, _ = achar_planilha(p["nome"], datas, homonimo)
    if arq is None:
        flash("Este paciente ainda não tem planilha. Lance uma avaliação ou clique em \"Gerar planilha e página\".",
              "aviso")
    else:
        os.startfile(arq)
    return redirect(url_for("paciente", pid=pid))


@app.route("/paciente/<int:pid>/avaliacao/nova", methods=["GET", "POST"])
@app.route("/paciente/<int:pid>/avaliacao/<int:aid>", methods=["GET", "POST"])
def avaliacao(pid, aid=None):
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        avs = avaliacoes_do_banco(cur, pid)
        atual = next((a for a in avs if a["id"] == aid), None)
        if aid is not None and atual is None:
            abort(404)
        erros = []
        if request.method == "POST":
            d, valores, erros = ler_formulario(request.form)
            if d and any(a["data_avaliacao"] == d and a["id"] != aid for a in avs):
                erros.append(f"Já existe uma avaliação em {d:%d/%m/%Y}. Abra essa avaliação para editar.")
            if not erros:
                valores.update(calcular(valores, p["genero"], p["data_nascimento"], d))
                if aid is None:
                    cols = ["paciente_id", "data_avaliacao"] + list(valores)
                    cur.execute(f"INSERT INTO avaliacao ({', '.join(cols)}) "
                                f"VALUES ({', '.join(['%s'] * len(cols))})", [pid, d] + list(valores.values()))
                else:
                    cur.execute(f"UPDATE avaliacao SET data_avaliacao = %s, "
                                f"{', '.join(f'{c} = %s' for c in valores)} WHERE id = %s",
                                [d] + list(valores.values()) + [aid])
                con.commit()
                for a in gerar_arquivos(cur, pid, p["nome"]):
                    flash(a, "aviso")
                flash(f"Avaliação de {d:%d/%m/%Y} gravada." + pedir_atualizacao(pid, p["nome"]))
                return redirect(url_for("paciente", pid=pid))
            form = dict(request.form)
        elif atual:
            form = {c: numero(atual[c]) if c not in TEXTO else (atual[c] or "") for c in CAMPOS}
            form["data_avaliacao"] = atual["data_avaliacao"].isoformat()
        else:
            # avaliação nova: começa com a altura, os diâmetros ósseos e o protocolo da última
            ult = avs[-1] if avs else {}
            form = {"data_avaliacao": date.today().isoformat(),
                    "protocolo_dobras": ult.get("protocolo_dobras") or "pollock7",
                    "equacao_gordura": ult.get("equacao_gordura") or "siri"}
            for c in ("altura_cm", "diametro_umero", "diametro_punho", "diametro_femur"):
                form[c] = numero(ult.get(c))
        ops = opcoes_texto(cur)
    ops["protocolo_dobras"] = antropo.do_sexo(p["genero"])
    if form.get("protocolo_dobras") and form["protocolo_dobras"] not in ops["protocolo_dobras"]:
        ops["protocolo_dobras"].append(form["protocolo_dobras"])   # protocolo gravado antes, de outro sexo
    rotulos = {k: f"{v['nome']} · {v['publico']}" for k, v in antropo.PROTOCOLOS.items()}
    rotulos.update(siri="Siri", brozek="Brozek")
    return render_template("avaliacao.html", p=p, aid=aid, form=form, erros=erros, secoes=SECOES, texto=TEXTO,
                           ops=ops, calculados=CALCULADOS, rotulos=rotulos)


def pedir_atualizacao(pid, nome):
    if links.artefato(pid, nome):
        links.pedir(pid, nome, "atualizar")
        return " O link publicado ficou na fila para atualizar (menu Links)."
    return ""


@app.route("/paciente/<int:pid>/calcular", methods=["POST"])
def calcular_formulario(pid):
    """o formulário manda o que foi digitado e recebe de volta os campos calculados"""
    with conectar() as con:
        p = buscar_paciente(con.cursor(), pid)
    d, valores, _ = ler_formulario(request.form)
    valores = {k: v for k, v in valores.items() if v is not None}
    passos = []
    calc = calcular(valores, p["genero"], p["data_nascimento"], d or date.today(), passos)
    saida = {k: v if isinstance(v, str) else numero(v) for k, v in calc.items()}
    saida["_passos"] = passos   # fórmulas com os números, para o quadro "Como foi calculado"
    import calculos
    saida["_dobras"] = calculos.dobras_do_protocolo(valores.get("protocolo_dobras"), p["genero"])   # destacadas na tela
    tudo = dict(valores, **calc)
    pf = antropo.perfil(tudo, p["genero"], p["data_nascimento"], d or date.today(),
                       p["meta_gordura_pct"] and float(p["meta_gordura_pct"]), p["meta_imo"] and float(p["meta_imo"]),
                       valores.get("equacao_gordura") or "siri")
    pf["escolhido"] = valores.get("protocolo_dobras")
    saida["_perfil"] = pf   # comparação dos protocolos, somatotipo, PVC, Z-score e metas
    return saida


@app.route("/paciente/<int:pid>/avaliacao/<int:aid>/excluir", methods=["POST"])
def excluir(pid, aid):
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        cur.execute("DELETE FROM avaliacao WHERE id = %s AND paciente_id = %s RETURNING data_avaliacao", (aid, pid))
        r = cur.fetchone()
        con.commit()
        avisos = gerar_arquivos(cur, pid, p["nome"])
    for a in avisos:
        flash(a, "aviso")
    if r:
        flash(f"Avaliação de {r[0]:%d/%m/%Y} excluída." + pedir_atualizacao(pid, p["nome"]))
    return redirect(url_for("paciente", pid=pid))


# ---------- plano alimentar ----------

@app.route("/paciente/<int:pid>/plano", methods=["POST"])
def enviar_plano(pid):
    arq = request.files.get("arquivo")
    titulo = " ".join(request.form.get("titulo", "").split())
    try:
        prescrito = date.fromisoformat(request.form.get("prescrito", ""))
    except ValueError:
        prescrito = None
    voltar = url_for("paciente", pid=pid) + "#plano"
    if not arq or not arq.filename:
        flash("Escolha o PDF do plano alimentar.", "aviso")
        return redirect(voltar)
    dados = arq.read()
    # PDF de plano num modelo conhecido vira a dieta interativa; qualquer outro PDF (ou se pedir) entra página por página
    lido = None if request.form.get("como_paginas") else plano_pdf.ler(dados)
    if lido:
        titulo = titulo or lido["titulo"]
        prescrito = prescrito or datetime.strptime(lido["prescrito"], "%d/%m/%Y").date()
        lido.update(titulo=titulo, prescrito=prescrito.strftime("%d/%m/%Y"))
        plano, resumo = lido, f"lido do PDF: {len(lido['refeicoes'])} refeições"
    else:
        try:
            paginas = planos.pdf_para_paginas(dados)
        except ValueError as e:
            flash(str(e), "aviso")
            return redirect(voltar)
        titulo, prescrito = titulo or "Plano alimentar", prescrito or date.today()
        plano = planos.montar_plano(titulo, prescrito, paginas)
        resumo = f"{len(paginas)} página{'s' if len(paginas) > 1 else ''} do PDF"
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        planos.gravar(cur, pid, titulo, prescrito, arq.filename, dados, plano)
    flash(f"Plano alimentar enviado ({resumo}). Ele aparece na aba Plano alimentar da página de evolução."
          + pedir_atualizacao(pid, p["nome"]))
    return redirect(voltar)


@app.route("/plano/<int:plid>/remover", methods=["POST"])
def remover_plano(plid):
    with conectar() as con:
        cur = con.cursor()
        cur.execute("DELETE FROM plano_alimentar WHERE id = %s RETURNING paciente_id, titulo", (plid,))
        r = cur.fetchone()
        if not r:
            abort(404)
        p = buscar_paciente(cur, r[0])
    flash(f"Plano “{r[1]}” removido da página." + pedir_atualizacao(p["id"], p["nome"]))
    return redirect(url_for("paciente", pid=p["id"]) + "#plano")


@app.route("/plano/<int:plid>.pdf")
def pdf_do_plano(plid):
    with conectar() as con:
        r = con.execute("SELECT pdf, nome_arquivo FROM plano_alimentar WHERE id = %s", (plid,)).fetchone()
    if not r or not r[0]:
        abort(404)
    return app.response_class(bytes(r[0]), mimetype="application/pdf",
                              headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(r[1] or 'plano.pdf')}"})


# ---------- editor de planos (montar e calcular no sistema) ----------

def carregar_alimentos(cur, ids=None):
    """alimentos (nutrientes por 100 g) com suas medidas caseiras: {id: {...}}"""
    onde, args = ("WHERE a.id = ANY(%s)", (list(ids),)) if ids is not None else ("", ())
    cur.execute(f"SELECT a.id, a.nome, a.fonte, g.nome, {', '.join('a.' + c for c in nutricao.COLUNAS)} "
                f"FROM alimento a LEFT JOIN alimento_grupo g ON g.id = a.grupo_id {onde}", args)
    alimentos = {}
    for r in cur.fetchall():
        a = {"id": r[0], "nome": r[1], "fonte": r[2], "grupo": r[3], "medidas": []}
        a.update({c: (float(v) if v is not None else None) for c, v in zip(nutricao.COLUNAS, r[4:])})
        alimentos[r[0]] = a
    if alimentos:
        cur.execute("SELECT alimento_id, id, nome, gramas FROM medida_caseira WHERE alimento_id = ANY(%s) ORDER BY nome",
                    (list(alimentos),))
        for aid, mid, nome, g in cur.fetchall():
            alimentos[aid]["medidas"].append({"id": mid, "nome": nome, "gramas": float(g)})
    return alimentos


def ids_do_editor(editor):
    ids = set()
    for r in editor.get("refeicoes", []):
        for it in r.get("itens", []):
            ids.add(it.get("alimento_id"))
            ids.update(sub.get("alimento_id") for sub in it.get("subs", []))
    return {i for i in ids if isinstance(i, int)}


@app.route("/paciente/<int:pid>/plano/novo")
@app.route("/plano/<int:plid>/editar")
def editor_plano(pid=None, plid=None):
    with conectar() as con:
        cur = con.cursor()
        editor = None
        if plid is not None:
            cur.execute("SELECT paciente_id, editor FROM plano_alimentar WHERE id = %s", (plid,))
            r = cur.fetchone()
            if not r or not r[1]:
                abort(404)
            pid, editor = r
        p = buscar_paciente(cur, pid)
        ultima = (avaliacoes_do_banco(cur, pid) or [None])[-1]
        alimentos = carregar_alimentos(cur, ids_do_editor(editor)) if editor else {}
        cur.execute("SELECT id, nome FROM alimento_grupo ORDER BY id")
        grupos = cur.fetchall()
    peso = float(ultima["peso_kg"]) if ultima and ultima["peso_kg"] else None
    altura = float(ultima["altura_cm"]) if ultima and ultima["altura_cm"] else None
    imc = peso / (altura / 100) ** 2 if peso and altura else None
    if editor is None:
        editor = {"titulo": "", "prescrito": date.today().isoformat(),
                  "energia": {"sexo": p["genero"], "idade": nutricao.idade_em(p["data_nascimento"]), "peso": peso,
                              "altura": altura, "acamado": False, "formula": nutricao.formula_sugerida(imc),
                              "fa": 1.2, "ajuste": 0},
                  "agua": {"ml_kg": 33, "ml": None, "exibir": True},
                  "refeicoes": [{"hora": h, "nome": n, "obs": "", "itens": []}
                                for h, n in (("07:00", "Café da manhã"), ("10:00", "Lanche da manhã"), ("12:30", "Almoço"),
                                             ("16:00", "Lanche da tarde"), ("20:00", "Jantar"))]}
    base = {"imc": round(imc, 1) if imc else None,
            "data_avaliacao": ultima["data_avaliacao"].strftime("%d/%m/%Y") if ultima else None}
    try:
        suplementos = json.loads((Path(__file__).resolve().parent / "suplementos.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        suplementos = None   # rode scripts/importar_suplementos.py
    return render_template("editor_plano.html", p=p, plid=plid, editor=editor, alimentos=alimentos, base=base,
                           suplementos=suplementos,
                           formulas=nutricao.FORMULAS, grupos=grupos, diretrizes_agua=nutricao.DIRETRIZES_AGUA)


@app.route("/paciente/<int:pid>/plano/salvar", methods=["POST"])
def salvar_plano_editor(pid):
    dados = request.get_json(silent=True) or {}
    editor, plid = dados.get("editor") or {}, dados.get("plid")
    if not any(it for r in editor.get("refeicoes", []) for it in r.get("itens", [])):
        return {"erro": "Coloque pelo menos um alimento no plano."}, 400
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        alimentos = carregar_alimentos(cur, ids_do_editor(editor))
        editor["energia_calculada"] = nutricao.energia(editor.get("energia") or {})
        plano = nutricao.plano_para_paciente(editor, alimentos, planos.PROFISSIONAL)
        prescrito = datetime.strptime(plano["prescrito"], "%d/%m/%Y").date()
        if plid:
            cur.execute("UPDATE plano_alimentar SET titulo = %s, prescrito = %s, plano = %s, editor = %s, enviado_em = now() "
                        "WHERE id = %s AND paciente_id = %s RETURNING id",
                        (plano["titulo"], prescrito, json.dumps(plano, ensure_ascii=False),
                         json.dumps(editor, ensure_ascii=False), plid, pid))
            if not cur.fetchone():
                return {"erro": "Plano não encontrado."}, 404
        else:
            cur.execute("INSERT INTO plano_alimentar (paciente_id, titulo, prescrito, plano, editor) "
                        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (pid, plano["titulo"], prescrito, json.dumps(plano, ensure_ascii=False),
                         json.dumps(editor, ensure_ascii=False)))
            plid = cur.fetchone()[0]
    flash(f"Plano “{plano['titulo']}” salvo ({plano['totais']['kcal']} kcal). Ele aparece na aba Plano alimentar "
          f"da página do paciente." + pedir_atualizacao(pid, p["nome"]))
    return {"ok": True, "plid": plid, "voltar": url_for("paciente", pid=pid) + "#plano"}


@app.route("/alimentos/buscar")
def buscar_alimentos():
    termos = norm(request.args.get("q", "")).replace(",", " ").split()
    if not termos:
        return {"alimentos": []}
    with conectar() as con:
        cur = con.cursor()
        cur.execute("SELECT id, nome FROM alimento")
        achados = [(i, n) for i, n in cur.fetchall() if all(t in norm(n).replace(",", " ") for t in termos)]
        # primeiro os que começam pela palavra buscada, depois os nomes mais curtos
        achados.sort(key=lambda a: (not norm(a[1]).startswith(termos[0]), len(a[1])))
        alimentos = carregar_alimentos(cur, [i for i, _ in achados[:25]])
    return {"alimentos": [alimentos[i] for i, _ in achados[:25]]}


@app.route("/alimentos/<int:aid>/medidas", methods=["POST"])
def nova_medida(aid):
    d = request.get_json(silent=True) or {}
    nome = " ".join(str(d.get("nome", "")).split())
    try:
        gramas = float(str(d.get("gramas", "")).replace(",", "."))
    except ValueError:
        gramas = 0
    if not nome or gramas <= 0:
        return {"erro": "Informe o nome da medida e quantos gramas ela tem."}, 400
    with conectar() as con:
        cur = con.cursor()
        cur.execute("INSERT INTO medida_caseira (alimento_id, nome, gramas) VALUES (%s, %s, %s) "
                    "ON CONFLICT (alimento_id, nome) DO UPDATE SET gramas = EXCLUDED.gramas RETURNING id",
                    (aid, nome, gramas))
        mid = cur.fetchone()[0]
    return {"id": mid, "nome": nome, "gramas": gramas}


CAMPOS_ALIMENTO = [("kcal", "Energia (kcal)"), ("proteina_g", "Proteína (g)"), ("carboidrato_g", "Carboidrato (g)"),
                   ("lipidios_g", "Gorduras totais (g)"), ("ag_saturados_g", "Gorduras saturadas (g)"),
                   ("ag_trans_g", "Gorduras trans (g)"), ("fibra_g", "Fibra (g)"), ("sodio_mg", "Sódio (mg)")]


@app.route("/alimentos", methods=["GET", "POST"])
def alimentos_proprios():
    if request.method == "POST":
        f = request.form
        nome = " ".join(f.get("nome", "").split())
        try:
            porcao = float(f.get("porcao", "100").replace(",", ".") or 100)
        except ValueError:
            porcao = 0
        valores, erros = {}, []
        for c, rotulo in CAMPOS_ALIMENTO:
            v = f.get(c, "").strip().replace(",", ".")
            try:
                valores[c] = float(v) * 100 / porcao if v else None   # tudo por 100 g
            except (ValueError, ZeroDivisionError):
                erros.append(rotulo)
        if not nome or porcao <= 0 or valores.get("kcal") is None:
            erros.insert(0, "nome, porção e energia são obrigatórios")
        if erros:
            flash("Confira: " + ", ".join(erros) + ".", "aviso")
        else:
            with conectar() as con:
                cur = con.cursor()
                cols = ["fonte", "nome", "grupo_id"] + list(valores)
                cur.execute(f"INSERT INTO alimento ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                            ["proprio", nome, int(f["grupo_id"]) if f.get("grupo_id") else None] + list(valores.values()))
                aid = cur.fetchone()[0]
                if f.get("medida_nome", "").strip() and porcao:
                    cur.execute("INSERT INTO medida_caseira (alimento_id, nome, gramas) VALUES (%s, %s, %s)",
                                (aid, " ".join(f["medida_nome"].split()), porcao))
            flash(f"Alimento “{nome}” cadastrado. Já aparece na busca do editor de planos.")
        return redirect(url_for("alimentos_proprios"))
    with conectar() as con:
        cur = con.cursor()
        cur.execute("SELECT id, nome FROM alimento_grupo ORDER BY id")
        grupos = cur.fetchall()
        cur.execute("SELECT id FROM alimento WHERE fonte = 'proprio' ORDER BY lower(nome)")
        ids = [r[0] for r in cur.fetchall()]
        lista = carregar_alimentos(cur, ids)
        cur.execute("SELECT count(*) FROM alimento WHERE fonte = 'TACO'")
        n_taco = cur.fetchone()[0]
    return render_template("alimentos.html", proprios=[lista[i] for i in ids], grupos=grupos, n_taco=n_taco,
                           campos=CAMPOS_ALIMENTO)


# ---------- links publicados ----------

@app.route("/paciente/<int:pid>/link", methods=["POST"])
def pedir_link(pid):
    with conectar() as con:
        p = buscar_paciente(con.cursor(), pid)
    if request.form.get("cancelar"):
        links.cancelar(pid)
        flash("Pedido de link cancelado.")
    else:
        links.pedir(pid, p["nome"], "atualizar" if links.artefato(pid, p["nome"]) else "novo")
        flash("Pedido anotado. Quando quiser, peça ao Claude: \u201cpublique os links pedidos\u201d.")
    return redirect(request.form.get("voltar") or url_for("paciente", pid=pid))


@app.route("/links")
def lista_links():
    with conectar() as con:
        cur = con.cursor()
        cur.execute("SELECT id, nome FROM paciente")
        nomes = dict(cur.fetchall())
        cur.execute("SELECT paciente_id, max(data_avaliacao) FROM avaliacao GROUP BY 1")
        ultima = dict(cur.fetchall())
    # links antigos sem número do paciente: acha pelo nome
    por_nome = {norm(n): i for i, n in nomes.items()}
    publicados = []
    for nome, info in links.todos_artefatos().items():
        pid = info.get("id") or por_nome.get(norm(nome))
        publicados.append(dict(id=pid, nome=nomes.get(pid, nome), url=info.get("url"),
                               publicado_em=info.get("publicado_em"), ultima=ultima.get(pid)))
    publicados.sort(key=lambda x: norm(x["nome"]))
    return render_template("links.html", pedidos=links.pedidos(), publicados=publicados)


# ---------- WhatsApp ----------


# ---------- perfil do paciente ----------

PERFIL = ["nome", "genero", "data_nascimento", "cpf", "telefone", "email", "cep", "endereco", "bairro", "cidade",
          "estado", "etiquetas", "retorno_em", "whatsapp_bloqueado"]
UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


def ler_perfil(f):
    """formulário -> (valores, erros)"""
    v, erros = {}, []
    v["nome"] = " ".join(f.get("nome", "").split())
    if not v["nome"]:
        erros.append("Informe o nome")
    v["genero"] = f.get("genero") if f.get("genero") in ("M", "F") else None
    for campo, rotulo in (("data_nascimento", "Data de nascimento"), ("retorno_em", "Próxima consulta")):
        try:
            v[campo] = date.fromisoformat(f[campo]) if f.get(campo) else None
        except ValueError:
            v[campo] = None
            erros.append(f"{rotulo} inválida")
    if v["data_nascimento"] and v["data_nascimento"] > date.today():
        erros.append("A data de nascimento está no futuro")
    cpf = "".join(c for c in f.get("cpf", "") if c.isdigit())
    if cpf and len(cpf) != 11:
        erros.append("O CPF precisa ter 11 números")
    v["cpf"] = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else None
    cep = "".join(c for c in f.get("cep", "") if c.isdigit())
    if cep and len(cep) != 8:
        erros.append("O CEP precisa ter 8 números")
    v["cep"] = f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else None
    v["email"] = f.get("email", "").strip() or None
    if v["email"] and ("@" not in v["email"] or "." not in v["email"].split("@")[-1]):
        erros.append("E-mail inválido")
    v["estado"] = f.get("estado", "").strip().upper() or None
    if v["estado"] and v["estado"] not in UFS:
        erros.append("Estado (UF) inválido")
    for campo in ("telefone", "endereco", "bairro", "cidade", "etiquetas"):
        v[campo] = " ".join(f.get(campo, "").split()) or None
    v["whatsapp_bloqueado"] = bool(f.get("whatsapp_bloqueado"))
    return v, erros


@app.route("/paciente/<int:pid>/perfil", methods=["GET", "POST"])
def perfil(pid):
    with conectar() as con:
        cur = con.cursor()
        cur.execute(f"SELECT {', '.join(PERFIL)} FROM paciente WHERE id = %s", (pid,))
        r = cur.fetchone()
        if not r:
            abort(404)
        atual = dict(zip(PERFIL, r))
        cur.execute("SELECT count(*) FROM avaliacao WHERE paciente_id = %s", (pid,))
        n_avs = cur.fetchone()[0]
        erros, form = [], atual
        if request.method == "POST":
            novo, erros = ler_perfil(request.form)
            form = novo
            if not erros:
                if novo["nome"] != atual["nome"]:
                    links.vincular(pid, atual["nome"])          # o link publicado continua deste paciente
                cur.execute(f"UPDATE paciente SET {', '.join(f'{c} = %s' for c in PERFIL)}, modificado_em = now() "
                            f"WHERE id = %s", [novo[c] for c in PERFIL] + [pid])
                con.commit()
                avisos = renomear_planilha(atual["nome"], novo["nome"]) if novo["nome"] != atual["nome"] else []
                for a in avisos:
                    flash(a, "aviso")
                flash("Perfil salvo.")
                mudou_calculo = (novo["genero"], novo["data_nascimento"]) != (atual["genero"], atual["data_nascimento"])
                if mudou_calculo and n_avs:
                    return redirect(url_for("recalcular", pid=pid))
                if novo["nome"] != atual["nome"]:
                    for a in gerar_arquivos(cur, pid, novo["nome"]):
                        flash(a, "aviso")
                    flash("Nome alterado: a planilha e a página foram geradas de novo." + pedir_atualizacao(pid, novo["nome"]))
                return redirect(url_for("paciente", pid=pid))
        cur.execute("""SELECT (SELECT count(*) FROM plano_alimentar WHERE paciente_id = %(p)s),
                              (SELECT count(*) FROM checkin WHERE paciente_id = %(p)s AND NOT excluido)""", {"p": pid})
        n_planos, n_checkins = cur.fetchone()
    return render_template("perfil.html", p={"id": pid, "nome": atual["nome"]}, form=form, erros=erros, ufs=UFS,
                           n_avs=n_avs, n_planos=n_planos, n_checkins=n_checkins, art=links.artefato(pid, atual["nome"]))


# ---------- excluir paciente ----------
RAIZ = Path(__file__).resolve().parent.parent
EXCLUIDOS = RAIZ / "_backup" / "pacientes_excluidos"


def _para_json(v):
    if isinstance(v, (bytes, memoryview)):
        return {"base64": base64.b64encode(bytes(v)).decode()}   # PDF do plano
    if isinstance(v, Decimal):
        return float(v)
    return str(v)                                                 # datas


def _linhas(cur, sql, args):
    cur.execute(sql, args)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@app.route("/paciente/<int:pid>/excluir", methods=["POST"])
def excluir_paciente(pid):
    """apaga o paciente e tudo dele; antes, guarda uma cópia completa em _backup/pacientes_excluidos"""
    if request.form.get("confirma", "").strip().upper() != "EXCLUIR":
        flash("Nada foi excluído. Para excluir, digite EXCLUIR na caixa de confirmação.", "aviso")
        return redirect(url_for("perfil", pid=pid) + "#excluir")
    from atualizar_paciente import PLANILHAS
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        copia = {"excluido_em": datetime.now().isoformat(timespec="seconds"),
                 "paciente": _linhas(cur, "SELECT * FROM paciente WHERE id = %s", (pid,))[0]}
        for tabela in ("avaliacao", "plano_alimentar", "contato", "checkin"):
            copia[tabela] = _linhas(cur, f"SELECT * FROM {tabela} WHERE paciente_id = %s ORDER BY id", (pid,))
        # planilha e página deste paciente (com homônimo, os arquivos levam um número no nome)
        cur.execute("SELECT nome FROM paciente WHERE id <> %s", (pid,))
        homonimo = any(norm(n) == norm(p["nome"]) for n, in cur.fetchall())
        planilha, _ = achar_planilha(p["nome"], {a["data_avaliacao"] for a in copia["avaliacao"]}, homonimo)
        pagina = PAGINAS / f"{safe_name(p['nome'])}{f' ({pid})' if homonimo else ''}.html"
        EXCLUIDOS.mkdir(parents=True, exist_ok=True)
        arq = EXCLUIDOS / f"{safe_name(p['nome'])} ({pid}) {datetime.now():%Y-%m-%d %H%M%S}.json"
        arq.write_text(json.dumps(copia, ensure_ascii=False, indent=1, default=_para_json), encoding="utf-8")
        cur.execute("DELETE FROM paciente WHERE id = %s", (pid,))   # avaliações, planos, contatos e check-ins vão junto
    pagina.unlink(missing_ok=True)
    if planilha and planilha.exists():
        destino = PLANILHAS / "Excluídos" / planilha.name
        destino.parent.mkdir(exist_ok=True)
        if destino.exists():
            destino = destino.with_name(f"{destino.stem} {datetime.now():%Y-%m-%d %H%M%S}{destino.suffix}")
        try:
            shutil.move(str(planilha), str(destino))
        except PermissionError:
            flash(f"A planilha “{planilha.name}” está aberta no Excel e ficou na pasta. Feche o Excel e apague ou "
                  f"mova o arquivo se quiser.", "aviso")
    links.cancelar(pid)
    art = links.excluir(pid, p["nome"])
    flash(f"{p['nome']} foi excluído, com {len(copia['avaliacao'])} avaliação(ões) e {len(copia['plano_alimentar'])} "
          f"plano(s). Uma cópia de tudo ficou em _backup/pacientes_excluidos e a planilha foi para a pasta "
          f"“Excluídos”." + (" O link publicado continua no ar: para tirá-lo, peça ao Claude “apague o link de "
                             f"{p['nome']}”." if art else ""))
    return redirect(url_for("inicio"))


def renomear_planilha(antigo, novo):
    """a planilha do paciente tem o nome dele no arquivo: acompanha a troca de nome"""
    from atualizar_paciente import PLANILHAS
    origem, destino = PLANILHAS / f"{safe_name(antigo)}.xlsx", PLANILHAS / f"{safe_name(novo)}.xlsx"
    if not origem.exists() or origem == destino:
        return []
    if destino.exists():
        return [f"Já existe uma planilha chamada “{destino.name}”; a antiga ficou com o nome anterior."]
    try:
        origem.rename(destino)
    except PermissionError:
        return ["A planilha está aberta no Excel e ficou com o nome antigo. Feche o Excel e clique em “Gerar planilha de novo”."]
    finally:
        (PAGINAS / f"{safe_name(antigo)}.html").unlink(missing_ok=True)   # a página é gerada de novo com o nome novo
    return []


# campos que dependem do sexo e da idade e que o recálculo refaz (as medidas não mudam)
RECALCULAVEIS = sorted(CALCULADOS)
MOSTRAR_RECALCULO = [("gordura_pct", "% gordura"), ("classificacao_gordura", "Classificação % gordura"),
                     ("massa_gordura_kg", "Massa de gordura"), ("massa_muscular_kg", "Massa muscular"),
                     ("massa_residual_kg", "Massa residual"), ("mlg_kg", "Massa livre de gordura"),
                     ("densidade_corporal", "Densidade"), ("risco_rcq", "Risco RCQ"), ("cmb_adequacao_pct", "Adequação CMB"),
                     ("classificacao_cmb", "Classificação CMB"), ("classificacao_imc", "Classificação IMC"),
                     ("peso_ideal", "Peso ideal"), ("bia_classificacao_gordura", "Classif. bioimpedância")]


def comparar_recalculo(cur, pid):
    """[(avaliação, {campo: (antes, depois)})] com o sexo e a data de nascimento atuais do cadastro"""
    p = buscar_paciente(cur, pid)
    saida = []
    for a in avaliacoes_do_banco(cur, pid):
        v = {k: (float(x) if type(x).__name__ == "Decimal" else x) for k, x in a.items()}
        for k in RECALCULAVEIS:
            v[k] = None
        novo = calcular(v, p["genero"], p["data_nascimento"], a["data_avaliacao"])
        dif = {}
        for k, val in novo.items():
            antes = a.get(k)
            tol = {"densidade_corporal": 0.0005, "rcq": 0.005}.get(k, 0.05)   # pela quantidade de casas do campo
            igual = (str(antes) == str(val)) if isinstance(val, str) or antes is None or isinstance(antes, str) \
                else abs(float(antes) - float(val)) < tol
            if not igual:
                dif[k] = (antes, val)
        saida.append((a, dif))
    return p, saida


@app.route("/paciente/<int:pid>/recalcular", methods=["GET", "POST"])
def recalcular(pid):
    with conectar() as con:
        cur = con.cursor()
        p, comparacao = comparar_recalculo(cur, pid)
        if request.method == "POST":
            n = 0
            for a, dif in comparacao:
                if dif:
                    cur.execute(f"UPDATE avaliacao SET {', '.join(f'{k} = %s' for k in dif)} WHERE id = %s",
                                [d for _, d in dif.values()] + [a["id"]])
                    n += 1
            con.commit()
            for aviso in gerar_arquivos(cur, pid, p["nome"]):
                flash(aviso, "aviso")
            flash(f"{n} avaliaç{'ão recalculada' if n == 1 else 'ões recalculadas'} com o sexo e a idade do cadastro. "
                  f"A planilha e a página foram geradas de novo." + (pedir_atualizacao(pid, p["nome"]) if n else ""))
            return redirect(url_for("paciente", pid=pid))
    p["idade"] = idade(p["data_nascimento"])
    return render_template("recalcular.html", p=p, comparacao=comparacao, mostrar=MOSTRAR_RECALCULO,
                           com_mudanca=sum(1 for _, d in comparacao if d))


@app.route("/paciente/<int:pid>/acompanhamento", methods=["POST"])
def acompanhamento(pid):
    f = request.form
    try:
        retorno = date.fromisoformat(f["retorno_em"]) if f.get("retorno_em") else None
    except ValueError:
        retorno = None
    with conectar() as con:
        cur = con.cursor()
        buscar_paciente(cur, pid)
        email = f.get("email", "").strip() or None
        if email and not checkin.email_valido(email):
            flash(f"O e-mail “{email}” não parece válido e não foi salvo.", "aviso")
            email = buscar_paciente(cur, pid)["email"]
        cur.execute("UPDATE paciente SET retorno_em = %s, whatsapp_bloqueado = %s, checkin_pausado = %s, telefone = %s, "
                    "email = %s WHERE id = %s",
                    (retorno, bool(f.get("whatsapp_bloqueado")), bool(f.get("checkin_pausado")),
                     " ".join(f.get("telefone", "").split()) or None, email, pid))
    flash("Acompanhamento salvo.")
    return redirect(url_for("paciente", pid=pid) + "#acompanhamento")


@app.route("/paciente/<int:pid>/metas", methods=["POST"])
def metas_perfil(pid):
    f = request.form
    gc, imo = exames.ler_numero(f.get("meta_gordura_pct")), exames.ler_numero(f.get("meta_imo"))
    if gc is not None and not 3 <= gc <= 50:
        flash("% de gordura alvo: use um valor entre 3 e 50.", "aviso")
        gc = None
    if imo is not None and not 1 <= imo <= 10:
        flash("Índice músculo-ósseo alvo: use um valor entre 1 e 10 (costuma ficar entre 3 e 5).", "aviso")
        imo = None
    with conectar() as con:
        buscar_paciente(con.cursor(), pid)
        con.execute("UPDATE paciente SET meta_gordura_pct = %s, meta_imo = %s WHERE id = %s", (gc, imo, pid))
    flash("Metas salvas.")
    return redirect(url_for("paciente", pid=pid) + "#perfil")


@app.route("/paciente/<int:pid>/whatsapp/<tipo>", methods=["POST"])
def whatsapp(pid, tipo):
    """registra o contato e abre o WhatsApp com a mensagem pronta (você confere e envia)"""
    if tipo not in contatos.TITULOS:
        abort(404)
    texto = request.form.get("texto", "")
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        link = contatos.link_whatsapp(p["telefone"], texto)
        if tipo != "livre":
            cur.execute("INSERT INTO contato (paciente_id, tipo, referencia) VALUES (%s, %s, %s)",
                        (pid, tipo, contatos.referencia(tipo, p)))
    if request.form.get("so_marcar") or not link:
        if not link:
            flash(f"O telefone de {p['nome']} não serve para o WhatsApp. Corrija em Acompanhamento.", "aviso")
        return redirect(request.form.get("voltar") or url_for("contatos_do_dia"))
    return redirect(link)


@app.route("/contatos")
def contatos_do_dia():
    cfg = contatos.carregar()
    with conectar() as con:
        checkin.sincronizar_se_preciso(con, cfg)   # quem já respondeu sai da lista de pedidos de check-in
        cur = con.cursor()
        itens = []
        for tipo, p, detalhe in contatos.pendencias(cur, cfg):
            itens.append(dict(tipo=tipo, titulo=contatos.TITULOS[tipo], p=p, detalhe=detalhe,
                              texto=contatos.mensagem(cfg, tipo, p),
                              tem_whatsapp=bool(contatos.telefone_whatsapp(p["telefone"]))))
        cur.execute("""SELECT c.feito_em, c.tipo, p.id, p.nome FROM contato c JOIN paciente p ON p.id = c.paciente_id
                       WHERE c.feito_em >= %s ORDER BY c.feito_em DESC""", (date.today(),))
        feitos = cur.fetchall()
        cur.execute("""SELECT id, nome, retorno_em FROM paciente WHERE retorno_em >= %s
                       ORDER BY retorno_em, nome LIMIT 30""", (date.today(),))
        agenda = cur.fetchall()
    return render_template("contatos.html", itens=itens, feitos=feitos, agenda=agenda, titulos=contatos.ROTULOS,
                           quando=contatos.quando)


@app.route("/configuracao", methods=["GET", "POST"])
def configuracao():
    cfg = contatos.carregar()
    if request.method == "POST":
        try:
            cfg["retorno_dias_antes"] = max(0, min(7, int(request.form.get("retorno_dias_antes", 1))))
        except ValueError:
            pass
        for t in contatos.TITULOS:
            if request.form.get(f"msg_{t}", "").strip():
                cfg["mensagens"][t] = request.form[f"msg_{t}"].strip()
        ag = cfg["agenda"]
        for k in ("local_presencial", "local_online", "profissional"):     # podem ficar vazios
            if k in request.form:
                ag[k] = request.form[k].strip()
        for k in ("email_assunto", "email_texto"):                          # vazio = mantém o texto atual
            if request.form.get(k, "").strip():
                ag[k] = request.form[k].strip().replace("\r\n", "\n")
        if "agenda_duracao" in request.form:   # o cartão da agenda veio no formulário
            for k in ("google", "google_convidar", "google_mostrar"):
                ag[k] = bool(request.form.get(k))
        try:
            ag["duracao"] = max(10, min(240, int(request.form.get("agenda_duracao", ag["duracao"]))))
        except ValueError:
            pass
        ck = cfg["checkin"]
        ck["email_ativo"] = bool(request.form.get("email_ativo"))
        for k in ("email_remetente", "email_assunto", "email_texto"):
            if request.form.get(k, "").strip():
                ck[k] = request.form[k].strip().replace("\r\n", "\n")
        for k, lo, hi in (("dias", 3, 31), ("ativo_dias", 15, 365), ("email_espera", 1, 6)):
            try:
                ck[k] = max(lo, min(hi, int(request.form.get(f"checkin_{k}", ck[k]))))
            except ValueError:
                pass
        url, chave = request.form.get("checkin_url", "").strip(), checkin.limpar_chave(request.form.get("checkin_chave", ""))
        if (url, chave) != (ck["url"], ck["chave"]):
            if not (url or chave):
                ck.update(url="", chave="", formulario="")
                flash("Check-in desligado do Google.")
            else:
                try:
                    info = checkin.testar(url, chave)
                    ck.update(url=url, chave=chave, formulario=info["link"], marca=info.get("marca", "NOME_DO_PACIENTE"),
                              versao=info.get("versao", 1))
                    flash(f"Check-in ligado ao formulário “{info.get('titulo', '')}”, que tem "
                          f"{info.get('respostas', 0)} resposta(s).")
                except checkin.ErroGoogle as e:
                    flash(f"A configuração foi salva, menos o check-in: {e}", "aviso")
        estado = None
        if checkin.configurado(cfg):
            try:
                info = checkin.info(ck["url"], ck["chave"])   # confere a versão do script (pode ter sido atualizado)
                ck["versao"] = info.get("versao", 1)
                if ck["versao"] >= checkin.VERSAO_SCRIPT:
                    with conectar() as con:
                        n, estado = checkin.enviar_lista(con.cursor(), cfg)
                    if ck["email_ativo"]:
                        flash(f"E-mail automático ligado: {n} paciente(s) com e-mail estão na lista de envio."
                              + ("" if estado.get("gatilho") else " Falta rodar a função ativarEmails no script do Google."),
                              "" if estado.get("gatilho") else "aviso")
                elif ck["email_ativo"]:
                    flash("Para o e-mail automático, atualize o código do script do Google (passo a passo abaixo).", "aviso")
            except checkin.ErroGoogle as e:
                flash(str(e), "aviso")
        contatos.salvar(cfg)
        flash("Configuração salva.")
        return redirect(url_for("configuracao"))
    estado = None
    if checkin.configurado(cfg):
        try:
            info = checkin.info(cfg["checkin"]["url"], cfg["checkin"]["chave"])
            estado = info.get("emails")
            if info.get("versao", 1) != cfg["checkin"].get("versao") or \
                    (info.get("leafq_link") or "") != (cfg["checkin"].get("leafq_formulario") or ""):
                cfg["checkin"]["versao"] = info.get("versao", 1)
                cfg["checkin"]["leafq_formulario"] = info.get("leafq_link") or ""
                contatos.salvar(cfg)
        except checkin.ErroGoogle as e:
            estado = {"erro": str(e)}
    with conectar() as con:
        cur = con.cursor()
        hoje = date.today()
        cur.execute(f"SELECT p.email FROM paciente p WHERE {checkin.ATIVOS}",
                    {"hoje": hoje, "desde": hoje - timedelta(days=int(cfg["checkin"].get("ativo_dias", 90)))})
        ativos = [e for e, in cur.fetchall()]
    return render_template("configuracao.html", cfg=cfg, titulos=contatos.TITULOS, variaveis=contatos.VARIAVEIS,
                           padrao=contatos.PADRAO["mensagens"], script=checkin.SCRIPT.read_text(encoding="utf-8"),
                           exemplo=checkin.link_formulario(cfg, "Maria da Silva"), estado=estado,
                           versao_atual=checkin.VERSAO_SCRIPT, versao_email=agenda.VERSAO_EMAIL,
                           versao_google=agenda.VERSAO_GOOGLE, n_ativos=len(ativos),
                           n_com_email=sum(checkin.email_valido(e) for e in ativos))


# ---------- rastreio de RED-S ----------

def _numero_form(v):
    try:
        return float(str(v).replace(",", ".")) if str(v).strip() else None
    except ValueError:
        return None


# ---------- exames laboratoriais ----------
@app.route("/paciente/<int:pid>/exames")
def exames_paciente(pid, erros=(), form=None):
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        lista, grupos = exames.historico(cur, pid, p["genero"])
    p["idade"] = idade(p["data_nascimento"])
    editar = next((e for e in lista if str(e["id"]) == request.args.get("editar", "")), None)
    if form is None:
        form = {"data": editar["data"].isoformat() if editar else date.today().isoformat(),
                "laboratorio": editar and editar["laboratorio"] or "", "observacao": editar and editar["observacao"] or ""}
        for k, (v, ref) in (editar["valores"] if editar else {}).items():
            form["v_" + k], form["r_" + k] = exames.fmt(v), ref or ""
    return render_template("exames.html", p=p, exames=lista, grupos=grupos, alertas=exames.alertas(grupos),
                           catalogo=exames.carregar()["grupos"], editar=editar, form=form, erros=erros,
                           ref=lambda it: exames.texto_ref(exames.ref_padrao(it, p["genero"])))


@app.route("/paciente/<int:pid>/exames", methods=["POST"])
def exames_salvar(pid):
    f = request.form
    erros, valores = [], {}
    try:
        data = date.fromisoformat(f.get("data", ""))
    except ValueError:
        data = None
        erros.append("Informe a data da coleta.")
    for k, it in exames.itens().items():
        if it.get("calculado") or not f.get("v_" + k, "").strip():
            continue
        v = exames.ler_numero(f["v_" + k])
        if v is None or v < 0:
            erros.append(f"{it['nome']}: \"{f['v_' + k]}\" não é um número.")
            continue
        valores[k] = (exames.normalizar(k, v), f.get("r_" + k, "").strip() or None)
    if not valores and not erros:
        erros.append("Preencha pelo menos um exame.")
    if erros:
        return exames_paciente(pid, erros, f.to_dict())
    eid = f.get("exame_id", type=int)
    lab, obs = f.get("laboratorio", "").strip() or None, f.get("observacao", "").strip() or None
    with conectar() as con:
        cur = con.cursor()
        buscar_paciente(cur, pid)
        cur.execute("SELECT id FROM exame WHERE paciente_id = %s AND data = %s", (pid, data))
        mesma = cur.fetchone()
        if eid:
            # edição: troca todos os valores do exame
            if mesma and mesma[0] != eid:
                return exames_paciente(pid, [f"Já existe um exame em {data:%d/%m/%Y}: edite aquele."], f.to_dict())
            cur.execute("UPDATE exame SET data = %s, laboratorio = %s, observacao = %s WHERE id = %s AND paciente_id = %s RETURNING id",
                        (data, lab, obs, eid, pid))
            cur.fetchone() or abort(404)
            cur.execute("DELETE FROM exame_valor WHERE exame_id = %s", (eid,))
        elif mesma:
            # mesma data de um exame que já existe: completa aquele
            eid = mesma[0]
            cur.execute("UPDATE exame SET laboratorio = coalesce(%s, laboratorio), observacao = coalesce(%s, observacao) WHERE id = %s",
                        (lab, obs, eid))
        else:
            cur.execute("INSERT INTO exame (paciente_id, data, laboratorio, observacao) VALUES (%s, %s, %s, %s) RETURNING id",
                        (pid, data, lab, obs))
            eid = cur.fetchone()[0]
        for k, (v, ref) in valores.items():
            cur.execute("INSERT INTO exame_valor (exame_id, item, valor, ref_laudo) VALUES (%s, %s, %s, %s) "
                        "ON CONFLICT (exame_id, item) DO UPDATE SET valor = EXCLUDED.valor, ref_laudo = EXCLUDED.ref_laudo",
                        (eid, k, v, ref))
    n = len(valores)
    flash(f"Exame de {data:%d/%m/%Y} salvo ({n} resultado{'s' if n != 1 else ''}).")
    return redirect(url_for("exames_paciente", pid=pid) + "#historico")


@app.route("/exame/<int:eid>/excluir", methods=["POST"])
def exame_excluir(eid):
    with conectar() as con:
        r = con.execute("DELETE FROM exame WHERE id = %s RETURNING paciente_id, data", (eid,)).fetchone() or abort(404)
    flash(f"Exame de {r[1]:%d/%m/%Y} excluído.")
    return redirect(url_for("exames_paciente", pid=r[0]) + "#historico")


@app.route("/exames/referencias", methods=["GET", "POST"])
def exames_referencias():
    dados = exames.carregar()
    if request.method == "POST":
        f = request.form
        backup = RAIZ / "_backup" / "exames_original.json"
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(exames.CATALOGO, backup)
        par = lambda a, b: [exames.ler_numero(f.get(a)), exames.ler_numero(f.get(b))]
        for g in dados["grupos"]:
            for it in g["itens"]:
                k = it["id"]
                if f"u_{k}" not in f:
                    continue
                it["unidade"] = f[f"u_{k}"].strip()
                m, fe = par(f"m0_{k}", f"m1_{k}"), par(f"f0_{k}", f"f1_{k}")
                for c in ("ref", "M", "F"):
                    it.pop(c, None)
                if m == fe:
                    if m != [None, None]:
                        it["ref"] = m
                else:
                    if m != [None, None]:
                        it["M"] = m
                    if fe != [None, None]:
                        it["F"] = fe
        exames.gravar(dados)
        flash("Referências salvas. Os exames passam a ser classificados com elas.")
        return redirect(url_for("exames_referencias"))
    lado = lambda it, s: it.get(s) or it.get("ref") or [None, None]
    return render_template("exames_referencias.html", grupos=dados["grupos"], lado=lado, fmt=exames.fmt)


# ---------- testes de desempenho ----------
@app.route("/paciente/<int:pid>/desempenho")
def desempenho_paciente(pid, erros=(), form=None):
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        testes = exames.desempenho(cur, pid)
    p["idade"] = idade(p["data_nascimento"])
    return render_template("desempenho.html", p=p, testes=testes, sugestoes=exames.TESTES, erros=erros,
                           form=form or {"data": date.today().isoformat()}, fmt=exames.fmt)


@app.route("/paciente/<int:pid>/desempenho", methods=["POST"])
def desempenho_salvar(pid):
    f = request.form
    erros = []
    try:
        data = date.fromisoformat(f.get("data", ""))
    except ValueError:
        erros.append("Informe a data do teste.")
    teste = " ".join(f.get("teste", "").split())
    if not teste:
        erros.append("Informe o nome do teste.")
    valor, esq = exames.ler_numero(f.get("valor")), exames.ler_numero(f.get("valor_esq"))
    if valor is None:
        erros.append("Informe o resultado" + (" do lado direito." if f.get("valor_esq", "").strip() else "."))
    if f.get("valor_esq", "").strip() and esq is None:
        erros.append("O resultado do lado esquerdo não é um número.")
    if erros:
        return desempenho_paciente(pid, erros, f.to_dict())
    with conectar() as con:
        buscar_paciente(con.cursor(), pid)
        con.execute("INSERT INTO desempenho (paciente_id, data, teste, unidade, melhor, valor, valor_esq, observacao) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (pid, data, teste, f.get("unidade", "").strip(), "menor" if f.get("melhor") == "menor" else "maior",
                     valor, esq, f.get("observacao", "").strip() or None))
    flash(f"{teste}: resultado de {data:%d/%m/%Y} salvo.")
    return redirect(url_for("desempenho_paciente", pid=pid) + "#testes")


@app.route("/desempenho/<int:did>/excluir", methods=["POST"])
def desempenho_excluir(did):
    with conectar() as con:
        r = con.execute("DELETE FROM desempenho WHERE id = %s RETURNING paciente_id", (did,)).fetchone() or abort(404)
    flash("Resultado excluído.")
    return redirect(url_for("desempenho_paciente", pid=r[0]) + "#testes")


@app.route("/paciente/<int:pid>/reds")
def reds_paciente(pid, erros=()):
    cfg = contatos.carregar()
    with conectar() as con:
        reds.sincronizar_se_preciso(con, cfg)
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        cur.execute("SELECT count(*) FROM reds_leafq WHERE paciente_id IS NULL")
        n_sem = cur.fetchone()[0]
        cur.execute("SELECT max(feito_em) FROM contato WHERE paciente_id = %s AND tipo = 'leafq'", (pid,))
        enviado = cur.fetchone()[0]
        cur.execute("SELECT id, data, respostas, lesoes, gastro, menstrual, total, origem FROM reds_leafq WHERE paciente_id = %s "
                    "ORDER BY data DESC, id DESC", (pid,))
        leafqs = [dict(zip(["id", "data", "respostas", "lesoes", "gastro", "menstrual", "total", "origem"], r)) for r in cur.fetchall()]
        for q in leafqs:
            q["classe"] = reds.classe_leafq(q["total"])
        cur.execute("SELECT id, data, ingestao_kcal, gasto_exercicio_kcal, mlg_kg, observacao FROM reds_energia "
                    "WHERE paciente_id = %s ORDER BY data DESC, id DESC", (pid,))
        energias = [dict(zip(["id", "data", "ingestao_kcal", "gasto_exercicio_kcal", "mlg_kg", "observacao"], r)) for r in cur.fetchall()]
        for e in energias:
            e["ed"] = reds.energia_disponivel(e["ingestao_kcal"], e["gasto_exercicio_kcal"], e["mlg_kg"])
            e["classe"] = reds.classe_ed(e["ed"])
        # MLG da última avaliação (dobras; se não houver, bioimpedância)
        cur.execute("""SELECT data_avaliacao, mlg_kg, bia_mlg_kg FROM avaliacao WHERE paciente_id = %s
                       AND (mlg_kg IS NOT NULL OR bia_mlg_kg IS NOT NULL) ORDER BY data_avaliacao DESC LIMIT 1""", (pid,))
        r = cur.fetchone()
        mlg = r and {"data": r[0], "valor": r[1] if r[1] is not None else r[2],
                     "origem": "Dobras cutâneas" if r[1] is not None else "Bioimpedância"}
        cur.execute("SELECT (plano->'totais'->>'kcal')::int FROM plano_alimentar WHERE paciente_id = %s "
                    "AND plano->'totais'->>'kcal' IS NOT NULL ORDER BY enviado_em DESC NULLS LAST, id DESC LIMIT 1", (pid,))
        r = cur.fetchone()
        kcal_plano = r[0] if r and r[0] else None
    p["idade"] = idade(p["data_nascimento"])
    ck = cfg["checkin"]
    envio = {"ligado": bool(ck.get("url") and ck.get("chave")), "versao_ok": int(ck.get("versao") or 0) >= 5,
             "link": reds.link_leafq(cfg, p["nome"]), "enviado": enviado, "n_sem": n_sem,
             "texto": contatos.mensagem(cfg, "leafq", p), "tem_whatsapp": bool(contatos.telefone_whatsapp(p["telefone"]))}
    return render_template("reds.html", p=p, leafqs=leafqs, energias=energias, mlg=mlg, kcal_plano=kcal_plano, envio=envio,
                           perguntas=reds.PERGUNTAS, secoes=reds.SECOES, risco=reds.RISCO_LEAFQ,
                           hoje=date.today().isoformat(), erros=erros)


@app.route("/paciente/<int:pid>/reds/leafq", methods=["POST"])
def reds_leafq(pid):
    try:
        data = date.fromisoformat(request.form.get("data", ""))
    except ValueError:
        return reds_paciente(pid, ["Informe a data da aplicação do LEAF-Q."])
    respostas = reds.ler_formulario(request.form)
    if not respostas:
        return reds_paciente(pid, ["Nenhuma pergunta do LEAF-Q foi respondida."])
    les, gi, men, total = reds.pontuar(respostas)
    with conectar() as con:
        buscar_paciente(con.cursor(), pid)
        con.execute("INSERT INTO reds_leafq (paciente_id, data, respostas, lesoes, gastro, menstrual, total) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)", (pid, data, json.dumps(respostas, ensure_ascii=False), les, gi, men, total))
    flash(f"LEAF-Q salvo: {total} ponto(s), {reds.classe_leafq(total).lower()}.")
    return redirect(url_for("reds_paciente", pid=pid) + "#leafq")


@app.route("/paciente/<int:pid>/reds/energia", methods=["POST"])
def reds_energia(pid):
    f = request.form
    ing, gee, mlg = _numero_form(f.get("ingestao", "")), _numero_form(f.get("gasto", "")), _numero_form(f.get("mlg", ""))
    erros = []
    try:
        data = date.fromisoformat(f.get("data", ""))
    except ValueError:
        erros.append("Informe a data.")
    if ing is None or not 300 <= ing <= 10000:
        erros.append("Ingestão energética: informe as kcal do dia (entre 300 e 10.000).")
    if gee is None or not 0 <= gee <= 8000:
        erros.append("Gasto no exercício: informe as kcal (entre 0 e 8.000).")
    if mlg is None or not 20 <= mlg <= 150:
        erros.append("Massa livre de gordura: informe em kg (entre 20 e 150).")
    if erros:
        return reds_paciente(pid, erros)
    with conectar() as con:
        buscar_paciente(con.cursor(), pid)
        con.execute("INSERT INTO reds_energia (paciente_id, data, ingestao_kcal, gasto_exercicio_kcal, mlg_kg, observacao) "
                    "VALUES (%s, %s, %s, %s, %s, %s)", (pid, data, ing, gee, mlg, f.get("observacao", "").strip() or None))
    ed = reds.energia_disponivel(ing, gee, mlg)
    flash(f"Energia disponível: {ed:.1f} kcal/kg MLG/dia ({reds.classe_ed(ed).lower()}).".replace(".", ",", 1))
    return redirect(url_for("reds_paciente", pid=pid) + "#energia")


@app.route("/reds/leafq/<int:qid>/excluir", methods=["POST"])
def reds_leafq_excluir(qid):
    with conectar() as con:
        r = con.execute("DELETE FROM reds_leafq WHERE id = %s RETURNING paciente_id", (qid,)).fetchone() or abort(404)
    flash("Aplicação do LEAF-Q excluída.")
    if r[0] is None:
        return redirect(url_for("reds_respostas"))
    return redirect(url_for("reds_paciente", pid=r[0]) + "#leafq")


@app.route("/reds/formulario/criar", methods=["POST"])
def reds_criar_formulario():
    cfg = contatos.carregar()
    try:
        r = reds.criar_formulario(cfg)
        cfg["checkin"]["leafq_formulario"] = r.get("link") or ""
        cfg["checkin"]["versao"] = r.get("versao", cfg["checkin"].get("versao"))
        contatos.salvar(cfg)
        flash("Formulário do LEAF-Q criado no seu Google. Agora é só mandar o link para as pacientes.")
    except checkin.ErroGoogle as e:
        flash(str(e), "aviso")
    return redirect(request.form.get("voltar") or url_for("reds_respostas"))


@app.route("/reds/respostas")
def reds_respostas():
    """respostas do LEAF-Q que chegaram sem paciente identificada, e a importação da planilha antiga"""
    cfg = contatos.carregar()
    with conectar() as con:
        cur = con.cursor()
        cur.execute("SELECT id, data, nome_informado, lesoes, gastro, menstrual, total, origem FROM reds_leafq "
                    "WHERE paciente_id IS NULL ORDER BY data DESC, id DESC")
        sem = [dict(zip(["id", "data", "nome", "lesoes", "gastro", "menstrual", "total", "origem"], r)) for r in cur.fetchall()]
        cur.execute("SELECT nome FROM paciente ORDER BY nome")
        nomes = [r[0] for r in cur.fetchall()]
    return render_template("reds_respostas.html", sem=sem, nomes=nomes, risco=reds.RISCO_LEAFQ,
                           formulario=bool(cfg["checkin"].get("leafq_formulario")))


@app.route("/reds/respostas/buscar", methods=["POST"])
def reds_buscar():
    try:
        with conectar() as con:
            novas, sem = reds.sincronizar(con.cursor(), contatos.carregar())
        flash(f"{novas} resposta(s) nova(s) do LEAF-Q." + (f" {sem} sem paciente identificada: escolha abaixo." if sem else "")
              if novas else "Nenhuma resposta nova do LEAF-Q.")
    except checkin.ErroGoogle as e:
        flash(str(e), "aviso")
    return redirect(request.form.get("voltar") or url_for("reds_respostas"))


@app.route("/reds/leafq/<int:qid>/paciente", methods=["POST"])
def reds_leafq_paciente(qid):
    nome = request.form.get("paciente", "")
    with conectar() as con:
        cur = con.cursor()
        cur.execute("SELECT id, nome FROM paciente")
        achados = [i for i, n in cur.fetchall() if norm(n) == norm(nome)]
        if len(achados) != 1:
            flash(f"Não achei uma paciente só com o nome “{nome}”. Escolha um nome da lista.", "aviso")
        else:
            cur.execute("UPDATE reds_leafq SET paciente_id = %s WHERE id = %s", (achados[0], qid))
            flash("Resposta do LEAF-Q ligada à paciente.")
    return redirect(url_for("reds_respostas"))


@app.route("/reds/importar", methods=["POST"])
def reds_importar():
    """lê a planilha antiga (aba de respostas do formulário) e mostra as respostas para escolher a paciente de cada uma"""
    arq = request.files.get("arquivo")
    if not arq or not arq.filename:
        flash("Escolha a planilha de RED-S (.xlsx).", "aviso")
        return redirect(url_for("reds_respostas"))
    try:
        linhas = reds.ler_planilha(arq.read())
    except Exception as e:   # arquivo que não é planilha, aba diferente...
        flash(f"Não consegui ler a planilha ({e.__class__.__name__}).", "aviso")
        return redirect(url_for("reds_respostas"))
    with conectar() as con:
        cur = con.cursor()
        cur.execute("SELECT origem FROM reds_leafq WHERE origem LIKE 'planilha:%%'")
        ja = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT nome FROM paciente ORDER BY nome")
        nomes = [r[0] for r in cur.fetchall()]
    for l in linhas:
        l["origem"] = f"planilha:{arq.filename}:{l['linha']}"
        l["ja"] = l["origem"] in ja
        l["json"] = json.dumps(l["respostas"], ensure_ascii=False)
    return render_template("reds_importar.html", linhas=linhas, nomes=nomes, arquivo=arq.filename,
                           risco=reds.RISCO_LEAFQ, hoje=date.today().isoformat())


@app.route("/reds/importar/salvar", methods=["POST"])
def reds_importar_salvar():
    f = request.form
    feitas, avisos = 0, []
    with conectar() as con:
        cur = con.cursor()
        cur.execute("SELECT id, nome FROM paciente")
        pacientes = cur.fetchall()
        for i in f.getlist("linha"):
            nome = f.get(f"paciente_{i}", "").strip()
            if not nome:
                continue
            achados = [pid for pid, n in pacientes if norm(n) == norm(nome)]
            if len(achados) != 1:
                avisos.append(f"Resposta {i}: não achei a paciente “{nome}”.")
                continue
            try:
                data = date.fromisoformat(f.get(f"data_{i}", ""))
            except ValueError:
                data = date.today()
            respostas = reds.respostas_de(json.loads(f.get(f"respostas_{i}", "{}")))
            les, gi, men, total = reds.pontuar(respostas)
            cur.execute("""INSERT INTO reds_leafq (paciente_id, data, respostas, lesoes, gastro, menstrual, total, origem)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (origem) DO NOTHING""",
                        (achados[0], data, json.dumps(respostas, ensure_ascii=False), les, gi, men, total, f.get(f"origem_{i}")))
            feitas += cur.rowcount
    for a in avisos:
        flash(a, "aviso")
    flash(f"{feitas} resposta(s) da planilha importada(s) para o rastreio das pacientes.")
    return redirect(url_for("reds_respostas"))


@app.route("/reds/energia/<int:eid>/excluir", methods=["POST"])
def reds_energia_excluir(eid):
    with conectar() as con:
        r = con.execute("DELETE FROM reds_energia WHERE id = %s RETURNING paciente_id", (eid,)).fetchone() or abort(404)
    flash("Lançamento de energia disponível excluído.")
    return redirect(url_for("reds_paciente", pid=r[0]) + "#energia")


# ---------- agenda ----------

@app.route("/agenda")
def agenda_semana():
    try:
        ref = date.fromisoformat(request.args.get("semana", ""))
    except ValueError:
        ref = date.today()
    ini = ref - timedelta(days=ref.weekday())
    cfg = contatos.carregar()
    with conectar() as con:
        cs = agenda.lista(con.cursor(), "c.inicio >= %s AND c.inicio < %s", (ini, ini + timedelta(days=7)))
    google, erro_google = [], None
    if agenda.google_pronto(cfg) and cfg["agenda"].get("google_mostrar", True):
        try:
            google = agenda.eventos_google(cfg, ini, ini + timedelta(days=7))
        except checkin.ErroGoogle as e:
            erro_google = str(e)
    # cada dia: consultas e compromissos do Google, por horário (os de dia inteiro primeiro)
    dias = []
    for i in range(7):
        d = ini + timedelta(days=i)
        itens = [("consulta", c, c["inicio"]) for c in cs if c["inicio"].date() == d]
        itens += [("google", g, datetime.combine(d, datetime.min.time()) if g["dia_todo"] else g["inicio"])
                  for g in google if ((g["inicio"].date() <= d < g["fim"].date()) if g["dia_todo"] else g["inicio"].date() == d)]
        itens.sort(key=lambda x: x[2])
        dias.append((d, itens))
    pendentes = sum(1 for c in cs if c["status"] in ("agendada", "confirmada") and c["inicio"] >= datetime.now()
                    and not (c["whatsapp_enviado_em"] or c["email_enviado_em"]))
    return render_template("agenda.html", dias=dias, ini=ini, fim=ini + timedelta(days=6), hoje=date.today(),
                           google_ligado=agenda.google_pronto(cfg), erro_google=erro_google, n_google=len(google),
                           anterior=ini - timedelta(days=7), proxima=ini + timedelta(days=7), total=len(cs),
                           pendentes=pendentes, status=agenda.STATUS, modalidades=agenda.MODALIDADES, now=datetime.now())


@app.route("/agenda/nova", methods=["GET", "POST"])
@app.route("/consulta/<int:cid>", methods=["GET", "POST"])
def consulta(cid=None):
    cfg = contatos.carregar()
    ag = cfg["agenda"]
    with conectar() as con:
        cur = con.cursor()
        c = agenda.buscar(cur, cid) if cid else None
        if cid and not c:
            abort(404)
        f, erros = request.form, []
        if request.method == "POST":
            pid = c["paciente_id"] if c else None
            if not c:
                nome = " ".join(f.get("paciente", "").split())
                cur.execute("SELECT id, nome FROM paciente")
                achados = [i for i, n in cur.fetchall() if norm(n) == norm(nome)]
                if len(achados) == 1:
                    pid = achados[0]
                else:
                    erros.append(f"Não achei um paciente só com o nome “{nome}”. Escolha um nome da lista."
                                 if nome else "Escolha o paciente.")
            try:
                inicio = datetime.combine(date.fromisoformat(f.get("data", "")), datetime.strptime(f.get("hora", ""), "%H:%M").time())
            except ValueError:
                inicio = None
                erros.append("Informe a data e o horário.")
            try:
                duracao = max(10, min(480, int(f.get("duracao") or ag["duracao"])))
            except ValueError:
                duracao = ag["duracao"]
            modalidade = f.get("modalidade") if f.get("modalidade") in agenda.MODALIDADES else "presencial"
            status = f.get("status") if f.get("status") in agenda.STATUS else (c["status"] if c else "agendada")
            valores = (inicio, duracao, modalidade, f.get("local", "").strip() or None, status,
                       f.get("observacao", "").strip() or None)
            if not erros:
                if c:
                    mudou_hora = inicio != c["inicio"]
                    cur.execute("UPDATE consulta SET inicio = %s, duracao_min = %s, modalidade = %s, local = %s, status = %s, "
                                "observacao = %s" + (", whatsapp_enviado_em = NULL, email_enviado_em = NULL" if mudou_hora else "")
                                + " WHERE id = %s", (*valores, cid))
                    flash("Consulta atualizada." + (" O horário mudou: envie a nova confirmação abaixo." if mudou_hora else ""))
                else:
                    cur.execute("INSERT INTO consulta (paciente_id, inicio, duracao_min, modalidade, local, status, observacao) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id", (pid, *valores))
                    cid = cur.fetchone()[0]
                    flash("Consulta agendada. Agora envie a confirmação ao paciente, logo abaixo.")
                agenda.atualizar_retorno(cur, pid)
                try:
                    if agenda.sincronizar_evento(cur, cfg, agenda.buscar(cur, cid)):
                        flash("Google Agenda atualizado." if status != "cancelada" else "Evento tirado do Google Agenda.")
                except checkin.ErroGoogle as e:
                    flash(str(e), "aviso")
                for o in agenda.conflitos(cur, inicio, duracao, cid):
                    flash(f"Atenção: no mesmo horário já existe a consulta de {o['nome']} "
                          f"({o['inicio']:%H:%M}–{o['fim']:%H:%M}).", "aviso")
                return redirect(url_for("consulta", cid=cid) + "#confirmar")
        cur.execute("SELECT nome FROM paciente ORDER BY nome")
        nomes = [r[0] for r in cur.fetchall()]
        novo = {"paciente": "", "data": request.args.get("data", ""), "hora": "", "duracao": ag["duracao"],
                "modalidade": "presencial", "local": ag["local_presencial"], "status": "agendada", "observacao": ""}
        if request.args.get("paciente", "").isdigit():
            cur.execute("SELECT nome FROM paciente WHERE id = %s", (int(request.args["paciente"]),))
            r = cur.fetchone()
            novo["paciente"] = r[0] if r else ""
        if c:
            novo = {"paciente": c["nome"], "data": c["inicio"].date().isoformat(), "hora": c["inicio"].strftime("%H:%M"),
                    "duracao": c["duracao_min"], "modalidade": c["modalidade"], "local": c["local"] or "",
                    "status": c["status"], "observacao": c["observacao"] or ""}
        if request.method == "POST":
            novo.update({k: f.get(k, novo[k]) for k in novo})
        historico = []
        if c:
            cur.execute("SELECT tipo, feito_em FROM contato WHERE paciente_id = %s AND tipo IN ('confirmacao', 'confirmacao_email') "
                        "AND referencia = %s ORDER BY feito_em DESC", (c["paciente_id"], str(cid)))
            historico = cur.fetchall()
    confirmar = None
    if c:
        confirmar = {"whatsapp": agenda.texto(cfg["mensagens"]["confirmacao"], c, cfg),
                     "assunto": agenda.texto(ag["email_assunto"], c, cfg), "email": agenda.texto(ag["email_texto"], c, cfg),
                     "tem_whatsapp": bool(contatos.telefone_whatsapp(c["telefone"])), "email_pronto": agenda.email_pronto(cfg)}
    return render_template("consulta.html", c=c, form=novo, erros=erros, nomes=nomes, confirmar=confirmar,
                           google_ligado=agenda.google_pronto(cfg),
                           historico=historico, status=agenda.STATUS, modalidades=agenda.MODALIDADES,
                           locais={"presencial": ag["local_presencial"], "online": ag["local_online"]},
                           titulos=contatos.ROTULOS)


@app.route("/consulta/<int:cid>/whatsapp", methods=["POST"])
def consulta_whatsapp(cid):
    with conectar() as con:
        cur = con.cursor()
        c = agenda.buscar(cur, cid) or abort(404)
        link = contatos.link_whatsapp(c["telefone"], request.form.get("texto", ""))
        if not link:
            flash(f"O telefone de {c['nome']} não serve para o WhatsApp. Corrija na ficha do paciente.", "aviso")
            return redirect(url_for("consulta", cid=cid) + "#confirmar")
        cur.execute("UPDATE consulta SET whatsapp_enviado_em = now() WHERE id = %s", (cid,))
        cur.execute("INSERT INTO contato (paciente_id, tipo, referencia) VALUES (%s, 'confirmacao', %s)", (c["paciente_id"], str(cid)))
    return redirect(link)


@app.route("/consulta/<int:cid>/email", methods=["POST"])
def consulta_email(cid):
    f = request.form
    with conectar() as con:
        cur = con.cursor()
        c = agenda.buscar(cur, cid) or abort(404)
        email = f.get("email", "").strip()
        if email != (c["email"] or "") and checkin.email_valido(email):
            cur.execute("UPDATE paciente SET email = %s WHERE id = %s", (email, c["paciente_id"]))   # fica salvo na ficha
            c["email"] = email
        elif email and not checkin.email_valido(email):
            flash(f"O e-mail “{email}” não parece válido.", "aviso")
            return redirect(url_for("consulta", cid=cid) + "#confirmar")
        try:
            agenda.enviar_email(c, contatos.carregar(), f.get("assunto", "").strip(), f.get("texto", "").strip())
        except checkin.ErroGoogle as e:
            con.commit()
            flash(str(e), "aviso")
            return redirect(url_for("consulta", cid=cid) + "#confirmar")
        cur.execute("UPDATE consulta SET email_enviado_em = now() WHERE id = %s", (cid,))
        cur.execute("INSERT INTO contato (paciente_id, tipo, referencia) VALUES (%s, 'confirmacao_email', %s)", (c["paciente_id"], str(cid)))
    flash(f"Confirmação enviada por e-mail para {c['email']}, com o convite para a agenda do paciente.")
    return redirect(url_for("consulta", cid=cid) + "#confirmar")


@app.route("/consulta/<int:cid>/excluir", methods=["POST"])
def consulta_excluir(cid):
    with conectar() as con:
        cur = con.cursor()
        c = agenda.buscar(cur, cid) or abort(404)
        cur.execute("DELETE FROM consulta WHERE id = %s", (cid,))
        agenda.atualizar_retorno(cur, c["paciente_id"])
    flash(f"Consulta de {c['nome']} em {c['inicio']:%d/%m %H:%M} excluída.")
    try:
        agenda.excluir_evento(contatos.carregar(), c["google_evento_id"])
    except checkin.ErroGoogle as e:
        flash(str(e) + " Apague o evento no Google Agenda à mão.", "aviso")
    return redirect(url_for("agenda_semana", semana=c["inicio"].date().isoformat()))


@app.route("/agenda/google/enviar", methods=["POST"])
def agenda_google_enviar():
    """leva para o Google Agenda as consultas futuras que ainda não estão lá"""
    cfg = contatos.carregar()
    if not agenda.google_pronto(cfg):
        flash("Ligue o Google Agenda na Configuração (e atualize o script) primeiro.", "aviso")
        return redirect(url_for("configuracao") + "#agenda")
    feitas, erros = 0, []
    with conectar() as con:
        cur = con.cursor()
        for c in agenda.lista(cur, "c.inicio >= now() AND c.status <> 'cancelada' AND c.google_evento_id IS NULL", ()):
            try:
                agenda.sincronizar_evento(cur, cfg, c)
                feitas += 1
            except checkin.ErroGoogle as e:
                erros.append(str(e))
                break
    flash(f"{feitas} consulta(s) enviada(s) ao Google Agenda." if feitas or not erros else erros[0],
          "aviso" if erros else "")
    return redirect(url_for("configuracao") + "#agenda")


# ---------- check-in semanal (Formulário Google) ----------

@app.route("/checkins")
def checkins():
    cfg = contatos.carregar()
    with conectar() as con:
        cur = con.cursor()
        sem = checkin.lista(cur, "k.paciente_id IS NULL", (), 100)
        recentes = checkin.com_alertas(checkin.lista(cur, "k.paciente_id IS NOT NULL", (), 80))
        cur.execute("SELECT nome FROM paciente ORDER BY nome")
        nomes = [r[0] for r in cur.fetchall()]
    return render_template("checkins.html", sem=sem, recentes=recentes, nomes=nomes, ligado=checkin.configurado(cfg),
                           aviso_email=checkin.aviso_email if checkin.usa_email(cfg) else None)


@app.route("/checkins/buscar", methods=["POST"])
def buscar_checkins():
    try:
        with conectar() as con:
            novas, sem = checkin.sincronizar(con.cursor(), contatos.carregar())
        flash(f"{novas} resposta(s) nova(s)." + (f" {sem} sem paciente identificado: escolha abaixo." if sem else "")
              if novas else "Nenhuma resposta nova.")
    except checkin.ErroGoogle as e:
        flash(str(e), "aviso")
    return redirect(url_for("checkins"))


@app.route("/checkin/<int:cid>/paciente", methods=["POST"])
def checkin_paciente(cid):
    nome = request.form.get("paciente", "")
    with conectar() as con:
        cur = con.cursor()
        cur.execute("SELECT id, nome FROM paciente")
        achados = [i for i, n in cur.fetchall() if norm(n) == norm(nome)]
        if len(achados) != 1:
            flash(f"Não achei um paciente só com o nome “{nome}”. Escolha um nome da lista.", "aviso")
        else:
            cur.execute("UPDATE checkin SET paciente_id = %s WHERE id = %s", (achados[0], cid))
            flash("Check-in ligado ao paciente.")
    return redirect(url_for("checkins"))


@app.route("/checkin/<int:cid>/excluir", methods=["POST"])
def checkin_excluir(cid):
    with conectar() as con:
        con.execute("UPDATE checkin SET excluido = true WHERE id = %s", (cid,))
    flash("Resposta excluída do sistema. No Google ela continua, mas não volta para cá.")
    return redirect(request.form.get("voltar") or url_for("checkins"))


if __name__ == "__main__":
    try:
        conectar().close()
    except psycopg.OperationalError as e:
        sys.exit(f"Não consegui conectar ao banco de dados. O PostgreSQL está ligado?\n{e}")
    print(f"Sistema aberto em http://localhost:{PORTA}  (feche esta janela para desligar)")
    if "--sem-navegador" not in sys.argv:
        webbrowser.open(f"http://localhost:{PORTA}")
    app.run(host="127.0.0.1", port=PORTA)
