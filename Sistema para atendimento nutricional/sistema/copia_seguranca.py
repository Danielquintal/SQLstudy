"""Cópia de segurança automática: banco de dados + configuração, uma vez por dia, enquanto o sistema está aberto.

  - Cada cópia é um .zip com o banco inteiro (pg_dump, formato "custom", que já inclui os PDFs dos planos) e os
    arquivos que não ficam no banco (sistema/config.json e os estados dos links em web/*.json).
  - Neste computador: pasta _copias/ (as 30 mais novas). Serve para voltar atrás num erro de digitação ou exclusão.
  - Fora do computador: a mesma cópia, trancada com AES-256-GCM pela "senha das cópias", vai para a pasta do
    OneDrive (que sobe sozinha para a nuvem). Serve se o computador estragar ou for roubado. Sem a senha, não vai.
    A senha fica em sistema/config.json (precisa dela para trancar sem você); guarde-a também fora do computador.
  - Para abrir/restaurar: scripts/restaurar_copia.py.
"""
import glob
import io
import json
import os
import subprocess
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_LOCAL = RAIZ / "_copias"
ESTADO = PASTA_LOCAL / "estado.json"
EXTRAS = ["sistema/config.json", "sistema/identidade.json", "sistema/licenca.chave", "sistema/licenca_estado.json",
          "ferramentas/licenca/chave_privada.pem", "ferramentas/licenca/emitidas.json",
          "web/artefatos.json", "web/pedidos.json", "web/site_estado.json"]
MANTER = 30
INTERVALO_H = 20          # faz outra se a última tiver mais de 20 horas
MAGICO = b"RESCOPIA1"     # cabeçalho do arquivo trancado: MAGICO + sal(16) + nonce(12) + conteúdo
ITERACOES = 600_000
_trava = threading.Lock()


class ErroCopia(Exception):
    pass


# ---------- onde ----------

def pasta_nuvem(cfg):
    p = (cfg.get("copia") or {}).get("pasta_nuvem") or ""
    if p:
        return Path(p)
    od = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    import identidade
    return Path(od) / f"{identidade.marca()} - copias de seguranca" if od and Path(od).is_dir() else None


def pg_dump():
    achados = sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"),
                     key=lambda s: int(Path(s).parts[3]) if Path(s).parts[3].isdigit() else 0)
    if achados:
        return achados[-1]
    raise ErroCopia("não achei o pg_dump.exe (ferramenta do PostgreSQL) em C:\\Program Files\\PostgreSQL")


# ---------- trancar / destrancar ----------

def _chave(senha, sal):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    return PBKDF2HMAC(hashes.SHA256(), 32, sal, ITERACOES).derive(senha.encode("utf-8"))


def trancar(dados, senha):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    sal, nonce = os.urandom(16), os.urandom(12)
    return MAGICO + sal + nonce + AESGCM(_chave(senha, sal)).encrypt(nonce, dados, MAGICO)


def destrancar(dados, senha):
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not dados.startswith(MAGICO):
        raise ErroCopia("este arquivo não é uma cópia trancada do sistema")
    n = len(MAGICO)
    sal, nonce, corpo = dados[n:n + 16], dados[n + 16:n + 28], dados[n + 28:]
    try:
        return AESGCM(_chave(senha, sal)).decrypt(nonce, corpo, MAGICO)
    except InvalidTag:
        raise ErroCopia("senha errada (ou o arquivo foi danificado)") from None


# ---------- estado ----------

def estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _gravar_estado(**mudou):
    e = estado()
    e.update(mudou)
    PASTA_LOCAL.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")
    return e


def _limpar(pasta, padrao):
    arqs = sorted(pasta.glob(padrao), key=lambda a: a.name)
    for velho in arqs[:-MANTER]:
        try:
            velho.unlink()
        except OSError:
            pass


# ---------- fazer ----------

def fazer(cfg, conexao):
    """faz uma cópia agora; devolve um resumo. Erros viram ErroCopia (e ficam anotados no estado)."""
    if not _trava.acquire(blocking=False):
        raise ErroCopia("já tem uma cópia sendo feita agora")
    try:
        quando = datetime.now()
        nome = f"copia_{quando:%Y-%m-%d_%H%M}"
        try:
            r = subprocess.run([pg_dump(), "--format=custom", "--no-owner", f"--dbname={conexao}"],
                               capture_output=True, timeout=600,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ErroCopia(f"o pg_dump não rodou: {e}") from None
        if r.returncode != 0 or not r.stdout:
            raise ErroCopia("o pg_dump falhou: " + r.stderr.decode("utf-8", "replace").strip()[-300:])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("banco.dump", r.stdout)
            for rel in EXTRAS:
                p = RAIZ / rel
                if p.exists():
                    z.write(p, rel)
            z.writestr("LEIA-ME.txt", f"Cópia de segurança do sistema {__import__('identidade').marca()}, feita em {quando:%d/%m/%Y %H:%M}.\n"
                                      "banco.dump = banco atendimento_nutricional (restaure com scripts/restaurar_copia.py\n"
                                      "ou: pg_restore --clean --if-exists -d atendimento_nutricional banco.dump).\n")
        dados = buf.getvalue()
        PASTA_LOCAL.mkdir(parents=True, exist_ok=True)
        (PASTA_LOCAL / f"{nome}.zip").write_bytes(dados)
        _limpar(PASTA_LOCAL, "copia_*.zip")
        resumo = {"ultima": quando.isoformat(timespec="seconds"), "tamanho_kb": round(len(dados) / 1024),
                  "erro": "", "nuvem": "", "aviso_nuvem": ""}
        senha, destino = (cfg.get("copia") or {}).get("senha") or "", pasta_nuvem(cfg)
        if not senha:
            resumo["aviso_nuvem"] = "sem a senha das cópias, a cópia ficou só neste computador"
        elif not destino:
            resumo["aviso_nuvem"] = "não achei a pasta do OneDrive; a cópia ficou só neste computador"
        else:
            try:
                destino.mkdir(parents=True, exist_ok=True)
                (destino / f"{nome}.rescopia").write_bytes(trancar(dados, senha))
                _limpar(destino, "copia_*.rescopia")
                resumo["nuvem"] = resumo["ultima"]
            except OSError as e:
                resumo["aviso_nuvem"] = f"não consegui gravar no OneDrive: {e}"
        _gravar_estado(**resumo)
        return resumo
    except Exception as e:   # noqa: BLE001 — qualquer falha fica anotada para aparecer na Configuração
        _gravar_estado(erro=str(e), erro_em=datetime.now().isoformat(timespec="seconds"))
        if isinstance(e, ErroCopia):
            raise
        raise ErroCopia(str(e)) from e
    finally:
        _trava.release()


def atrasada():
    u = estado().get("ultima")
    try:
        return not u or (datetime.now() - datetime.fromisoformat(u)).total_seconds() > INTERVALO_H * 3600
    except ValueError:
        return True


def iniciar_automatico(carregar_cfg, conexao):
    """roda em segundo plano: confere de hora em hora e faz a cópia quando a última passou de 20 horas"""
    def laco():
        time.sleep(60)       # deixa o sistema abrir primeiro
        while True:
            if atrasada():
                try:
                    fazer(carregar_cfg(), conexao)
                except Exception:   # noqa: BLE001 — anotado no estado; tenta de novo na próxima hora
                    pass
            time.sleep(3600)
    threading.Thread(target=laco, daemon=True, name="copia-seguranca").start()
