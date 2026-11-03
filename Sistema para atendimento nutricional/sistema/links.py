"""Links publicados (web/artefatos.json) e pedidos de publicação (web/pedidos.json).

O sistema não publica sozinho: ele anota o pedido e o Claude publica quando você pedir
"publique os links pedidos" (ver scripts/publicar_pedidos.py).
"""
import json, re, unicodedata
from datetime import datetime
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
ARTEFATOS = WEB / "artefatos.json"
PEDIDOS = WEB / "pedidos.json"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _ler(arq, vazio):
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return vazio


def _gravar(arq, dados):
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def artefato(pid, nome):
    """{"url", "publicado_em", ...} do paciente, achado pelo número e, nos links antigos, pelo nome"""
    pacs = _ler(ARTEFATOS, {"pacientes": {}})["pacientes"]
    por_id = [v for v in pacs.values() if v.get("id") == pid]
    if por_id:
        return por_id[0]
    return next((v for n, v in pacs.items() if "id" not in v and norm(n) == norm(nome)), None)


def todos_artefatos():
    return _ler(ARTEFATOS, {"pacientes": {}})["pacientes"]


def pedidos():
    return _ler(PEDIDOS, {"pedidos": []})["pedidos"]


def pedido(pid):
    return next((p for p in pedidos() if p["id"] == pid), None)


def pedir(pid, nome, motivo):
    """anota (ou renova) o pedido de publicar o link do paciente"""
    lista = [p for p in pedidos() if p["id"] != pid]
    lista.append({"id": pid, "nome": nome, "motivo": motivo, "pedido_em": datetime.now().isoformat(timespec="minutes")})
    _gravar(PEDIDOS, {"_sobre": "Links a publicar pelo Claude. Peça: publique os links pedidos.", "pedidos": lista})


def cancelar(pid):
    _gravar(PEDIDOS, {"_sobre": "Links a publicar pelo Claude. Peça: publique os links pedidos.",
                      "pedidos": [p for p in pedidos() if p["id"] != pid]})


def vincular(pid, nome):
    """grava o número do paciente no link achado pelo nome, para o link continuar dele se o nome mudar"""
    dados = _ler(ARTEFATOS, {"pacientes": {}})
    for n, v in dados["pacientes"].items():
        if "id" not in v and norm(n) == norm(nome):
            v["id"] = pid
            _gravar(ARTEFATOS, dados)
            return


def concluir(pid, nome, url):
    """grava o link publicado e tira o pedido da fila"""
    dados = _ler(ARTEFATOS, {"pacientes": {}})
    pacs = dados["pacientes"]
    chave = next((n for n, v in pacs.items() if v.get("id") == pid), None) \
        or next((n for n, v in pacs.items() if "id" not in v and norm(n) == norm(nome)), None) or nome
    info = pacs.get(chave, {"plano": None})
    info.update({"id": pid, "url": url, "publicado_em": datetime.now().isoformat(timespec="minutes")})
    pacs[chave] = info
    _gravar(ARTEFATOS, dados)
    cancelar(pid)
