"""Calcula os RESUMOS do rebanho (o que o painel realmente usa). Pequenos: alguns milhares de linhas."""
import numpy as np
import pandas as pd

from rebanho_comum import ESPECIES, FAIXAS_LIM, LIMITE_GRUPO

TODAS = len(FAIXAS_LIM)  # faixa 7 = "todas as faixas" (contagem exata de propriedades)


def _faixa(q):
    return (np.searchsorted(FAIXAS_LIM, q, side="right") - 1).astype("int64")


def _cubo(df, chave):
    """df: municipio_codigo, <chave>, propriedade_codigo, q -> municipio_codigo, chave, faixa, propriedades, quantidade."""
    df = df.copy()
    df["faixa"] = _faixa(df["q"].values)
    a = df.groupby(["municipio_codigo", chave, "faixa"]).agg(
        propriedades=("propriedade_codigo", "nunique"), quantidade=("q", "sum")).reset_index()
    b = df.groupby(["municipio_codigo", chave]).agg(
        propriedades=("propriedade_codigo", "nunique"), quantidade=("q", "sum")).reset_index()
    b["faixa"] = TODAS
    out = pd.concat([a, b], ignore_index=True)
    out["quantidade"] = out["quantidade"].round().astype("int64")
    return out[["municipio_codigo", chave, "faixa", "propriedades", "quantidade"]]


def calcular(reb, prop, vinc):
    """reb(produtor_codigo, propriedade_codigo, especie, quantidade), prop(propriedade_codigo, municipio_codigo,
    municipio_nome, latitude, longitude), vinc(produtor_codigo, propriedade_codigo) -> dict de DataFrames."""
    prop = prop.copy()
    prop["municipio_codigo"] = prop["municipio_codigo"].astype("int64")
    df = reb[["produtor_codigo", "propriedade_codigo", "especie", "quantidade"]].merge(
        prop[["propriedade_codigo", "municipio_codigo"]], on="propriedade_codigo", how="inner")
    df["grupo"] = df["especie"].map(lambda c: ESPECIES[c][1]).astype("int64")
    df["q"] = df["quantidade"].astype("float64")

    # valores suspeitos: acima do limite de plausibilidade do grupo (ficam fora dos totais)
    sus_mask = df["q"] > df["grupo"].map(LIMITE_GRUPO)
    sus = df[sus_mask].copy()
    ok = df[~sus_mask]

    cubo_especie = _cubo(ok, "especie")
    soma = ok.groupby(["produtor_codigo", "propriedade_codigo", "grupo", "municipio_codigo"], as_index=False)["q"].sum()
    cubo_grupo = _cubo(soma, "grupo")

    # por município
    n_props = prop.groupby("municipio_codigo").size()
    vm = vinc.merge(prop[["propriedade_codigo", "municipio_codigo"]], on="propriedade_codigo", how="inner")
    n_prod = vm.groupby("municipio_codigo")["produtor_codigo"].nunique()
    props_reb = set(ok["propriedade_codigo"])
    n_reb = prop[prop["propriedade_codigo"].isin(props_reb)].groupby("municipio_codigo").size()
    lat = pd.to_numeric(prop["latitude"], errors="coerce")
    lon = pd.to_numeric(prop["longitude"], errors="coerce")
    tem = lat.notna() & lon.notna()
    n_coord = prop[tem].groupby("municipio_codigo").size()
    nomes = prop.groupby("municipio_codigo")["municipio_nome"].first()
    municipio = pd.DataFrame({"municipio_nome": nomes, "propriedades": n_props, "produtores": n_prod,
                              "propriedades_com_rebanho": n_reb, "propriedades_com_coordenada": n_coord}).fillna(0)
    municipio = municipio.reset_index().rename(columns={"index": "municipio_codigo"})
    for c in ("propriedades", "produtores", "propriedades_com_rebanho", "propriedades_com_coordenada"):
        municipio[c] = municipio[c].astype("int64")

    suspeito = pd.DataFrame({"especie": sus["especie"].values, "municipio_codigo": sus["municipio_codigo"].values,
                             "quantidade": sus["quantidade"].values,
                             "limite": sus["grupo"].map(LIMITE_GRUPO).astype("int64").values})
    suspeito = suspeito.sort_values("quantidade", ascending=False).reset_index(drop=True)

    fora = int((tem & ((lat < -8) | (lat > -2.5) | (lon < -42) | (lon > -37))).sum())
    qualidade = {"propriedades": int(len(prop)), "produtores": int(vinc["produtor_codigo"].nunique()),
                 "vinculos": int(len(vinc)), "propriedades_com_rebanho": int(len(props_reb & set(prop["propriedade_codigo"]))),
                 "sem_coordenada": int((~tem).sum()), "coordenada_fora_ce": fora, "valores_suspeitos": int(len(suspeito))}
    return {"cubo_especie": cubo_especie, "cubo_grupo": cubo_grupo, "municipio": municipio, "suspeito": suspeito,
            "qualidade": qualidade}
