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
        raise ErroCloudflare("o nome do projeto só pode ter letras minúsculas, números e hífen (ex.: meu-consultorio)")
    try:
        r = _api(cfg_cf, "GET", f"/accounts/{conta}/pages/projects/{projeto}")
    except ErroCloudflare as e:
        if "not found" not in str(e).lower() and "could not be found" not in str(e).lower():
            raise
        r = _api(cfg_cf, "POST", f"/accounts/{conta}/pages/projects", {"name": projeto, "production_branch": "main"})
    sub = (r.get("result") or {}).get("subdomain") or f"{projeto}.pages.dev"
    return f"https://{sub}"


ICONES = ["icone-192.png", "icone-512.png", "icone-maskable-512.png", "icone-apple-180.png"]


def manifesto_paciente(token):
    """grava p/<token>.webmanifest (o celular instala a página como app, abrindo direto nela) e devolve as
    marcações do cabeçalho. Sem o nome do paciente: este arquivo não é criptografado."""
    import json
    import identidade
    m = {"name": f"{identidade.marca()} · Minha evolução", "short_name": "Minha evolução", "id": f"./{token}",
         "start_url": f"./{token}", "scope": "./", "display": "standalone", "background_color": "#F2F6F6",
         "theme_color": "#12434F", "lang": "pt-BR",
         "icons": [{"src": "/icone-192.png", "sizes": "192x192", "type": "image/png"},
                   {"src": "/icone-512.png", "sizes": "512x512", "type": "image/png"},
                   {"src": "/icone-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}
    arq = SITE / "p" / f"{token}.webmanifest"
    txt = json.dumps(m, ensure_ascii=False)
    if not arq.exists() or arq.read_text(encoding="utf-8") != txt:
        arq.write_text(txt, encoding="utf-8")
    return (f'<link rel="manifest" href="{token}.webmanifest"><meta name="theme-color" content="#12434F">'
            '<link rel="icon" href="/icone-192.png"><link rel="apple-touch-icon" href="/icone-apple-180.png">'
            '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">'
            '<meta name="apple-mobile-web-app-title" content="Minha evolução">')


def preparar_pasta():
    """arquivos fixos do site: página inicial neutra e pedido para não indexar"""
    import html
    import identidade
    (SITE / "p").mkdir(parents=True, exist_ok=True)
    marca = html.escape(identidade.marca())
    fixos = {
        "index.html": f"<!doctype html><meta charset=utf-8><meta name=robots content=noindex><title>{marca}</title>"
                      f"<p style=\"font:16px system-ui;margin:40px\">{marca} · acompanhamento nutricional</p>",
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
    estaticos = Path(__file__).resolve().parent / "static"
    for nome in ICONES:                      # ícones do app (instalar a página no celular)
        origem, arq = estaticos / nome, SITE / nome
        if origem.exists() and (not arq.exists() or arq.read_bytes() != origem.read_bytes()):
            arq.write_bytes(origem.read_bytes())


MARCA_C = SITE.parent / "confirmacao_publicada.txt"     # qual versão do c.html já está no ar


def _html_confirmacao(cfg):
    """página /c do site: lê o link curto (#codigo.assinatura.AAAAMMDDHHMM.nome) e abre a página de confirmação
    do script do Google com os dados completos. O que vai depois do # nem chega ao servidor."""
    import json
    import checkin
    url = (cfg.get("checkin") or {}).get("url") or ""
    if not url:
        return None
    w = checkin.whatsapp_prof(cfg) or ""
    return ("<!doctype html><meta charset=utf-8><meta name=robots content=noindex>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1\"><title>Confirmação de consulta</title>"
            "<p id=m style=\"font:17px system-ui;margin:40px;color:#14444f\">Abrindo a confirmação da sua consulta…</p><script>"
            f"var S={json.dumps(url)},W={json.dumps(w)};"
            "var p=location.hash.slice(1).split('.');"
            "if(p.length>=4&&/^\\d{12}$/.test(p[2])){var d=p[2],dt=new Date(+d.slice(0,4),+d.slice(4,6)-1,+d.slice(6,8)),"
            "D=['domingo','segunda-feira','terça-feira','quarta-feira','quinta-feira','sexta-feira','sábado'],"
            "q=D[dt.getDay()]+', '+d.slice(6,8)+'/'+d.slice(4,6)+' às '+d.slice(8,10)+':'+d.slice(10,12),"
            "n=decodeURIComponent(p.slice(3).join('.'));"
            "location.replace(S+'?cod='+encodeURIComponent(p[0])+'&s='+encodeURIComponent(p[1])+'&n='+encodeURIComponent(n)"
            "+'&q='+encodeURIComponent(q)+'&w='+encodeURIComponent(W));}"
            "else document.getElementById('m').textContent='Este link de confirmação está incompleto. Responda pela mensagem que você recebeu.';"
            "</script>")


def pagina_confirmacao(cfg):
    """grava web/site/c.html (vai no próximo envio); devolve o texto ou None sem o script do Google"""
    html = _html_confirmacao(cfg)
    if html:
        arq = SITE / "c.html"
        SITE.mkdir(parents=True, exist_ok=True)
        if not arq.exists() or arq.read_text(encoding="utf-8") != html:
            arq.write_text(html, encoding="utf-8")
    return html


def confirmacao_curta(cfg):
    """endereço do site se a página /c atual já está no ar (senão o link sai no formato longo do Google)"""
    html = _html_confirmacao(cfg) if configurado(cfg) else None
    try:
        return cfg["cloudflare"]["url"].rstrip("/") if html and MARCA_C.read_text(encoding="utf-8") == _hash(html) else None
    except FileNotFoundError:
        return None


def _hash(t):
    import hashlib
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def enviar(cfg):
    """envia a pasta web/site para o Cloudflare (só o que mudou). Demora alguns segundos."""
    c = cfg["cloudflare"]
    if not WRANGLER.exists():
        raise ErroCloudflare("a ferramenta do Cloudflare não está instalada (ferramentas/cloudflare)")
    preparar_pasta()
    html_c = pagina_confirmacao(cfg)
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
    if html_c:
        MARCA_C.write_text(_hash(html_c), encoding="utf-8")     # a partir daqui, os links de confirmação saem curtos
    return r.stdout
