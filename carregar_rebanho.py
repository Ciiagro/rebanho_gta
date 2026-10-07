"""Carrega o CSV "Produtores_Propriedades_Rebanhos - FAEC" no Supabase (schema adagri).

Por padrão grava SÓ OS RESUMOS que o painel usa (menos de 2 MB no banco). O CSV completo fica no seu computador.

Uso:
  python carregar_rebanho.py "Produtores_Propriedades_Rebanhos_-_FAEC_-_01_10_2026.csv"
  python carregar_rebanho.py arquivo.csv --teste         # só lê e mostra os números, sem gravar
  python carregar_rebanho.py arquivo.csv --substituir    # refaz uma data que já foi carregada
  python carregar_rebanho.py arquivo.csv --data 2026-10-01   # se o nome não tiver a data
  python carregar_rebanho.py arquivo.csv --detalhado     # (opcional, ~150 MB) grava também linha a linha

A data de referência vem do nome do arquivo (dd_mm_aaaa), por exemplo 01_10_2026 = 01/10/2026.
Antes de rodar, execute sql/06_rebanho_resumo.sql no SQL Editor do Supabase.
NÃO são carregados: CPF/CNPJ, nome, apelido, nascimento, RG, e-mail, telefones, endereço, confrontantes.
"""
import io
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rebanho_comum import ESPECIES, GRUPOS, codigo_coluna, data_do_nome  # noqa: E402
from rebanho_cubos import calcular  # noqa: E402

COL_PRODUTOR = "produtor_codigo_adagri"
COL_PROP = "propriedade_codigo_adagri"
COLS_PROP = ["latitude_gd", "longitude_gd", "propriedade_codigo_municipio", "propriedade_nome_municipio",
             "propriedade_area_total"]


def preparar(caminho, data_ref):
    """Lê o CSV e devolve as tabelas prontas (sem dados pessoais)."""
    cab = pd.read_csv(caminho, sep=";", nrows=0, encoding="utf-8").columns
    col_reb = [c for c in cab if c.startswith("rebanho_")]
    df = pd.read_csv(caminho, sep=";", dtype=str, encoding="utf-8", keep_default_na=False, na_values=[""],
                     usecols=[COL_PRODUTOR, COL_PROP] + COLS_PROP + col_reb, low_memory=False)
    n_linhas = len(df)

    desconhecidas = sorted({codigo_coluna(c) for c in col_reb} - set(ESPECIES))
    if desconhecidas:
        sys.exit("ERRO: espécies novas no arquivo, ainda sem nome/grupo em rebanho_comum.py: " + ", ".join(desconhecidas))

    df[COL_PRODUTOR] = pd.to_numeric(df[COL_PRODUTOR], errors="coerce").astype("Int64")
    df[COL_PROP] = pd.to_numeric(df[COL_PROP], errors="coerce").astype("Int64")
    df["propriedade_codigo_municipio"] = pd.to_numeric(df["propriedade_codigo_municipio"], errors="coerce").astype("Int64")
    if df[[COL_PRODUTOR, COL_PROP, "propriedade_codigo_municipio"]].isna().any().any():
        sys.exit("ERRO: há linhas sem código de produtor, propriedade ou município.")

    # vínculos produtor x propriedade
    vinculo = df[[COL_PRODUTOR, COL_PROP]].drop_duplicates().rename(
        columns={COL_PRODUTOR: "produtor_codigo", COL_PROP: "propriedade_codigo"})

    # propriedades (uma linha por código)
    prop = df[[COL_PROP] + COLS_PROP].copy()
    for c in ("latitude_gd", "longitude_gd", "propriedade_area_total"):
        prop[c] = pd.to_numeric(prop[c], errors="coerce")
    prop = prop.groupby(COL_PROP, as_index=False).first()
    prop["latitude_gd"] = prop["latitude_gd"].round(6)
    prop["longitude_gd"] = prop["longitude_gd"].round(6)
    prop["propriedade_area_total"] = prop["propriedade_area_total"].round(2)
    prop = prop.rename(columns={COL_PROP: "propriedade_codigo", "latitude_gd": "latitude", "longitude_gd": "longitude",
                                "propriedade_codigo_municipio": "municipio_codigo",
                                "propriedade_nome_municipio": "municipio_nome", "propriedade_area_total": "area_total"})
    prop = prop[["propriedade_codigo", "municipio_codigo", "municipio_nome", "latitude", "longitude", "area_total"]]

    # rebanho em formato longo (só quantidade > 0). Colunas repetidas (ex.: mexilhao.1) somam na mesma espécie.
    pedacos = []
    base = df[[COL_PRODUTOR, COL_PROP]].rename(columns={COL_PRODUTOR: "produtor_codigo", COL_PROP: "propriedade_codigo"})
    for c in col_reb:
        q = pd.to_numeric(df[c], errors="coerce").fillna(0).round().astype("int64")
        m = q.values > 0
        if m.any():
            p = base[m].copy()
            p["especie"] = codigo_coluna(c)
            p["quantidade"] = q.values[m]
            pedacos.append(p)
    reb = pd.concat(pedacos, ignore_index=True)
    reb = reb.groupby(["produtor_codigo", "propriedade_codigo", "especie"], as_index=False)["quantidade"].sum()

    for t in (vinculo, prop, reb):
        t.insert(0, "data_referencia", data_ref)
    especies = pd.DataFrame([(k, v[0], v[1]) for k, v in ESPECIES.items()], columns=["codigo", "nome", "grupo_idx"])
    resumo = {"linhas_arquivo": n_linhas, "propriedades": len(prop), "produtores": int(vinculo["produtor_codigo"].nunique()),
              "registros_rebanho": len(reb)}
    return especies, prop, vinculo, reb, resumo


def copiar(cur, tabela, df, colunas, lote=100000):
    cols = ",".join(colunas)
    for i in range(0, len(df), lote):
        buf = io.StringIO()
        df.iloc[i:i + lote][colunas].to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(f"copy {tabela} ({cols}) from stdin with (format csv, null '\\N')", buf)
        print(f"  {tabela}: {min(i + lote, len(df)):,} / {len(df):,}")


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        sys.exit(__doc__)
    caminho = args[0]
    data_ref = date.fromisoformat(args[args.index("--data") + 1]) if "--data" in args else data_do_nome(os.path.basename(caminho))
    if data_ref is None:
        sys.exit("Não achei a data no nome do arquivo. Use: --data AAAA-MM-DD")
    print(f"Data de referência do arquivo: {data_ref:%d/%m/%Y}")

    print("Lendo o CSV (pode levar 1 a 2 minutos)...")
    especies, prop, vinculo, reb, resumo = preparar(caminho, data_ref)
    print(f"{resumo['linhas_arquivo']:,} linhas | {resumo['propriedades']:,} propriedades | "
          f"{resumo['produtores']:,} produtores | {resumo['registros_rebanho']:,} registros de rebanho")
    cubos = calcular(reb, prop, vinculo)
    q = cubos["qualidade"]
    linhas_resumo = sum(len(cubos[k]) for k in ("cubo_especie", "cubo_grupo", "municipio", "suspeito"))
    print(f"Resumos calculados: {linhas_resumo:,} linhas no total | {q['valores_suspeitos']} valores suspeitos fora dos totais")
    if "--teste" in args:
        print("Modo teste: nada foi gravado.")
        return

    from dotenv import load_dotenv
    import psycopg2
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        sys.exit("Defina SUPABASE_DB_URL no arquivo .env")
    conn = psycopg2.connect(url, connect_timeout=20)
    cur = conn.cursor()
    try:
        cur.execute("select count(*) from adagri.rebanho_municipio where data_referencia = %s", (data_ref,))
        if cur.fetchone()[0] > 0:
            if "--substituir" not in args:
                sys.exit(f"Já existe carga de {data_ref:%d/%m/%Y}. Use --substituir para refazer.")
            for t in ("rebanho_cubo_especie", "rebanho_cubo_grupo", "rebanho_municipio", "rebanho_suspeito", "rebanho_qualidade"):
                cur.execute(f"delete from adagri.{t} where data_referencia = %s", (data_ref,))
            print("Carga anterior dessa data removida.")

        for _, e in especies.iterrows():
            cur.execute("insert into adagri.especie_rebanho (codigo, nome, grupo) values (%s,%s,%s) "
                        "on conflict (codigo) do update set nome = excluded.nome, grupo = excluded.grupo",
                        (e.codigo, e.nome, GRUPOS[int(e.grupo_idx)]))
        for nome, cols in (("cubo_especie", ["municipio_codigo", "especie", "faixa", "propriedades", "quantidade"]),
                           ("cubo_grupo", ["municipio_codigo", "grupo", "faixa", "propriedades", "quantidade"]),
                           ("municipio", ["municipio_codigo", "municipio_nome", "propriedades", "produtores",
                                          "propriedades_com_rebanho", "propriedades_com_coordenada"]),
                           ("suspeito", ["especie", "municipio_codigo", "quantidade", "limite"])):
            d = cubos[nome].copy()
            d.insert(0, "data_referencia", data_ref)
            copiar(cur, "adagri.rebanho_" + nome, d, ["data_referencia"] + cols)
        cur.execute("insert into adagri.rebanho_qualidade (data_referencia, propriedades, produtores, vinculos, "
                    "propriedades_com_rebanho, sem_coordenada, coordenada_fora_ce, valores_suspeitos) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (data_ref, q["propriedades"], q["produtores"], q["vinculos"], q["propriedades_com_rebanho"],
                     q["sem_coordenada"], q["coordenada_fora_ce"], q["valores_suspeitos"]))

        if "--detalhado" in args:
            cur.execute("select to_regclass('adagri.rebanho')")
            if cur.fetchone()[0] is None:
                sys.exit("Para --detalhado, rode antes sql/04_rebanho.sql.")
            for t in ("rebanho", "produtor_propriedade", "propriedade"):
                cur.execute(f"delete from adagri.{t} where data_referencia = %s", (data_ref,))
            copiar(cur, "adagri.propriedade", prop,
                   ["data_referencia", "propriedade_codigo", "municipio_codigo", "municipio_nome", "latitude", "longitude", "area_total"])
            copiar(cur, "adagri.produtor_propriedade", vinculo, ["data_referencia", "produtor_codigo", "propriedade_codigo"])
            copiar(cur, "adagri.rebanho", reb, ["data_referencia", "produtor_codigo", "propriedade_codigo", "especie", "quantidade"])

        cur.execute("insert into adagri.carga_rebanho_log (arquivo, data_referencia, linhas_arquivo, propriedades, produtores, registros_rebanho) "
                    "values (%s,%s,%s,%s,%s,%s)",
                    (os.path.basename(caminho), data_ref, resumo["linhas_arquivo"], resumo["propriedades"],
                     resumo["produtores"], resumo["registros_rebanho"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"Pronto. Resumos do rebanho de {data_ref:%d/%m/%Y} carregados e registrados em adagri.carga_rebanho_log.")


if __name__ == "__main__":
    main()
