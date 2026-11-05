"""Publicar a página do paciente pelo próprio sistema (Cloudflare Pages), sem a fila do Claude.

publicar(cfg, [pid, ...])       gera as páginas (criptografadas, com login) em web/site/p/<token>.html, envia ao
                                Cloudflare e grava o link em web/artefatos.json (o link antigo do claude.ai fica em url_claude)
publicar_depois(cfg, pid, nome) o mesmo, em segundo plano (atualização automática depois de salvar avaliação, plano...)
remover(cfg, pid)               tira a página do site (paciente excluído)
estado()                        última publicação e último erro (para mostrar na tela)
"""
import json
import secrets
import threading
from datetime import datetime
from pathlib import Path

import psycopg

import checkin
import cloudflare
import exames
import links
from atualizar_paciente import CONEXAO, TEMPLATE, avaliacoes_do_banco, para_pagina
from montar_pagina import montar
from plano import plano_do_banco

ESTADO = Path(__file__).resolve().parent.parent / "web" / "site_estado.json"


def _token(cur, pid):
    cur.execute("SELECT pagina_token FROM paciente WHERE id = %s", (pid,))
    r = cur.fetchone()
    if r and r[0]:
        return r[0]
    t = secrets.token_urlsafe(18).replace("_", "x").replace("-", "y")   # 24 letras e números
    cur.execute("UPDATE paciente SET pagina_token = %s WHERE id = %s", (t, pid))
    return t


def _gravar_estado(**kv):
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e = {}
    e.update(kv)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gerar(cur, cfg, pid):
    """grava web/site/p/<token>.html; devolve (nome, url) ou (nome, None) se não há o que mostrar"""
    cur.execute("SELECT nome FROM paciente WHERE id = %s", (pid,))
    r = cur.fetchone()
    if not r:
        return None, None
    nome = r[0]
    avs = [para_pagina(a) for a in avaliacoes_do_banco(cur, pid)]
    plano, link_ck = plano_do_banco(cur, pid), checkin.link_paciente(cur, cfg, pid, nome)
    extras = exames.extras_pagina(cur, pid)
    if not (avs or plano or link_ck or exames.tem_extras(extras)):
        return nome, None
    token = _token(cur, pid)
    cloudflare.preparar_pasta()
    montar(str(TEMPLATE), nome, avs, plano, str(cloudflare.SITE / "p" / f"{token}.html"), link_ck, extras)
    return nome, f"{cfg['cloudflare']['url'].rstrip('/')}/p/{token}"


def publicar(cfg, pids):
    """gera e publica; devolve [(pid, nome, url)] dos publicados. Levanta ErroCloudflare se o envio falhar."""
    feitos = []
    with psycopg.connect(CONEXAO) as con:
        cur = con.cursor()
        for pid in pids:
            nome, url = _gerar(cur, cfg, pid)
            if url:
                feitos.append((pid, nome, url))
        con.commit()
    if not feitos:
        return []
    try:
        cloudflare.enviar(cfg)
    except cloudflare.ErroCloudflare as e:
        _gravar_estado(erro=str(e), erro_em=datetime.now().isoformat(timespec="minutes"))
        raise
    for pid, nome, url in feitos:
        atual = links.artefato(pid, nome)
        if atual and atual.get("url") and "claude.ai" in atual["url"]:
            links.guardar_url_antiga(pid, nome, atual["url"])
        links.concluir(pid, nome, url)
    _gravar_estado(ultima=datetime.now().isoformat(timespec="minutes"), ultimos=[n for _, n, _ in feitos][:20], erro=None)
    return feitos


def publicar_depois(cfg, pid, nome):
    """atualiza o link em segundo plano; se falhar, o pedido fica na fila (e o erro aparece em Links)"""
    def rodar():
        try:
            publicar(cfg, [pid])
        except Exception as e:   # noqa: BLE001 — qualquer falha vira pedido na fila, para não perder a atualização
            links.pedir(pid, nome, "atualizar")
            _gravar_estado(erro=f"{nome}: {e}", erro_em=datetime.now().isoformat(timespec="minutes"))
    threading.Thread(target=rodar, daemon=True).start()


def remover(cfg, pid, token):
    """paciente excluído: apaga a página do site e envia de novo (em segundo plano)"""
    if not token:
        return
    arq = cloudflare.SITE / "p" / f"{token}.html"
    if arq.exists():
        arq.unlink()
        threading.Thread(target=lambda: cloudflare.enviar(cfg), daemon=True).start()
