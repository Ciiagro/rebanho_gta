"""Mostra em QUAL banco o .env desta pasta conecta e o que já existe nele (sem mostrar a senha).
Uso: python testar_conexao.py   (precisa de: pip install psycopg2-binary python-dotenv)
"""
import os
import re
import sys

import psycopg2
from dotenv import load_dotenv

pasta = os.path.dirname(os.path.abspath(__file__))
caminho_env = os.path.join(pasta, ".env")
print("Pasta do script:", pasta)
print("Arquivo .env:", caminho_env, "(existe)" if os.path.exists(caminho_env) else "(NÃO EXISTE)")
load_dotenv(caminho_env)
url = os.environ.get("SUPABASE_DB_URL")
if not url:
    sys.exit("ERRO: não achei SUPABASE_DB_URL no .env desta pasta.")

print("Conectando em:", re.sub(r":[^:@/]+@", ":*****@", url))
m = re.search(r"//([^:]+):", url)
usuario_url = m.group(1) if m else ""
if "." in usuario_url:
    print("Código do projeto no endereço:", usuario_url.split(".", 1)[1])

try:
    conn = psycopg2.connect(url, connect_timeout=15)
except Exception as e:
    sys.exit(f"FALHOU ao conectar:\n{e}")

cur = conn.cursor()
cur.execute("select current_user, current_database()")
u, b = cur.fetchone()
print(f"\nConectou! usuário={u}  banco={b}")

print("\nO que existe no schema adagri deste banco:")
for t in ("gta", "carga_log", "rebanho_municipio", "rebanho_cubo_especie", "rebanho_cubo_grupo", "rebanho_qualidade"):
    try:
        cur.execute(f"select count(*) from adagri.{t}")
        print(f"  adagri.{t:22s} {cur.fetchone()[0]:>10,} linhas")
    except Exception:
        conn.rollback()
        print(f"  adagri.{t:22s} NÃO EXISTE")

try:
    cur.execute("select arquivo, data_referencia, carregado_em from adagri.carga_rebanho_log order by carregado_em desc limit 3")
    rows = cur.fetchall()
    print("\nÚltimas cargas de rebanho registradas:", rows if rows else "nenhuma")
except Exception:
    conn.rollback()
    print("\nTabela de log do rebanho não existe neste banco (o SQL 06 não foi rodado aqui).")
conn.close()
