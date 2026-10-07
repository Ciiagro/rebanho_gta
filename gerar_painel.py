"""Gera o painel de GTAs (arquivo HTML) lendo o banco Supabase (adagri.gta).

Uso:
  pip install pandas numpy psycopg2-binary python-dotenv
  python gerar_painel.py                # usa o ano da última GTA do banco
  python gerar_painel.py --ano 2026     # força o ano
  python gerar_painel.py --saida meu_painel.html

Precisa do .env com SUPABASE_DB_URL e dos arquivos painel_template.html e mapa_ce.json
na mesma pasta. O HTML gerado não contém CPF, CNPJ nem nomes de pessoas.
"""
import base64, json, os, sys
from datetime import timedelta, timezone

import numpy as np
import pandas as pd

PASTA = os.path.dirname(os.path.abspath(__file__))

# ---------------- regras de contagem (iguais às do painel original) ----------------
Q_COLS = """colmeia rainha ovoscistossementesesporos jovens adulto femeaacima6meses machoacima6meses femeaate6meses
machoate6meses naodestinadasaproducaoornamentaissilvestresovosferteis naodestinadasaproducaoornamentaissilvestresadulto
naodestinadasaproducaoornamentaissilvestresoutrasespecies femea0ate12meses macho0ate12meses macho13ate24meses
femea13ate24meses macho25ate36meses femea25ate36meses machoacima36meses femeaacima36meses larva poslarva cistos todos
capivara ate12mesesmacho ate12mesesfemea acima12mesesmacho acima12mesesfemea alevinojuvenil ovosembrionarios
gamestasovasousemen avesde1dia adulto_1 recriada ovosferteis juveniladulto sementes ate12meses acima12meses outrasespecies
recriado iniciado criada imago girino ovos repteisnaohidrobios machoreprodutorcachaco femeamatriz macholeitao femealeitao
sexoidadenaorelevante adultofemea adultomacho ovosfemea ovosmacho jovensmacho jovensfemea""".split()
EGG_COLS = ["naodestinadasaproducaoornamentaissilvestresovosferteis", "cistos", "gamestasovasousemen",
            "ovosembrionarios", "ovosferteis"]
ANIMAL_COLS = [c for c in Q_COLS if c not in EGG_COLS and c not in ("rainha", "colmeia")]
ABELHAS = ("APIS MELLIFERA (ABELHA)", "ABELHA NATIVA SEM FERRÃO")

ESP_NOMES = {
    "AVES NÃO DESTINADAS À PRODUÇÃO DE CARNE OU OVOS (ORNAMENTAIS/SILVESTRES)": "Aves ornamentais/silvestres",
    "APIS MELLIFERA (ABELHA)": "Abelha Apis mellifera", "ABELHA NATIVA SEM FERRÃO": "Abelha nativa sem ferrão",
    "GALINHA-D ANGOLA": "Galinha-d'angola", "OUTRAS ESPÉCIES DE ANIMAIS AQUÁTICOS": "Outros animais aquáticos",
    "TILÁPIA DO NILO": "Tilápia do Nilo", "OUTRAS TILÁPIAS": "Outras tilápias", "SUÍNO": "Suíno",
    "CAMARÃO MARINHO": "Camarão marinho",
}
from rebanho_comum import GRUPOS  # lista única de grupos (a mesma do rebanho e da consulta)


def _g(nome):
    return GRUPOS.index(nome)


GRUPO_DE = {
    "BOVINO": _g("Bovinos"), "BUBALINO": _g("Bubalinos"), "OVINO": _g("Ovinos"), "CAPRINO": _g("Caprinos"),
    "SUÍNO": _g("Suínos"), "JAVALI": _g("Suínos"),
    "EQUINO": _g("Equídeos"), "ASININO": _g("Equídeos"), "MUAR": _g("Equídeos"),
    "GALINHA": _g("Aves"), "GALINHA-D ANGOLA": _g("Aves"), "CODORNA": _g("Aves"), "PATO": _g("Aves"),
    "PERU": _g("Aves"), "RATITAS": _g("Aves"),
    "AVES NÃO DESTINADAS À PRODUÇÃO DE CARNE OU OVOS (ORNAMENTAIS/SILVESTRES)": _g("Aves"),
    "APIS MELLIFERA (ABELHA)": _g("Abelhas"), "ABELHA NATIVA SEM FERRÃO": _g("Abelhas"),
    "OUTRAS ESPÉCIES": _g("Outras espécies"),
}
AQUATICO = ("CAMAR", "TILÁPIA", "PEIXE", "CRUST", "MOLUSC", "AQUÁTIC", "INVERTEBRADOS")
TIPOS = {"RODOVIÁRIO": "Rodoviário", "A PÉ": "A pé", "AÉREO": "Aéreo", "FERROVIÁRIO": "Ferroviário",
         "MARÍTIMO/FLUVIAL": "Marítimo/fluvial"}
FIN_NOMES = {"MIGRAÇAO DE ABELHAS": "Migração de abelhas", "ORNAMENTAÇÃO/AQUARIOFILIA": "Ornamentação/aquariofilia"}
PEQUENAS = {"de", "da", "do", "das", "dos", "e"}


def grupo_de(especie):
    if especie in GRUPO_DE:
        return GRUPO_DE[especie]
    return _g("Aquicultura") if any(k in especie for k in AQUATICO) else _g("Outras espécies")


def tcase(s):
    w = str(s).lower().split(" ")
    return " ".join(x if (i > 0 and x in PEQUENAS) else x.capitalize() for i, x in enumerate(w))


# ---------------- leitura do banco ----------------
def sql_dados(ano):
    soma = " + ".join(f"coalesce({c},0)" for c in ANIMAL_COLS)
    ovos = " + ".join(f"coalesce({c},0)" for c in EGG_COLS)
    abelhas = ",".join(f"'{a}'" for a in ABELHAS)
    return f"""
select dataemissao, tipotransito, finalidade, especie, ufdestino,
       codmunicipioorigem, codmunicipiodestino, nomemunicipiodestino,
       case when especie in ({abelhas}) then coalesce(colmeia,0) else {soma} end as q,
       case when especie in ({abelhas}) then 0 else {ovos} end as qe
from adagri.gta
where dataemissao >= '{ano}-01-01' and dataemissao < '{ano + 1}-01-01'
"""


def executar(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def ano_padrao(conn):
    cur = conn.cursor()
    cur.execute("select max(dataemissao) from adagri.gta")
    v = cur.fetchone()[0]
    if v is None:
        sys.exit("A tabela adagri.gta está vazia. Rode antes o carregar_gta.py.")
    return int(str(v)[:4])


def ultima_atualizacao(conn):
    try:
        cur = conn.cursor()
        cur.execute("select carregado_em from adagri.carga_log order by carregado_em desc limit 1")
        r = cur.fetchone()
        if not r or r[0] is None:
            return None
        v = r[0]
        if isinstance(v, str):
            v = pd.to_datetime(v).to_pydatetime()
        if v.tzinfo is not None:  # horário de Fortaleza (UTC-3, sem horário de verão)
            v = v.astimezone(timezone(timedelta(hours=-3))).replace(tzinfo=None)
        return v.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return None


# ---------------- montagem dos dados do painel ----------------
def montar_payload(df, mapa, ano, upd):
    for c in ("tipotransito", "finalidade", "especie", "ufdestino"):
        df[c] = df[c].fillna("(não informado)").astype(str)
    df["nomemunicipiodestino"] = df["nomemunicipiodestino"].fillna("").astype(str)
    df["q"] = pd.to_numeric(df["q"]).fillna(0).astype("float64")
    df["qe"] = pd.to_numeric(df["qe"]).fillna(0).astype("float64")

    munis = mapa["munis"]
    ce_codes = [m["c"] for m in munis]
    ce_idx = {c: i for i, c in enumerate(ce_codes)}
    ce_nome = {m["c"]: m["n"] for m in munis}

    # origem: só municípios do Ceará conhecidos
    cod_o = df["codmunicipioorigem"].fillna(0).astype("int64").astype(str)
    mo = cod_o.map(ce_idx)
    sem_mapa = mo.isna()
    if sem_mapa.any():
        print(f"AVISO: {int(sem_mapa.sum())} guias com município de origem fora do mapa do Ceará foram ignoradas.")
        df, mo, cod_o = df[~sem_mapa], mo[~sem_mapa], cod_o[~sem_mapa]
    mo = mo.astype("uint8")

    esp_list = list(df["especie"].value_counts().index)
    fin_list = list(df["finalidade"].value_counts().index)
    tipo_list = list(df["tipotransito"].value_counts().index)
    uf_list = ["CE"] + [u for u in df["ufdestino"].value_counts().index if u != "CE"]
    esp_idx = {e: i for i, e in enumerate(esp_list)}
    fin_idx = {f: i for i, f in enumerate(fin_list)}
    tipo_idx = {t: i for i, t in enumerate(tipo_list)}
    uf_idx = {u: i for i, u in enumerate(uf_list)}

    # destino: municípios do CE primeiro (mesma ordem do mapa), depois os de fora
    dest = [[ce_nome[c], "CE"] for c in ce_codes]
    out_idx = {}
    md = np.empty(len(df), dtype="uint16")
    cod_d = df["codmunicipiodestino"].fillna(0).astype("int64").values
    ufd = df["ufdestino"].values
    nomes = df["nomemunicipiodestino"].values
    for k in range(len(df)):
        uf, cod = ufd[k], cod_d[k]
        if uf == "CE" and str(cod) in ce_idx:
            md[k] = ce_idx[str(cod)]
        else:
            chave = (uf, cod if cod else nomes[k])
            if chave not in out_idx:
                out_idx[chave] = len(dest)
                dest.append([tcase(nomes[k]) if nomes[k] else "(sem município)", uf])
            md[k] = out_idx[chave]

    d0 = pd.Timestamp(f"{ano}-01-01")
    dias = (pd.to_datetime(df["dataemissao"]) - d0).dt.days.values.astype("<u2")
    arrs = {
        "d": dias,
        "e": df["especie"].map(esp_idx).values.astype("u1"),
        "f": df["finalidade"].map(fin_idx).values.astype("u1"),
        "t": df["tipotransito"].map(tipo_idx).values.astype("u1"),
        "u": df["ufdestino"].map(uf_idx).values.astype("u1"),
        "o": mo.values,
        "m": md.astype("<u2"),
        "q": df["q"].values.astype("<f8"),
    }
    b = {k: base64.b64encode(v.tobytes()).decode() for k, v in arrs.items()}
    nz = np.nonzero(df["qe"].values)[0]
    b["ei"] = base64.b64encode(nz.astype("<u4").tobytes()).decode()
    b["ev"] = base64.b64encode(df["qe"].values[nz].astype("<f8").tobytes()).decode()

    return {
        "n": len(df), "ano": ano, "upd": upd,
        "esp": [{"n": ESP_NOMES.get(e, e.capitalize()), "g": grupo_de(e)} for e in esp_list],
        "fin": [FIN_NOMES.get(f, f.capitalize()) for f in fin_list],
        "tipo": [TIPOS.get(t, t.capitalize()) for t in tipo_list],
        "uf": uf_list, "grupos": GRUPOS, "dest": dest, "munis": munis,
        "mapW": mapa["mapW"], "mapH": mapa["mapH"], "b": b,
    }


def main():
    args = sys.argv[1:]
    ano = int(args[args.index("--ano") + 1]) if "--ano" in args else None
    saida = args[args.index("--saida") + 1] if "--saida" in args else os.path.join(PASTA, "painel_gta_ceara.html")

    from dotenv import load_dotenv
    import psycopg2
    load_dotenv(os.path.join(PASTA, ".env"))
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        sys.exit("Defina SUPABASE_DB_URL no arquivo .env")
    conn = psycopg2.connect(url, connect_timeout=20)

    ano = ano or ano_padrao(conn)
    print(f"Lendo as GTAs de {ano} do banco...")
    df = executar(conn, sql_dados(ano))
    upd = ultima_atualizacao(conn)
    conn.close()
    print(f"{len(df):,} guias lidas. Última atualização da base: {upd or 'não registrada'}")
    if df.empty:
        sys.exit("Nenhuma guia nesse ano.")

    mapa = json.load(open(os.path.join(PASTA, "mapa_ce.json"), encoding="utf-8"))
    payload = montar_payload(df, mapa, ano, upd)
    tpl = open(os.path.join(PASTA, "painel_template.html"), encoding="utf-8").read()
    html = tpl.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    open(saida, "w", encoding="utf-8").write(html)
    print(f"Painel gerado: {saida} ({os.path.getsize(saida) / 1e6:.1f} MB). Abra o arquivo no navegador.")


if __name__ == "__main__":
    main()
