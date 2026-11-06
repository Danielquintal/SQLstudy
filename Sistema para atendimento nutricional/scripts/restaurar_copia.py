"""Abre uma cópia de segurança do sistema (feita por sistema/copia_seguranca.py) e restaura o banco.

  python scripts/restaurar_copia.py ARQUIVO [--banco NOME] [--extrair PASTA]

  - ARQUIVO: um .zip de _copias/ ou um .rescopia do OneDrive (pede a senha das cópias).
  - Por segurança, restaura num banco SEPARADO (padrão: atendimento_nutricional_restaurado), para conferir antes.
    Só com --banco atendimento_nutricional ele sobrescreve o banco do sistema (feche o sistema antes; pede confirmação).
  - --extrair PASTA: só tira os arquivos do pacote (banco.dump, config.json...) para a pasta, sem restaurar.
"""
import argparse
import getpass
import io
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "sistema"))
sys.path.insert(0, str(RAIZ / "scripts"))
import copia_seguranca as cs  # noqa: E402

PRINCIPAL = "atendimento_nutricional"


def abrir(arquivo, senha=None):
    dados = Path(arquivo).read_bytes()
    if dados.startswith(cs.MAGICO):
        dados = cs.destrancar(dados, senha if senha is not None else getpass.getpass("Senha das cópias: "))
    return zipfile.ZipFile(io.BytesIO(dados))


def ferramenta(nome):
    return str(Path(cs.pg_dump()).with_name(nome))


def restaurar(z, banco, conexao_base):
    dump = z.read("banco.dump")
    base = " ".join(p for p in conexao_base.split() if not p.startswith("dbname="))
    if banco != PRINCIPAL:
        subprocess.run([ferramenta("dropdb.exe"), "--if-exists", f"--maintenance-db={base} dbname=postgres", banco], check=True)
        subprocess.run([ferramenta("createdb.exe"), f"--maintenance-db={base} dbname=postgres", banco], check=True)
    r = subprocess.run([ferramenta("pg_restore.exe"), "--clean", "--if-exists", "--no-owner", "--exit-on-error",
                        f"--dbname={base} dbname={banco}"], input=dump)
    if r.returncode != 0:
        sys.exit("A restauração falhou (mensagens acima).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("arquivo")
    ap.add_argument("--banco", default=PRINCIPAL + "_restaurado")
    ap.add_argument("--extrair")
    a = ap.parse_args()
    try:
        z = abrir(a.arquivo)
    except cs.ErroCopia as e:
        sys.exit(f"Não abriu: {e}.")
    print("Conteúdo:", ", ".join(z.namelist()))
    if a.extrair:
        z.extractall(a.extrair)
        print(f"Arquivos extraídos em {a.extrair}.")
        return
    if a.banco == PRINCIPAL and input("Isto SUBSTITUI o banco do sistema pelo da cópia. Digite SIM para continuar: ") != "SIM":
        sys.exit("Cancelado.")
    from atualizar_paciente import CONEXAO
    restaurar(z, a.banco, CONEXAO)
    print(f"Banco restaurado em “{a.banco}”.")


if __name__ == "__main__":
    main()
