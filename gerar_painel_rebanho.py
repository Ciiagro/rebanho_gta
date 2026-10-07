"""Gera o painel de REBANHO (arquivo HTML) lendo o banco Supabase (schema adagri).

Uso:
  python gerar_painel_rebanho.py                    # usa a data de referência mais recente carregada
  python gerar_painel_rebanho.py --data 2026-10-01  # escolhe uma data
  python gerar_painel_rebanho.py --saida meu_painel.html

Precisa do .env (SUPABASE_DB_URL), de painel_rebanho_template.html e de mapa_ce.json na mesma pasta.
O HTML gerado traz só números agregados por município, espécie e faixa de tamanho. Nada de CPF, nome ou endereço.
"""
import json
import os
import sys
from datetime import date, timedelta, timezone

import pandas as pd

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)
from rebanho_comum import ESPECIES, FAIXAS_TXT, GRUPOS, LIMITE_GRUPO, UNIDADES  # noqa: E402


# ---------------- leitura do banco (só tabelas de resumo, pequenas) ----------------
def executar(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def data_padrao(conn):
    cur = conn.cursor()
    cur.execute("select max(data_referencia) from adagri.rebanho_municipio")
    v = cur.fetchone()[0]
    if v is None:
        sys.exit("Não há resumo de rebanho no banco. Rode antes o carregar_rebanho.py.")
    return str(v)[:10]


def buscar(conn, data):
    d = f"data_referencia = '{data}'"
    return {
        "cubo_especie": executar(conn, f"select municipio_codigo, especie, faixa, propriedades, quantidade from adagri.rebanho_cubo_especie where {d}"),
        "cubo_grupo": executar(conn, f"select municipio_codigo, grupo, faixa, propriedades, quantidade from adagri.rebanho_cubo_grupo where {d}"),
        "municipio": executar(conn, f"select municipio_codigo, propriedades, produtores, propriedades_com_rebanho, propriedades_com_coordenada from adagri.rebanho_municipio where {d}"),
        "suspeito": executar(conn, f"select especie, municipio_codigo, quantidade from adagri.rebanho_suspeito where {d} order by quantidade desc"),
        "qualidade": executar(conn, f"select * from adagri.rebanho_qualidade where {d}"),
    }


def ultima_carga(conn, data):
    try:
        cur = conn.cursor()
        cur.execute(f"select carregado_em from adagri.carga_rebanho_log where data_referencia = '{data}' "
                    "order by carregado_em desc limit 1")
        r = cur.fetchone()
        if not r or r[0] is None:
            return None
        v = r[0]
        if isinstance(v, str):
            v = pd.to_datetime(v).to_pydatetime()
        if v.tzinfo is not None:  # horário de Fortaleza (UTC-3)
            v = v.astimezone(timezone(timedelta(hours=-3))).replace(tzinfo=None)
        return v.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return None


# ---------------- dados do painel ----------------
def montar_payload(t, mapa, data_ref, upd):
    munis = mapa["munis"]
    nm = len(munis)
    ce_idx = {int(m["c"]): i for i, m in enumerate(munis)}

    ce_df, cg_df, mu_df, su_df, ql = t["cubo_especie"], t["cubo_grupo"], t["municipio"], t["suspeito"], t["qualidade"]
    desconhecidas = set(ce_df["especie"]) - set(ESPECIES)
    if desconhecidas:
        sys.exit("Espécies sem cadastro em rebanho_comum.py: " + ", ".join(sorted(desconhecidas)))
    # Proteção: os resumos por grupo no banco têm que bater com os por espécie. Se não baterem, foram gravados
    # com a lista de grupos antiga (antes de separar ovinos de caprinos etc.) e é preciso recarregar.
    por_esp = ce_df[ce_df["faixa"] == len(FAIXAS_TXT)].assign(g=lambda d: d["especie"].map(lambda c: ESPECIES[c][1]))
    tot_esp = por_esp.groupby("g")["quantidade"].sum()
    tot_grp = cg_df[cg_df["faixa"] == len(FAIXAS_TXT)].groupby("grupo")["quantidade"].sum()
    todos = sorted(set(tot_esp.index) | set(tot_grp.index))
    if any(int(tot_esp.get(g, 0)) != int(tot_grp.get(g, 0)) for g in todos):
        sys.exit("Os resumos por grupo gravados no banco são de uma versão antiga (grupos diferentes dos atuais).\n"
                 "Recarregue com:  python carregar_rebanho.py \"SEU_ARQUIVO.csv\" --substituir\n"
                 "e depois rode de novo o gerar_painel_rebanho.py.")
    presentes = [c for c in ESPECIES if c in set(ce_df["especie"]) | set(su_df["especie"])]
    esp_idx = {c: i for i, c in enumerate(presentes)}
    esp = [{"n": ESPECIES[c][0], "g": ESPECIES[c][1]} for c in presentes]

    def idx(df):
        df = df.copy()
        df["m"] = df["municipio_codigo"].astype("int64").map(ce_idx)
        return df[df["m"].notna()].astype({"m": "int64"})

    ce_df = idx(ce_df)
    ce_df["e"] = ce_df["especie"].map(esp_idx)
    ce = ce_df[["m", "e", "faixa", "propriedades", "quantidade"]].astype("int64").values.tolist()
    cg_df = idx(cg_df)
    cg = cg_df[["m", "grupo", "faixa", "propriedades", "quantidade"]].astype("int64").values.tolist()

    mun = [[0, 0, 0, 0] for _ in range(nm)]
    for r in idx(mu_df).itertuples():
        mun[r.m] = [int(r.propriedades), int(r.produtores), int(r.propriedades_com_rebanho), int(r.propriedades_com_coordenada)]

    su = idx(su_df)
    sus = [[esp_idx[r.especie], int(r.m), int(r.quantidade)] for r in su.head(40).itertuples()]
    q = ql.iloc[0]
    qual = {"props": int(q["propriedades"]), "prods": int(q["produtores"]), "vinc": int(q["vinculos"]),
            "com_rebanho": int(q["propriedades_com_rebanho"]), "sem_coord": int(q["sem_coordenada"]),
            "fora_ce": int(q["coordenada_fora_ce"])}
    dr = date.fromisoformat(data_ref)
    return {
        "ref": data_ref, "refTxt": dr.strftime("%d/%m/%Y"), "upd": upd,
        "grupos": GRUPOS, "unidades": UNIDADES, "esp": esp, "faixas": FAIXAS_TXT,
        "limites": [LIMITE_GRUPO[g] for g in range(len(GRUPOS))],
        "munis": munis, "mapW": mapa["mapW"], "mapH": mapa["mapH"],
        "ce": ce, "cg": cg, "mun": mun, "sus": sus, "nsus": int(q["valores_suspeitos"]), "q": qual,
    }


def main():
    args = sys.argv[1:]
    data = args[args.index("--data") + 1] if "--data" in args else None
    saida = args[args.index("--saida") + 1] if "--saida" in args else os.path.join(PASTA, "painel_rebanho_ceara.html")

    from dotenv import load_dotenv
    import psycopg2
    load_dotenv(os.path.join(PASTA, ".env"))
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        sys.exit("Defina SUPABASE_DB_URL no arquivo .env")
    conn = psycopg2.connect(url, connect_timeout=20)
    data = data or data_padrao(conn)
    print(f"Lendo os resumos do rebanho de {data} do banco...")
    tabelas = buscar(conn, data)
    upd = ultima_carga(conn, data)
    conn.close()
    if tabelas["qualidade"].empty:
        sys.exit(f"Não há resumo de rebanho para {data}.")
    print(f"{len(tabelas['cubo_especie']):,} linhas de resumo por espécie | {len(tabelas['municipio'])} municípios")

    mapa = json.load(open(os.path.join(PASTA, "mapa_ce.json"), encoding="utf-8"))
    payload = montar_payload(tabelas, mapa, data, upd)
    tpl = open(os.path.join(PASTA, "painel_rebanho_template.html"), encoding="utf-8").read()
    html = tpl.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    open(saida, "w", encoding="utf-8").write(html)
    print(f"Painel gerado: {saida} ({os.path.getsize(saida) / 1e6:.1f} MB). Abra no navegador.")
    if payload["nsus"]:
        print(f"Atenção: {payload['nsus']} valores suspeitos ficaram fora dos totais (veja o quadro de qualidade).")


if __name__ == "__main__":
    main()
