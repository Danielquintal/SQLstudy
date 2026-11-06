"""Acesso ao sistema de fora deste computador, pelo túnel do Cloudflare (Cloudflare Tunnel + Cloudflare Access).

  - O sistema continua rodando aqui (localhost:5000). O túnel (ferramentas/cloudflared/cloudflared.exe) liga este
    computador ao Cloudflare por uma conexão de saída: nenhuma porta fica aberta no roteador.
  - No Cloudflare: só do Brasil e verificação contra robôs (regras do WAF).
  - Aqui: senha do sistema + código de 6 números do app do celular (se ligado), pedidos a quem chega pelo túnel.
    A entrada vale 12 horas. Quem usa o próprio computador (localhost) continua entrando direto.
  - Config (sistema/config.json, chave "remoto"): dominio (ex.: sistema.seudominio.com.br), token_tunel (o token do
    túnel criado no painel do Cloudflare) e senha_hash (nunca a senha em si).
"""
import atexit
import base64
import hashlib
import hmac
import os
import struct
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

from werkzeug.security import check_password_hash, generate_password_hash

RAIZ = Path(__file__).resolve().parent.parent
CLOUDFLARED = RAIZ / "ferramentas" / "cloudflared" / "cloudflared.exe"
# túnel criado aqui pela ferramenta (sem o painel do Zero Trust): configuração e credenciais nesta pasta
TUNEL_CONFIG = RAIZ / "ferramentas" / "cloudflared" / "config.yml"
LOG = RAIZ / "web" / "tunel.log"
LOCAIS = ("localhost", "127.0.0.1")
_processo = None
_falhas = {}            # ip -> [tentativas erradas, bloqueado até]
LIMITE, ESPERA = 5, 5 * 60


def eh_remoto(request):
    """pedido que veio pelo túnel (o Cloudflare manda o IP real no Cf-Connecting-Ip) ou por outro endereço"""
    return bool(request.headers.get("Cf-Connecting-Ip")) or (request.host.split(":")[0] not in LOCAIS)


def ip(request):
    return request.headers.get("Cf-Connecting-Ip") or request.remote_addr or "?"


def definir_senha(cfg, senha):
    cfg["remoto"]["senha_hash"] = generate_password_hash(senha)


def bloqueado(quem):
    f = _falhas.get(quem)
    return bool(f and f[1] > time.time())


# ---------- código do celular (2ª etapa): TOTP, o mesmo do Google Authenticator / Microsoft Authenticator ----------
_ultimo_passo = [0]          # o mesmo código não vale duas vezes


def novo_segredo():
    return base64.b32encode(os.urandom(20)).decode("ascii")


def _totp(segredo, passo):
    d = hmac.new(base64.b32decode(segredo), struct.pack(">Q", passo), hashlib.sha1).digest()
    o = d[-1] & 15
    return f"{(struct.unpack('>I', d[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def codigo_confere(segredo, codigo):
    """aceita o código de agora e o de 30 s antes/depois (relógio do celular um pouco diferente)"""
    codigo = "".join(c for c in str(codigo or "") if c.isdigit())
    if not segredo or len(codigo) != 6:
        return False
    agora = int(time.time()) // 30
    for passo in (agora - 1, agora, agora + 1):
        if passo > _ultimo_passo[0] and hmac.compare_digest(_totp(segredo, passo), codigo):
            _ultimo_passo[0] = passo
            return True
    return False


def endereco_app(segredo):
    """o que vai no QR code para o app do celular"""
    import identidade
    emissor = quote(identidade.marca())
    return f"otpauth://totp/{emissor}:sistema?secret={segredo}&issuer={emissor}&digits=6&period=30"


def tem_celular(cfg):
    return bool((cfg.get("remoto") or {}).get("totp_segredo"))


def senha_local(cfg):
    """opção "Pedir senha também neste computador" (precisa da senha do sistema criada)"""
    r = cfg.get("remoto") or {}
    return bool(r.get("senha_local") and r.get("senha_hash"))


def conferir(cfg, quem, senha, codigo=""):
    """True se a senha (e, se ligado, o código do celular) confere; conta as erradas e trava o IP por 5 minutos
    depois de 5 seguidas. Vale para quem vem de fora e, com a opção ligada, para este computador."""
    if bloqueado(quem):
        return False
    h = cfg["remoto"].get("senha_hash")
    if (h and senha and check_password_hash(h, senha)
            and (not tem_celular(cfg) or codigo_confere(cfg["remoto"]["totp_segredo"], codigo))):
        _falhas.pop(quem, None)
        return True
    f = _falhas.setdefault(quem, [0, 0])
    f[0] += 1
    if f[0] >= LIMITE:
        f[:] = [0, time.time() + ESPERA]
    return False


def _tem_tunel(r):
    """token do painel (Zero Trust) ou túnel criado aqui (tunel_nome + config.yml)"""
    return bool(r.get("token_tunel") or (r.get("tunel_nome") and TUNEL_CONFIG.exists()))


def configurado(cfg):
    r = cfg.get("remoto") or {}
    return bool(_tem_tunel(r) and r.get("senha_hash") and CLOUDFLARED.exists())


def iniciar_tunel(cfg):
    """liga o túnel junto com o sistema (e desliga quando o sistema fecha). Só com token e senha definidos."""
    global _processo
    if not configurado(cfg) or (_processo and _processo.poll() is None):
        return False
    LOG.parent.mkdir(parents=True, exist_ok=True)
    saida = open(LOG, "a", encoding="utf-8")
    r = cfg["remoto"]
    comando = ([str(CLOUDFLARED), "tunnel", "--no-autoupdate", "run", "--token", r["token_tunel"]] if r.get("token_tunel")
               else [str(CLOUDFLARED), "tunnel", "--no-autoupdate", "--config", str(TUNEL_CONFIG), "run", r["tunel_nome"]])
    _processo = subprocess.Popen(comando,
                                 stdout=saida, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    atexit.register(parar_tunel)
    return True


def parar_tunel():
    global _processo
    if _processo and _processo.poll() is None:
        _processo.terminate()
    _processo = None


def tunel_ligado():
    return bool(_processo and _processo.poll() is None)


def ultimas_linhas(n=6):
    try:
        return LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-n:]
    except OSError:
        return []
