"""Prepara as páginas dos links pedidos no sistema e registra os links publicados.

Uso (feito pelo Claude quando você pede "publique os links pedidos"):
  python scripts/publicar_pedidos.py                     gera web/paginas/<nome>.html de cada pedido e lista
                                                          id, arquivo e link atual (vazio = link novo)
  python scripts/publicar_pedidos.py --concluir ID URL   grava o link em web/artefatos.json e tira o pedido da fila
Publicar sempre no link atual quando ele existir, para o paciente continuar com o mesmo endereço.
"""
import json, sys
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "sistema"))
from atualizar_paciente import CONEXAO, PAGINAS, TEMPLATE, avaliacoes_do_banco, para_app_naive
from montar_pagina import montar
from plano import plano_do_banco
from planilha_paciente import safe_name
import checkin, contatos, links, reds


def preparar():
    fila = links.pedidos()
    if not fila:
        print("Nenhum link pedido.")
        return
    PAGINAS.mkdir(parents=True, exist_ok=True)
    cfg = contatos.carregar()
    with psycopg.connect(CONEXAO) as con:
        cur = con.cursor()
        for p in fila:
            cur.execute("SELECT nome FROM paciente WHERE id = %s", (p["id"],))
            r = cur.fetchone()
            if not r:
                print(json.dumps({"id": p["id"], "erro": "paciente não existe mais"}, ensure_ascii=False))
                continue
            nome = r[0]
            avs = [para_app_naive(a) for a in avaliacoes_do_banco(cur, p["id"])]
            plano, link_ck = plano_do_banco(cur, p["id"]), checkin.link_paciente(cur, cfg, p["id"], nome)
            if not (avs or plano or link_ck):
                print(json.dumps({"id": p["id"], "nome": nome, "erro": "sem avaliação, plano ou check-in"}, ensure_ascii=False))
                continue
            cur.execute("SELECT count(*) FROM paciente WHERE id <> %s AND lower(nome) = lower(%s)", (p["id"], nome))
            homonimo = cur.fetchone()[0] > 0
            sufixo = f" ({p['id']})" if homonimo else ""
            arq = PAGINAS / f"{safe_name(nome)}{sufixo}.html"
            montar(str(TEMPLATE), nome, avs, plano, str(arq), link_ck,
                   {"checkins": checkin.para_pagina(cur, p["id"]), "reds": reds.para_pagina(cur, p["id"])})
            atual = links.artefato(p["id"], nome)
            print(json.dumps({"id": p["id"], "nome": nome, "arquivo": str(arq), "url_atual": atual and atual.get("url"),
                              "motivo": p["motivo"]}, ensure_ascii=False))


def concluir(pid, url):
    with psycopg.connect(CONEXAO) as con:
        r = con.execute("SELECT nome FROM paciente WHERE id = %s", (pid,)).fetchone()
    if not r:
        sys.exit(f"Paciente {pid} não existe.")
    links.concluir(pid, r[0], url)
    print(f"{r[0]}: {url} registrado")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--concluir":
        concluir(int(sys.argv[2]), sys.argv[3])
    else:
        preparar()
