"""Consulta de produtores e propriedades, cruzando o CADASTRO DE REBANHO com as GTAs.

Roda SÓ no seu computador (endereço http://127.0.0.1:8765). Nada é enviado para fora, e nenhum dado pessoal
vai para o banco, para o painel ou para o Git.

Uso:
  pip install pandas numpy openpyxl psycopg2-binary python-dotenv
  python consultar.py                                   # acha o CSV de rebanho e usa as GTAs do banco (.env)
  python consultar.py --rebanho "Produtores_..._01_10_2026.csv" --gta-xlsx "GTA CORRETO.xlsx"
  python consultar.py --atualizar                       # refaz a leitura (use quando trocar os arquivos)
  python consultar.py --porta 8800

Na primeira vez leva alguns minutos para ler os arquivos; depois fica guardado em .cache_consulta/ e abre em segundos.
A pasta .cache_consulta/ contém dados pessoais: não copie nem suba para o Git. Feche com Ctrl+C quando terminar.
"""
import csv
import glob
import io
import json
import os
import re
import sys
import unicodedata
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

PASTA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PASTA)
from rebanho_comum import ESPECIES, GRUPOS, LIMITE_GRUPO, UNIDADES  # noqa: E402
import carregar_rebanho as cr  # noqa: E402
import gerar_painel as gp  # noqa: E402

CACHE = os.path.join(PASTA, ".cache_consulta")
ESP_NOME = {k: v[0] for k, v in ESPECIES.items()}
ESP_GRUPO = {k: v[1] for k, v in ESPECIES.items()}


# ======================================================================== leitura dos dados
def sem_acento(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def so_digitos(s):
    return re.sub(r"\D", "", str(s)) if s is not None else ""


def mascarar(d):
    d = so_digitos(d)
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"**.***.{d[5:8]}/{d[8:12]}-**"
    return "***" if d else ""


def formatar(d):
    d = so_digitos(d)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d


def carregar_rebanho(csv_path):
    print("Lendo o cadastro de rebanho (1 a 2 minutos)...")
    esp, prop, vinc, reb, res = cr.preparar(csv_path, date(2000, 1, 1))
    cols = ["produtor_codigo_adagri", "produtor_nr_cpf_cnpj", "produtor_nome", "produtor_apelido",
            "produtor_tel_residencial", "produtor_tel_comercial", "produtor_tel_movel",
            "propriedade_codigo_adagri", "propriedade_nome"]
    raw = pd.read_csv(csv_path, sep=";", dtype=str, encoding="utf-8", keep_default_na=False, na_values=[""],
                      usecols=cols, low_memory=False)
    pes = raw.drop_duplicates("produtor_codigo_adagri").copy()
    pes["produtor_codigo"] = pes["produtor_codigo_adagri"].astype("int64")
    pes["cpf"] = pes["produtor_nr_cpf_cnpj"].map(so_digitos)
    pes["cpf_num"] = pd.to_numeric(pes["cpf"], errors="coerce").astype("Int64")
    pes["nome"] = pes["produtor_nome"].fillna("")
    pes["nome_norm"] = pes["nome"].map(sem_acento)
    pes["tel"] = pes["produtor_tel_movel"].fillna(pes["produtor_tel_residencial"]).fillna(pes["produtor_tel_comercial"])
    pes = pes[["produtor_codigo", "nome", "produtor_apelido", "cpf", "cpf_num", "nome_norm", "tel"]].reset_index(drop=True)
    nomes_prop = raw.drop_duplicates("propriedade_codigo_adagri")[["propriedade_codigo_adagri", "propriedade_nome"]].copy()
    nomes_prop.columns = ["propriedade_codigo", "nome_prop"]
    nomes_prop["propriedade_codigo"] = nomes_prop["propriedade_codigo"].astype("int64")
    prop = prop.drop(columns=["data_referencia"]).merge(nomes_prop, on="propriedade_codigo", how="left")
    prop["nome_prop"] = prop["nome_prop"].fillna("")
    prop["nome_prop_norm"] = prop["nome_prop"].map(sem_acento)
    reb = reb.drop(columns=["data_referencia"])
    reb["grupo"] = reb["especie"].map(ESP_GRUPO).astype("int64")
    # valores impossíveis ficam fora (mesma regra do painel)
    reb = reb[reb["quantidade"] <= reb["grupo"].map(LIMITE_GRUPO)].reset_index(drop=True)
    vinc = vinc.drop(columns=["data_referencia"])
    return {"pes": pes, "prop": prop, "vinc": vinc, "reb": reb}


def carregar_gtas(xlsx=None):
    if xlsx:
        print("Lendo as GTAs da planilha (1 a 2 minutos)...")
        df = pd.read_excel(xlsx)
        df.columns = [c.strip().lower() for c in df.columns]
        soma = df[gp.ANIMAL_COLS].fillna(0).sum(axis=1).astype("float64")
        abel = df["especie"].isin(gp.ABELHAS)
        soma[abel] = df.loc[abel, "colmeia"].fillna(0).astype("float64")
        df["q"] = soma
        df["dataemissao"] = pd.to_datetime(df["dataemissao"])
    else:
        from dotenv import load_dotenv
        import psycopg2
        load_dotenv(os.path.join(PASTA, ".env"))
        url = os.environ.get("SUPABASE_DB_URL")
        if not url:
            sys.exit("Sem planilha de GTAs e sem SUPABASE_DB_URL no .env. Use --gta-xlsx \"GTA CORRETO.xlsx\".")
        print("Lendo as GTAs do banco...")
        soma = " + ".join(f"coalesce({c},0)" for c in gp.ANIMAL_COLS)
        abel = ",".join(f"'{a}'" for a in gp.ABELHAS)
        sql = f"""select numerogta, dataemissao, tipotransito, finalidade, especie, ufdestino, nomemunicipiodestino,
          codmunicipioorigem, nomemunicipioorigem, codpropestaborigem, codpropestabdestino, cpfcnpjorigem, cpfcnpjdestino,
          nomepessoaorigem, nomepessoadestino,
          case when especie in ({abel}) then coalesce(colmeia,0) else {soma} end as q from adagri.gta"""
        conn = psycopg2.connect(url, connect_timeout=20)
        df = gp.executar(conn, sql)
        conn.close()
        df["dataemissao"] = pd.to_datetime(df["dataemissao"])
    g = pd.DataFrame({
        "numero": df["numerogta"].astype("int64"), "data": df["dataemissao"], "esp": df["especie"].astype(str),
        "fin": df["finalidade"].astype(str).str.capitalize(), "ufd": df["ufdestino"].astype(str),
        "mund": df["nomemunicipiodestino"].astype(str), "munc": df["codmunicipioorigem"].astype("int64"),
        "muno": df["nomemunicipioorigem"].astype(str),
        "po": pd.to_numeric(df["codpropestaborigem"], errors="coerce").astype("Int64"),
        "pd": pd.to_numeric(df["codpropestabdestino"], errors="coerce").astype("Int64"),
        "co": pd.to_numeric(df["cpfcnpjorigem"], errors="coerce").astype("Int64"),
        "cd": pd.to_numeric(df["cpfcnpjdestino"], errors="coerce").astype("Int64"),
        "nome_o": df["nomepessoaorigem"].fillna("").astype(str), "nome_d": df["nomepessoadestino"].fillna("").astype(str),
        "q": pd.to_numeric(df["q"]).fillna(0).astype("float64"),
    })
    g["grupo"] = g["esp"].map(gp.grupo_de).astype("int64")
    return g


def carregar_tudo(args):
    os.makedirs(CACHE, exist_ok=True)
    csvp = args.get("rebanho") or next(iter(sorted(glob.glob(os.path.join(PASTA, "*Rebanhos*.csv")))), None)
    if not csvp:
        sys.exit("Não achei o CSV de rebanho. Use --rebanho \"caminho\\arquivo.csv\".")
    xl = args.get("gta-xlsx")
    chave = f"v2|{len(GRUPOS)}|{os.path.basename(csvp)}|{os.path.getsize(csvp)}|{xl or 'db'}"
    pk = os.path.join(CACHE, "dados.pkl")
    if os.path.exists(pk) and not args.get("atualizar"):
        try:
            d = pd.read_pickle(pk)
            if d.get("chave") == chave:
                print("Dados carregados do cache.")
                return d
        except Exception:
            pass
    d = carregar_rebanho(csvp)
    d["gt"] = carregar_gtas(xl)
    d["chave"] = chave
    d["ref"] = cr.data_do_nome(os.path.basename(csvp))
    d["gt_ate"] = d["gt"]["data"].max()
    pd.to_pickle(d, pk)
    return d


# ======================================================================== consultas
class Base:
    def __init__(self, d):
        self.pes, self.prop, self.vinc, self.reb, self.gt = d["pes"], d["prop"], d["vinc"], d["reb"], d["gt"]
        self.ref, self.gt_ate = d.get("ref"), d.get("gt_ate")
        self.pes_i = self.pes.set_index("produtor_codigo")
        self.prop_i = self.prop.set_index("propriedade_codigo")
        self.props_de = self.vinc.groupby("produtor_codigo")["propriedade_codigo"].apply(list).to_dict()
        self.prods_de = self.vinc.groupby("propriedade_codigo")["produtor_codigo"].apply(list).to_dict()
        # rebanho por grupo
        self.rb_prop_g = self.reb.groupby(["propriedade_codigo", "grupo"])["quantidade"].sum()
        self.rb_prod_g = self.reb.groupby(["produtor_codigo", "grupo"])["quantidade"].sum()
        cpf_de = self.pes.set_index("produtor_codigo")["cpf_num"]
        r2 = self.rb_prod_g.reset_index()
        r2["cpf_num"] = r2["produtor_codigo"].map(cpf_de)
        self.rb_cpf_g = r2.groupby(["cpf_num", "grupo"])["quantidade"].sum()

    # ---------- util
    def _prop_info(self, cod):
        if cod in self.prop_i.index:
            r = self.prop_i.loc[cod]
            return {"codigo": int(cod), "nome": r["nome_prop"], "municipio": r["municipio_nome"],
                    "area": None if pd.isna(r["area_total"]) else float(r["area_total"])}
        return {"codigo": int(cod), "nome": "", "municipio": "", "area": None}

    def _resumo_gtas(self, sub, rebanho_g=None):
        """sub: GTAs filtradas. rebanho_g: dict grupo_idx -> rebanho cadastrado."""
        r = {"total": int(len(sub)), "grupos": [], "meses": [0] * 12, "finalidades": [], "destinos": [], "ultimas": []}
        if sub.empty:
            return r
        for g, s in sub.groupby("grupo"):
            mov = float(s["q"].sum())
            reb = float((rebanho_g or {}).get(int(g), 0))
            r["grupos"].append({"grupo": GRUPOS[int(g)], "unidade": UNIDADES[int(g)], "guias": int(len(s)),
                                "movimentado": int(mov), "rebanho": int(reb), "razao": (mov / reb) if reb > 0 else None})
        r["grupos"].sort(key=lambda x: -x["guias"])
        for m, n in sub["data"].dt.month.value_counts().items():
            r["meses"][int(m) - 1] = int(n)
        r["finalidades"] = [{"nome": k, "guias": int(v)} for k, v in sub["fin"].value_counts().head(5).items()]
        dest = sub.assign(d=sub["mund"].str.title() + " (" + sub["ufd"] + ")").groupby("d").agg(
            guias=("numero", "count"), animais=("q", "sum")).sort_values("guias", ascending=False).head(8)
        r["destinos"] = [{"nome": k, "guias": int(v.guias), "animais": int(v.animais)} for k, v in dest.iterrows()]
        ult = sub.sort_values("data", ascending=False).head(15)
        r["ultimas"] = [{"numero": int(x.numero), "data": x.data.strftime("%d/%m/%Y"), "especie": x.esp.capitalize(),
                         "fin": x.fin, "quantidade": int(x.q), "destino": f"{x.mund.title()} ({x.ufd})"} for x in ult.itertuples()]
        return r

    # ---------- busca
    def buscar(self, q):
        q = (q or "").strip()
        if len(q) < 3:
            return []
        dig = so_digitos(q)
        res = []
        if dig and len(dig) >= 5 and not re.search(r"[A-Za-z]", q):
            n = int(dig)
            hit = self.pes[(self.pes["cpf_num"] == n) | (self.pes["produtor_codigo"] == n)]
            for r in hit.head(20).itertuples():
                res.append(self._item_produtor(r.produtor_codigo))
            if n in self.prop_i.index:
                res.append(self._item_prop(n))
            return res[:30]
        toks = [t for t in sem_acento(q).split() if t]
        m = pd.Series(True, index=self.pes.index)
        for t in toks:
            m &= self.pes["nome_norm"].str.contains(t, regex=False)
        for r in self.pes[m].head(25).itertuples():
            res.append(self._item_produtor(r.produtor_codigo))
        m2 = pd.Series(True, index=self.prop.index)
        for t in toks:
            m2 &= self.prop["nome_prop_norm"].str.contains(t, regex=False)
        for r in self.prop[m2].head(10).itertuples():
            res.append(self._item_prop(r.propriedade_codigo))
        return res

    def _item_produtor(self, cod):
        p = self.pes_i.loc[cod]
        props = self.props_de.get(cod, [])
        muns = sorted({self._prop_info(c)["municipio"] for c in props if c in self.prop_i.index})
        return {"tipo": "produtor", "id": int(cod), "nome": p["nome"], "doc": mascarar(p["cpf"]),
                "detalhe": f"{len(props)} propriedade(s)" + (f" · {', '.join(m.title() for m in muns[:2])}" if muns else "")}

    def _item_prop(self, cod):
        i = self._prop_info(cod)
        prods = self.prods_de.get(cod, [])
        return {"tipo": "propriedade", "id": int(cod), "nome": i["nome"] or f"Propriedade {cod}", "doc": str(cod),
                "detalhe": f"{i['municipio'].title()} · {len(prods)} produtor(es)"}

    # ---------- produtor
    def produtor(self, cod):
        if cod not in self.pes_i.index:
            return None
        p = self.pes_i.loc[cod]
        props = self.props_de.get(cod, [])
        cpf = p["cpf_num"]
        r = self.reb[self.reb["produtor_codigo"] == cod]
        especies = r.groupby("especie")["quantidade"].sum().sort_values(ascending=False)
        reb_g = {g: float(self.rb_prod_g.get((cod, g), 0)) for g in range(len(GRUPOS))}
        gt = self.gt
        # GTAs do produtor: pelo CPF/CNPJ; e também pela propriedade, mas só quando ele é o único produtor dela
        # (em propriedade com vários produtores, a guia não pode ser atribuída a um só)
        unicas = [c for c in props if len(self.prods_de.get(c, [])) == 1]
        m_o = gt["po"].isin(unicas)
        m_d = gt["pd"].isin(unicas)
        if not pd.isna(cpf):
            m_o |= (gt["co"] == cpf)
            m_d |= (gt["cd"] == cpf)
        rr = r.groupby(["propriedade_codigo", "grupo"])["quantidade"].sum()
        propriedades = []
        for c in props:
            i = self._prop_info(c)
            i["rebanho"] = {GRUPOS[g]: int(rr.get((c, g), 0)) for g in range(len(GRUPOS)) if rr.get((c, g), 0)}
            i["gtas_saida"] = int(gt["po"].eq(c).sum())
            i["produtores"] = len(self.prods_de.get(c, []))
            propriedades.append(i)
        return {"tipo": "produtor", "id": int(cod), "nome": p["nome"], "apelido": p["produtor_apelido"] or "",
                "doc": mascarar(p["cpf"]), "doc_completo": formatar(p["cpf"]), "telefone": p["tel"] or "",
                "propriedades": propriedades,
                "especies": [{"especie": ESP_NOME[k], "quantidade": int(v)} for k, v in especies.items()],
                "saida": self._resumo_gtas(gt[m_o], reb_g),
                "entrada": self._resumo_gtas(gt[m_d])}

    # ---------- propriedade
    def propriedade(self, cod):
        if cod not in self.prop_i.index:
            return None
        i = self._prop_info(cod)
        r = self.reb[self.reb["propriedade_codigo"] == cod]
        especies = r.groupby("especie")["quantidade"].sum().sort_values(ascending=False)
        reb_g = {g: float(self.rb_prop_g.get((cod, g), 0)) for g in range(len(GRUPOS))}
        prods = []
        for pc in self.prods_de.get(cod, []):
            p = self.pes_i.loc[pc]
            prods.append({"id": int(pc), "nome": p["nome"], "doc": mascarar(p["cpf"])})
        gt = self.gt
        i.update({"tipo": "propriedade", "id": int(cod), "produtores": prods,
                  "especies": [{"especie": ESP_NOME[k], "quantidade": int(v)} for k, v in especies.items()],
                  "saida": self._resumo_gtas(gt[gt["po"] == cod], reb_g),
                  "entrada": self._resumo_gtas(gt[gt["pd"] == cod])})
        return i

    # ---------- ranking
    def ranking(self, grupo, de, ate, mun, por, ordem, n=50):
        gt = self.gt
        m = gt["grupo"] == grupo
        if de:
            m &= gt["data"] >= pd.Timestamp(de)
        if ate:
            m &= gt["data"] <= pd.Timestamp(ate)
        if mun:
            m &= gt["munc"] == mun
        sub = gt[m]
        chave = "po" if por == "propriedade" else "co"
        sub = sub[sub[chave].notna()]
        ag = sub.groupby(chave).agg(guias=("numero", "count"), movimentado=("q", "sum")).reset_index()
        ag = ag.sort_values("guias" if ordem == "guias" else "movimentado", ascending=False)
        total_guias, total_mov = int(len(sub)), float(sub["q"].sum())
        linhas = []
        idx = sub.groupby(chave).indices
        for r in ag.head(n).itertuples():
            k = int(getattr(r, chave))
            s = sub.iloc[idx[k]]
            fin = s["fin"].value_counts().index[0]
            ufd = s["ufd"].value_counts().index[0]
            fora = float((s["ufd"] != "CE").mean())
            if por == "propriedade":
                i = self._prop_info(k)
                nome, mun_nome = i["nome"] or f"Propriedade {k}", i["municipio"].title()
                if not mun_nome:
                    mun_nome = s["muno"].iloc[0].title()
                reb = float(self.rb_prop_g.get((k, grupo), 0))
                doc = str(k)
                produtores = ", ".join(self.pes_i.loc[p]["nome"].title() for p in self.prods_de.get(k, [])[:2])
            else:
                hit = self.pes[self.pes["cpf_num"] == k]
                nome = hit["nome"].iloc[0] if len(hit) else (s["nome_o"].iloc[0] or "(fora do cadastro)")
                mun_nome = s["muno"].iloc[0].title()
                reb = float(self.rb_cpf_g.get((k, grupo), 0))
                doc = mascarar(str(k).zfill(11)) if len(str(k)) <= 11 else mascarar(str(k).zfill(14))
                produtores = ""
            linhas.append({"nome": nome.title(), "doc": doc, "municipio": mun_nome, "guias": int(r.guias),
                           "movimentado": int(r.movimentado), "rebanho": int(reb),
                           "razao": (r.movimentado / reb) if reb > 0 else None,
                           "finalidade": fin, "destino": ufd, "fora_ce": fora, "produtores": produtores,
                           "no_cadastro": reb > 0})
        return {"linhas": linhas, "total_guias": total_guias, "total_movimentado": int(total_mov),
                "entidades": int(len(ag)), "unidade": UNIDADES[grupo], "grupo": GRUPOS[grupo]}

    def municipios(self):
        d = self.gt.groupby(["munc", "muno"]).size().reset_index()[["munc", "muno"]]
        return [{"codigo": int(r.munc), "nome": r.muno.title()} for r in d.sort_values("muno").itertuples()]


# ======================================================================== servidor
PAGINA = r"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Consulta de produtores e propriedades</title>
<style>
:root{--bg:#EDF0EB;--surface:#F9FAF7;--ink:#12302B;--muted:#5A6E68;--line:#D4DAD2;--soft:#E4E9E1;--brand:#1F6B5B;--ochre:#C58A17;--warn:#B3412C;--sea:#2D7BA0;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0E1A18;--surface:#152421;--ink:#E3ECE8;--muted:#92A8A1;--line:#27393A;--soft:#1D2F2C;--brand:#58BBA3;--ochre:#E2A93D;--warn:#E8856F;--sea:#6DB2D3;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 'Segoe UI',system-ui,sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:20px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:18px;margin:0 0 10px}h3{font-size:15px;margin:16px 0 6px}
.sub{color:var(--muted);margin:0 0 14px}
.aviso{background:var(--soft);border-left:3px solid var(--ochre);padding:8px 12px;border-radius:0 6px 6px 0;font-size:13.5px;margin-bottom:16px}
.tabs{display:flex;gap:6px;margin-bottom:14px}.tabs button{border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:6px 16px;cursor:pointer;font:inherit;font-weight:600}
.tabs button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:14px}
input,select,button.go{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:8px 10px}
input[type=text]{width:min(520px,100%)}button.go{background:var(--brand);color:#fff;border-color:var(--brand);cursor:pointer;font-weight:600}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}.fld{display:flex;flex-direction:column;gap:3px}.fld span{font-size:12.5px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px}th{font-size:12.5px;color:var(--muted);font-weight:600;text-align:left;padding:4px 8px 6px}
td{padding:7px 8px;border-top:1px solid var(--line);vertical-align:top}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.cl{cursor:pointer}tr.cl:hover td{background:var(--soft)}
.tag{display:inline-block;background:var(--soft);border:1px solid var(--line);border-radius:4px;padding:0 6px;font-size:12px;color:var(--muted)}
.warn{color:var(--warn);font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:8px 0 4px}.kpis div{border-left:3px solid var(--line);padding-left:10px}.kpis b{display:block;font-size:22px;line-height:1.1}.kpis span{font-size:13px;color:var(--muted)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media (max-width:860px){.cols{grid-template-columns:1fr}}
.bars{display:flex;align-items:flex-end;gap:4px;height:70px}.bars i{flex:1;background:var(--brand);border-radius:2px 2px 0 0;min-height:2px}.mes{display:flex;gap:4px;font-size:11px;color:var(--muted)}.mes span{flex:1;text-align:center}
a.l{color:var(--brand);cursor:pointer;text-decoration:underline}.hid{display:none}.mut{color:var(--muted)}
.scroll{overflow-x:auto}
</style></head><body><div class="wrap">
<h1>Consulta de produtores e propriedades</h1>
<p class="sub">Cadastro de rebanho cruzado com as GTAs. <span id="ref"></span></p>
<div class="aviso">Ferramenta <b>local</b>: roda só neste computador e mostra dados pessoais. Use apenas para o trabalho da ADAGRI, não compartilhe prints com CPF e feche o programa ao terminar.</div>
<div class="tabs"><button id="t1" class="on">Buscar</button><button id="t2">Quem mais movimenta</button></div>

<section id="s1">
  <div class="panel"><div class="row"><div class="fld"><span>Nome, CPF/CNPJ, código do produtor ou da propriedade</span>
    <input type="text" id="q" placeholder="Ex.: maria silva, 12345678901 ou 23028002352" autofocus></div><button class="go" id="bq">Buscar</button></div>
    <div id="res" style="margin-top:12px"></div></div>
  <div id="det"></div>
</section>

<section id="s2" class="hid">
  <div class="panel"><div class="row">
    <div class="fld"><span>Grupo de animais</span><select id="rg"></select></div>
    <div class="fld"><span>Agrupar por</span><select id="rp"><option value="propriedade">Propriedade</option><option value="produtor">Produtor (CPF/CNPJ)</option></select></div>
    <div class="fld"><span>Ordenar por</span><select id="ro"><option value="movimentado">Animais movimentados</option><option value="guias">Número de guias</option></select></div>
    <div class="fld"><span>Município de origem</span><select id="rm"></select></div>
    <div class="fld"><span>De</span><input type="date" id="rd"></div><div class="fld"><span>Até</span><input type="date" id="ra"></div>
    <button class="go" id="br">Ver ranking</button><button class="go" id="bc" style="background:var(--sea);border-color:var(--sea)">Baixar CSV</button></div>
    <div id="rsum" class="kpis"></div></div>
  <div class="panel scroll" id="rtab"></div>
</section>
</div>
<script>
var $=function(i){return document.getElementById(i)};
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
var nf=new Intl.NumberFormat('pt-BR');function fN(n){return nf.format(Math.round(n))}
function fR(r){return r==null?'<span class="mut">sem cadastro</span>':(r>1?'<span class="warn">'+r.toFixed(1).replace('.',',')+'x</span>':r.toFixed(2).replace('.',',')+'x')}
function cap(s){return String(s||'').toLowerCase().replace(/(^|\s)\S/g,function(c){return c.toUpperCase()})}
function api(p){return fetch(p).then(function(r){return r.json()})}
$('t1').onclick=function(){tab(1)};$('t2').onclick=function(){tab(2)};
function tab(n){$('s1').className=n==1?'':'hid';$('s2').className=n==2?'':'hid';$('t1').className=n==1?'on':'';$('t2').className=n==2?'on':''}
function buscar(){var q=$('q').value;api('/api/buscar?q='+encodeURIComponent(q)).then(function(r){
  if(!r.length){$('res').innerHTML='<p class="mut">Nada encontrado. Digite pelo menos 3 letras do nome, ou o CPF/CNPJ completo.</p>';return}
  $('res').innerHTML='<table><tr><th>Tipo</th><th>Nome</th><th>Documento / código</th><th>Detalhe</th></tr>'+r.map(function(x){
    return '<tr class="cl" data-t="'+x.tipo+'" data-i="'+x.id+'"><td><span class="tag">'+x.tipo+'</span></td><td>'+esc(x.nome)+'</td><td>'+esc(x.doc)+'</td><td>'+esc(x.detalhe)+'</td></tr>'}).join('')+'</table>'})}
$('bq').onclick=buscar;$('q').onkeydown=function(e){if(e.key=='Enter')buscar()};
$('res').onclick=function(e){var tr=e.target.closest('tr.cl');if(tr)abrir(tr.dataset.t,tr.dataset.i)};
function abrir(t,i){api('/api/'+t+'?id='+i).then(function(d){$('det').innerHTML=card(d);window.scrollTo({top:$('det').offsetTop-10,behavior:'smooth'})})}
document.addEventListener('click',function(e){var a=e.target.closest('a.l');if(a&&a.dataset.t)abrir(a.dataset.t,a.dataset.i);
  if(e.target.id=='mostra'){var d=e.target.dataset;e.target.previousElementSibling.textContent=d.on=='1'?d.f:d.m;d.on=d.on=='1'?'0':'1';e.target.textContent=d.on=='1'?'mostrar completo':'esconder'}});
function rebs(o){var k=Object.keys(o||{});return k.length?k.map(function(g){return esc(g)+' <b>'+fN(o[g])+'</b>'}).join(' · '):'<span class="mut">sem rebanho</span>'}
function gtaBloco(t,r){
  if(!r.total)return '<h3>'+t+'</h3><p class="mut">Nenhuma GTA encontrada.</p>';
  var mx=Math.max.apply(null,r.meses.concat([1])),M=['J','F','M','A','M','J','J','A','S','O','N','D'];
  var h='<h3>'+t+' <span class="tag">'+fN(r.total)+' guias</span></h3>';
  h+='<div class="scroll"><table><tr><th>Grupo</th><th class="n">Guias</th><th class="n">Animais movimentados</th><th class="n">Rebanho cadastrado</th><th class="n">Movimentado / rebanho</th></tr>'+r.grupos.map(function(g){
    return '<tr><td>'+esc(g.grupo)+'</td><td class="n">'+fN(g.guias)+'</td><td class="n">'+fN(g.movimentado)+' <span class="mut">'+g.unidade+'</span></td><td class="n">'+fN(g.rebanho)+'</td><td class="n">'+fR(g.razao)+'</td></tr>'}).join('')+'</table></div>';
  h+='<div class="bars" style="margin-top:12px">'+r.meses.map(function(n){return '<i title="'+n+' guias" style="height:'+(n/mx*100)+'%"></i>'}).join('')+'</div><div class="mes">'+M.map(function(m){return '<span>'+m+'</span>'}).join('')+'</div>';
  h+='<div class="cols"><div><h3>Finalidades</h3>'+r.finalidades.map(function(f){return esc(f.nome)+' <b>'+fN(f.guias)+'</b>'}).join('<br>')+'</div>';
  h+='<div><h3>Principais destinos</h3>'+r.destinos.map(function(d){return esc(d.nome)+' <b>'+fN(d.guias)+'</b> guias'}).join('<br>')+'</div></div>';
  h+='<h3>Últimas guias</h3><div class="scroll"><table><tr><th>Número</th><th>Data</th><th>Espécie</th><th>Finalidade</th><th class="n">Qtde</th><th>Destino</th></tr>'+r.ultimas.map(function(u){
    return '<tr><td>'+u.numero+'</td><td>'+u.data+'</td><td>'+esc(u.especie)+'</td><td>'+esc(u.fin)+'</td><td class="n">'+fN(u.quantidade)+'</td><td>'+esc(u.destino)+'</td></tr>'}).join('')+'</table></div>';
  return h}
function esps(l){return l.length?'<table><tr><th>Espécie</th><th class="n">Quantidade</th></tr>'+l.map(function(e){return '<tr><td>'+esc(e.especie)+'</td><td class="n">'+fN(e.quantidade)+'</td></tr>'}).join('')+'</table>':'<p class="mut">Sem rebanho declarado.</p>'}
function card(d){
  if(!d||d.erro)return '<div class="panel">Não encontrado.</div>';
  var h='<div class="panel">';
  if(d.tipo=='produtor'){
    h+='<h2>'+esc(d.nome)+(d.apelido?' <span class="mut">('+esc(d.apelido)+')</span>':'')+'</h2><p class="sub">CPF/CNPJ <span>'+esc(d.doc)+'</span> <a class="l" id="mostra" data-m="'+esc(d.doc)+'" data-f="'+esc(d.doc_completo)+'" data-on="1">mostrar completo</a>'+(d.telefone?' · Telefone '+esc(d.telefone):'')+'</p>';
    h+='<div class="kpis"><div><b>'+d.propriedades.length+'</b><span>propriedades</span></div><div><b>'+fN(d.saida.total)+'</b><span>GTAs como origem</span></div><div><b>'+fN(d.entrada.total)+'</b><span>GTAs como destino</span></div></div>';
    h+='<p class="mut" style="font-size:13px">As GTAs abaixo são ligadas ao produtor pelo CPF/CNPJ e, quando ele é o único produtor da propriedade, também pelo código da propriedade. Em propriedade com vários produtores, a coluna “GTAs saída da propriedade” mostra o total da propriedade, não só dele.</p>';
    h+='<h3>Propriedades</h3><div class="scroll"><table><tr><th>Código</th><th>Nome</th><th>Município</th><th class="n">Área (ha)</th><th class="n">Produtores</th><th>Rebanho</th><th class="n">GTAs saída da propriedade</th></tr>'+d.propriedades.map(function(p){
      return '<tr><td><a class="l" data-t="propriedade" data-i="'+p.codigo+'">'+p.codigo+'</a></td><td>'+esc(p.nome)+'</td><td>'+esc(cap(p.municipio))+'</td><td class="n">'+(p.area==null?'':fN(p.area))+'</td><td class="n">'+p.produtores+'</td><td>'+rebs(p.rebanho)+'</td><td class="n">'+fN(p.gtas_saida)+'</td></tr>'}).join('')+'</table></div>';
  }else{
    h+='<h2>'+esc(d.nome||('Propriedade '+d.id))+'</h2><p class="sub">Código '+d.id+' · '+esc(cap(d.municipio))+(d.area!=null?' · '+fN(d.area)+' ha':'')+'</p>';
    h+='<h3>Produtores vinculados ('+d.produtores.length+')</h3>'+(d.produtores.length?d.produtores.map(function(p){return '<a class="l" data-t="produtor" data-i="'+p.id+'">'+esc(p.nome)+'</a> <span class="mut">'+esc(p.doc)+'</span>'}).join('<br>'):'<span class="mut">nenhum</span>');
  }
  h+='<h3>Rebanho cadastrado</h3>'+esps(d.especies)+gtaBloco('GTAs com origem aqui',d.saida)+gtaBloco('GTAs com destino aqui',d.entrada);
  return h+'</div>'}
function params(){return new URLSearchParams({grupo:$('rg').value,por:$('rp').value,ordem:$('ro').value,mun:$('rm').value,de:$('rd').value,ate:$('ra').value}).toString()}
function ranking(){api('/api/ranking?'+params()).then(function(r){
  var prop=$('rp').value=='propriedade';
  $('rsum').innerHTML='<div><b>'+fN(r.total_guias)+'</b><span>guias no filtro</span></div><div><b>'+fN(r.total_movimentado)+'</b><span>'+esc(r.unidade)+' movimentados</span></div><div><b>'+fN(r.entidades)+'</b><span>'+(prop?'propriedades':'produtores')+' com guias</span></div>';
  $('rtab').innerHTML=r.linhas.length?'<table><tr><th>#</th><th>'+(prop?'Propriedade':'Produtor')+'</th><th>Município</th><th class="n">Guias</th><th class="n">'+esc(r.unidade)+' movimentados</th><th class="n">Rebanho cadastrado</th><th class="n">Mov./rebanho</th><th>Finalidade principal</th><th class="n">Fora do CE</th></tr>'+r.linhas.map(function(l,i){
    return '<tr><td>'+(i+1)+'</td><td>'+esc(l.nome)+'<br><span class="mut">'+esc(l.doc)+(l.produtores?' · '+esc(l.produtores):'')+'</span></td><td>'+esc(l.municipio)+'</td><td class="n">'+fN(l.guias)+'</td><td class="n">'+fN(l.movimentado)+'</td><td class="n">'+fN(l.rebanho)+'</td><td class="n">'+fR(l.razao)+'</td><td>'+esc(l.finalidade)+'</td><td class="n">'+Math.round(l.fora_ce*100)+'%</td></tr>'}).join('')+'</table><p class="mut" style="font-size:13px">Em vermelho: movimentou mais animais do que o rebanho cadastrado. Pode ser rebanho desatualizado, compra e revenda, ou erro de cadastro. Vale conferir.</p>':'<p class="mut">Nenhuma GTA para esse filtro.</p>'})}
$('br').onclick=ranking;$('bc').onclick=function(){location.href='/api/ranking.csv?'+params()};
api('/api/info').then(function(i){
  $('ref').textContent='Rebanho: posição de '+i.ref+'. GTAs até '+i.gt_ate+'.';
  $('rg').innerHTML=i.grupos.map(function(g,k){return '<option value="'+k+'">'+esc(g)+'</option>'}).join('');
  $('rm').innerHTML='<option value="">Todos</option>'+i.municipios.map(function(m){return '<option value="'+m.codigo+'">'+esc(m.nome)+'</option>'}).join('')})
</script></body></html>
"""


def criar_handler(base):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj, ensure_ascii=False,
                           default=lambda o: int(o) if isinstance(o, np.integer) else float(o)).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/":
                    b = PAGINA.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                elif u.path == "/api/info":
                    self._json({"ref": base.ref.strftime("%d/%m/%Y") if base.ref else "?",
                                "gt_ate": base.gt_ate.strftime("%d/%m/%Y"), "grupos": GRUPOS,
                                "municipios": base.municipios()})
                elif u.path == "/api/buscar":
                    self._json(base.buscar(q.get("q", "")))
                elif u.path == "/api/produtor":
                    self._json(base.produtor(int(q["id"])) or {"erro": "nao encontrado"})
                elif u.path == "/api/propriedade":
                    self._json(base.propriedade(int(q["id"])) or {"erro": "nao encontrado"})
                elif u.path in ("/api/ranking", "/api/ranking.csv"):
                    csv_ = u.path.endswith(".csv")
                    r = base.ranking(int(q.get("grupo", 0)), q.get("de") or None, q.get("ate") or None,
                                     int(q["mun"]) if q.get("mun") else None, q.get("por", "propriedade"),
                                     q.get("ordem", "movimentado"), 5000 if csv_ else 50)
                    if not csv_:
                        self._json(r)
                    else:
                        buf = io.StringIO()
                        w = csv.writer(buf, delimiter=";")
                        w.writerow(["posicao", "nome", "documento_ou_codigo", "municipio", "guias", "movimentado",
                                    "rebanho_cadastrado", "movimentado_sobre_rebanho", "finalidade_principal",
                                    "uf_destino_principal", "pct_fora_ce"])
                        for i, l in enumerate(r["linhas"], 1):
                            w.writerow([i, l["nome"], l["doc"], l["municipio"], l["guias"], l["movimentado"],
                                        l["rebanho"], "" if l["razao"] is None else f"{l['razao']:.2f}".replace(".", ","),
                                        l["finalidade"], l["destino"], f"{l['fora_ce'] * 100:.0f}"])
                        b = ("\ufeff" + buf.getvalue()).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "text/csv; charset=utf-8")
                        self.send_header("Content-Disposition", 'attachment; filename="ranking_movimentacao.csv"')
                        self.send_header("Content-Length", str(len(b)))
                        self.end_headers()
                        self.wfile.write(b)
                else:
                    self.send_error(404)
            except Exception as e:  # mostra o erro na página em vez de travar
                self._json({"erro": str(e)}, 500)
    return H


def main():
    a = sys.argv[1:]
    args = {"atualizar": "--atualizar" in a}
    for k in ("rebanho", "gta-xlsx", "porta"):
        if f"--{k}" in a:
            args[k] = a[a.index(f"--{k}") + 1]
    d = carregar_tudo(args)
    base = Base(d)
    porta = int(args.get("porta", 8765))
    srv = ThreadingHTTPServer(("127.0.0.1", porta), criar_handler(base))
    url = f"http://127.0.0.1:{porta}"
    print(f"\nPronto! Abra {url} no navegador. (Ctrl+C para encerrar)\n")
    try:
        webbrowser.open(url)
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Encerrado.")


if __name__ == "__main__":
    main()
