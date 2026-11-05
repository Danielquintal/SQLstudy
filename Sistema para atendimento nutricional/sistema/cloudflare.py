"""Publicação das páginas dos pacientes no Cloudflare Pages, feita pelo próprio sistema (sem pedir ao Claude).

  - Configuração (sistema/config.json, chave "cloudflare"): account_id, token (API token com permissão
    "Cloudflare Pages: Edit"), projeto (nome do projeto no Pages) e url (https://<projeto>.pages.dev).
  - Pasta do site: web/site/ — index.html neutro, robots.txt e _headers (não indexar) e p/<token>.html, uma página por
    paciente, com endereço aleatório e longo (não dá para adivinhar nem listar). As páginas vão criptografadas com o
    login do paciente (scripts/acesso_pagina.py).
  - Cada publicação envia a pasta inteira com a ferramenta oficial (Wrangler, em ferramentas/cloudflare), que só
    transfere o que mudou.
"""
import json
import os
import re
import subprocess
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parent.parent
SITE = RAIZ / "web" / "site"
WRANGLER = RAIZ / "ferramentas" / "cloudflare" / "node_modules" / ".bin" / ("wrangler.cmd" if os.name == "nt" else "wrangler")
API = "https://api.cloudflare.com/client/v4"
_trava = threading.Lock()   # um envio por vez


class ErroCloudflare(Exception):
    pass


def configurado(cfg):
    c = cfg.get("cloudflare") or {}
    return bool(c.get("account_id") and c.get("token") and c.get("projeto") and c.get("url"))


def _api(cfg_cf, metodo, caminho, dados=None):
    req = Request(f"{API}{caminho}", method=metodo, data=json.dumps(dados).encode() if dados is not None else None,
                  headers={"Authorization": f"Bearer {cfg_cf['token']}", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        try:
            erro = json.loads(e.read().decode())
            msg = "; ".join(x.get("message", "") for x in erro.get("errors", [])) or str(e)
        except ValueError:
            msg = str(e)
        raise ErroCloudflare(msg) from None
    except URLError as e:
        raise ErroCloudflare(f"sem conexão com o Cloudflare ({e.reason})") from None


def conectar(cfg_cf):
    """confere a chave, cria o projeto no Pages se ainda não existir e devolve o endereço do site"""
    conta, projeto = cfg_cf["account_id"].strip(), cfg_cf["projeto"].strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,56}[a-z0-9]", projeto):
        raise ErroCloudflare("o nome do projeto só pode ter letras minúsculas, números e hífen (ex.: res-athleticae)")
    try:
        r = _api(cfg_cf, "GET", f"/accounts/{conta}/pages/projects/{projeto}")
    except ErroCloudflare as e:
        if "not found" not in str(e).lower() and "could not be found" not in str(e).lower():
            raise
        r = _api(cfg_cf, "POST", f"/accounts/{conta}/pages/projects", {"name": projeto, "production_branch": "main"})
    sub = (r.get("result") or {}).get("subdomain") or f"{projeto}.pages.dev"
    return f"https://{sub}"


def preparar_pasta():
    """arquivos fixos do site: página inicial neutra e pedido para não indexar"""
    (SITE / "p").mkdir(parents=True, exist_ok=True)
    fixos = {
        "index.html": "<!doctype html><meta charset=utf-8><meta name=robots content=noindex><title>Res Athleticae</title>"
                      "<p style=\"font:16px system-ui;margin:40px\">Res Athleticae · acompanhamento nutricional</p>",
        "robots.txt": "User-agent: *\nDisallow: /\n",
        # endereço que não existe: "não encontrado" (sem isso o Cloudflare devolve a página inicial)
        "404.html": "<!doctype html><meta charset=utf-8><meta name=robots content=noindex><title>Página não encontrada</title>"
                    "<p style=\"font:16px system-ui;margin:40px\">Página não encontrada. Confira o link que seu nutricionista enviou.</p>",
        "_headers": "/*\n  X-Robots-Tag: noindex, nofollow\n  Referrer-Policy: no-referrer\n",
    }
    for nome, txt in fixos.items():
        arq = SITE / nome
        if not arq.exists() or arq.read_text(encoding="utf-8") != txt:
            arq.write_text(txt, encoding="utf-8")


def enviar(cfg):
    """envia a pasta web/site para o Cloudflare (só o que mudou). Demora alguns segundos."""
    c = cfg["cloudflare"]
    if not WRANGLER.exists():
        raise ErroCloudflare("a ferramenta do Cloudflare não está instalada (ferramentas/cloudflare)")
    preparar_pasta()
    amb = dict(os.environ, CLOUDFLARE_API_TOKEN=c["token"], CLOUDFLARE_ACCOUNT_ID=c["account_id"],
               WRANGLER_SEND_METRICS="false", CI="1")
    with _trava:
        r = subprocess.run([str(WRANGLER), "pages", "deploy", str(SITE), "--project-name", c["projeto"],
                            "--branch", "main", "--commit-dirty=true"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=amb, timeout=300,
                           cwd=str(WRANGLER.parent.parent.parent))
    if r.returncode != 0:
        # o motivo vem na linha seguinte ao primeiro "[ERROR]" (ex.: "Authentication failed (status: 400)")
        linhas = [re.sub(r"\x1b\[[0-9;]*m", "", l).strip() for l in (r.stdout + "\n" + r.stderr).splitlines()]
        linhas = [l for l in linhas if l]
        i = next((k for k, l in enumerate(linhas) if "[ERROR]" in l), None)
        motivo = " ".join(linhas[i:i + 2]).replace("X [ERROR] ", "") if i is not None else (linhas[-1] if linhas else "o envio falhou")
        if "Authentication" in motivo or "9106" in motivo or "10000" in motivo:
            motivo = "a chave (token) foi recusada: confira se ela tem a permissão Cloudflare Pages · Editar e se o ID da conta está certo"
        raise ErroCloudflare(motivo[:300])
    return r.stdout
