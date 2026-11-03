"""Sistema local: pacientes e avaliações no navegador, gravando direto no banco app_naive.

Uso:  python sistema/app.py   (ou dois cliques em "Abrir sistema.bat")  ->  http://localhost:5000
Só atende este computador (127.0.0.1). Depois de gravar uma avaliação, gera de novo a planilha e a página do paciente.
"""
import json, os, sys, webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse

import psycopg
from flask import Flask, abort, flash, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from atualizar_paciente import (CONEXAO, PAGINAS, TEMPLATE, achar_planilha, avaliacoes_do_banco, converter,
                                mostrar, norm, para_app_naive)
from calculos import calcular
from campos import CAMPOS, TEXTO
from montar_pagina import gerar_html, montar
from planilha_paciente import SECTIONS, build, safe_name
import contatos
import links
import plano as planos
import plano_app_naive
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
                   "whatsapp_bloqueado"]


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
            n = len(contatos.pendencias(con.cursor(), contatos.carregar()))
    except psycopg.Error:
        n = 0
    return {"n_contatos": n, "n_pedidos": len(links.pedidos())}


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
    avs = [para_app_naive(r) for r in banco]
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
    montar(str(TEMPLATE), nome, avs, planos.plano_do_banco(cur, pid), str(PAGINAS / f"{safe_name(nome)}.html"))
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
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        avs = avaliacoes_do_banco(cur, pid)
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
    cfg = contatos.carregar()
    extra = {"{link_evolucao}": url,
             "{data_avaliacao}": ultima["data_avaliacao"].strftime("%d/%m/%Y") if ultima else None}
    # mensagens que fazem sentido para este paciente agora
    tipos = (["livre"] + (["evolucao"] if url and ultima else [])
             + (["retorno"] if p["retorno_em"] and p["retorno_em"] >= date.today() else []))
    mensagens = [(t, contatos.TITULOS[t], contatos.mensagem(cfg, t, p, extra)) for t in tipos]
    return render_template("paciente.html", p=p, avs=list(reversed(avs)), primeira=primeira, ultima=ultima,
                           url=url, art=art, pedido=links.pedido(pid), historico=historico, mensagens=mensagens,
                           planos=planos_paciente,
                           tem_whatsapp=bool(contatos.telefone_whatsapp(p["telefone"])), titulos=contatos.TITULOS)


@app.route("/paciente/<int:pid>/evolucao")
def evolucao(pid):
    with conectar() as con:
        cur = con.cursor()
        p = buscar_paciente(cur, pid)
        avs = [para_app_naive(r) for r in avaliacoes_do_banco(cur, pid)]
        plano = planos.plano_do_banco(cur, pid)
    if not avs:
        flash("Este paciente ainda não tem avaliações.")
        return redirect(url_for("paciente", pid=pid))
    return gerar_html(str(TEMPLATE), p["nome"], avs, plano)


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
    return render_template("avaliacao.html", p=p, aid=aid, form=form, erros=erros, secoes=SECOES, texto=TEXTO,
                           ops=ops, calculados=CALCULADOS)


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
    calc = calcular(valores, p["genero"], p["data_nascimento"], d or date.today())
    return {k: v if isinstance(v, str) else numero(v) for k, v in calc.items()}


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
    # PDF do App Naive vira a dieta interativa; qualquer outro PDF (ou se pedir) entra página por página
    lido = None if request.form.get("como_paginas") else plano_app_naive.ler(dados)
    if lido:
        titulo = titulo or lido["titulo"]
        prescrito = prescrito or datetime.strptime(lido["prescrito"], "%d/%m/%Y").date()
        lido.update(titulo=titulo, prescrito=prescrito.strftime("%d/%m/%Y"))
        plano, resumo = lido, f"lido do App Naive: {len(lido['refeicoes'])} refeições"
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
                  "refeicoes": [{"hora": h, "nome": n, "obs": "", "itens": []}
                                for h, n in (("07:00", "Café da manhã"), ("10:00", "Lanche da manhã"), ("12:30", "Almoço"),
                                             ("16:00", "Lanche da tarde"), ("20:00", "Jantar"))]}
    base = {"imc": round(imc, 1) if imc else None,
            "data_avaliacao": ultima["data_avaliacao"].strftime("%d/%m/%Y") if ultima else None}
    return render_template("editor_plano.html", p=p, plid=plid, editor=editor, alimentos=alimentos, base=base,
                           formulas=nutricao.FORMULAS, grupos=grupos)


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
    return render_template("perfil.html", p={"id": pid, "nome": atual["nome"]}, form=form, erros=erros, ufs=UFS,
                           n_avs=n_avs)


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
            igual = (str(antes) == str(val)) if isinstance(val, str) or antes is None or isinstance(antes, str) \
                else abs(float(antes) - float(val)) < 0.05
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
        cur.execute("UPDATE paciente SET retorno_em = %s, whatsapp_bloqueado = %s, telefone = %s WHERE id = %s",
                    (retorno, bool(f.get("whatsapp_bloqueado")),
                     " ".join(f.get("telefone", "").split()) or None, pid))
    flash("Acompanhamento salvo.")
    return redirect(url_for("paciente", pid=pid) + "#acompanhamento")


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
    return render_template("contatos.html", itens=itens, feitos=feitos, agenda=agenda, titulos=contatos.TITULOS,
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
        contatos.salvar(cfg)
        flash("Configuração salva.")
        return redirect(url_for("configuracao"))
    return render_template("configuracao.html", cfg=cfg, titulos=contatos.TITULOS, variaveis=contatos.VARIAVEIS,
                           padrao=contatos.PADRAO["mensagens"])


if __name__ == "__main__":
    try:
        conectar().close()
    except psycopg.OperationalError as e:
        sys.exit(f"Não consegui conectar ao banco app_naive. O PostgreSQL está ligado?\n{e}")
    print(f"Sistema aberto em http://localhost:{PORTA}  (feche esta janela para desligar)")
    if "--sem-navegador" not in sys.argv:
        webbrowser.open(f"http://localhost:{PORTA}")
    app.run(host="127.0.0.1", port=PORTA)
