"""Carrega GTA_CORRETO.xlsx na tabela adagri.gta do Supabase.

Uso:
  pip install pandas openpyxl psycopg2-binary python-dotenv
  copie .env.example para .env e preencha SUPABASE_DB_URL
  python carregar_gta.py GTA_CORRETO.xlsx          # carga normal
  python carregar_gta.py GTA_CORRETO.xlsx --limpar # apaga a tabela antes
"""
import io, os, sys
from datetime import datetime, timezone
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_DB_URL")
if not url:
    sys.exit("Defina SUPABASE_DB_URL no arquivo .env")
if len(sys.argv) < 2:
    sys.exit("Informe o arquivo: python carregar_gta.py GTA_CORRETO.xlsx")

print("Lendo a planilha (leva cerca de 1 minuto)...")
df = pd.read_excel(sys.argv[1])
df.columns = [c.strip().lower() for c in df.columns]

# colunas de texto: vazio vira NULL
for c in df.select_dtypes(include=["object", "string"]).columns:
    df[c] = df[c].astype("string").str.strip().replace("", pd.NA)
# colunas numéricas que vieram como decimal (códigos com vazios) viram inteiro com NULL
for c in df.select_dtypes("float").columns:
    df[c] = df[c].astype("Int64")
df["dataemissao"] = pd.to_datetime(df["dataemissao"]).dt.date
print(f"{len(df):,} linhas, {df.shape[1]} colunas")

cols = ",".join(df.columns)
conn = psycopg2.connect(url)
cur = conn.cursor()
if "--limpar" in sys.argv:
    cur.execute("truncate adagri.gta")
    print("Tabela limpa.")

CH = 20000
for i in range(0, len(df), CH):
    buf = io.StringIO()
    df.iloc[i:i + CH].to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cur.copy_expert(f"copy adagri.gta ({cols}) from stdin with (format csv, null '\\N')", buf)
    conn.commit()
    print(f"  {min(i + CH, len(df)):,} / {len(df):,}")

cur.execute("select count(*) from adagri.gta")
total = cur.fetchone()[0]
print("Total no banco:", f"{total:,}")

# registra a atualização (rode antes o 03_log_atualizacao.sql)
arq = sys.argv[1]
modificado = datetime.fromtimestamp(os.path.getmtime(arq), tz=timezone.utc)
cur.execute(
    "insert into adagri.carga_log (arquivo, arquivo_modificado_em, total_linhas, emissao_min, emissao_max) "
    "values (%s, %s, %s, %s, %s)",
    (os.path.basename(arq), modificado, total, df["dataemissao"].min(), df["dataemissao"].max()),
)
conn.commit()
print(f"Atualização registrada: arquivo de {modificado:%d/%m/%Y %H:%M}, GTAs até {df['dataemissao'].max():%d/%m/%Y}")
conn.close()
