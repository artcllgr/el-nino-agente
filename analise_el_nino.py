# -*- coding: utf-8 -*-
"""
Analise El Nino - INMET (2024, 2025, 2026)
==========================================
Le os CSV anuais de TODAS as estacoes automaticas do INMET e produz:

  1) Agregacao horaria -> diaria -> mensal por estacao
  2) Z-score interno do periodo (deseasonalizado por mes-do-ano)
  3) Deteccao de anomalias (calor/frio, seca/excesso de chuva) por estacao/mes
  4) Agregacao por UF e por regiao
  5) Determinacao de QUANDO a anomalia foi confirmada
  6) Ranking dos ESTADOS mais impactados (regiao-aware)
  7) facts.json (consumido pelo app/agente) + CSVs de apoio

Saidas em ./saida/
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------- #
# Configuracao
# ----------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
ANOS = ["2024", "2025", "2026"]
SAIDA = BASE_DIR / "saida"
SAIDA.mkdir(exist_ok=True)

# Limiar do z-score para marcar uma estacao/mes como anomalo
Z_LIMIAR = 1.5

# Criterio de CONFIRMACAO da anomalia (assinatura de calor ampla e sustentada)
Z_CALOR_CONF = 1.0      # anomalia nacional de temperatura minima (em sigmas)
FRAC_CONF = 0.40        # fracao minima de estacoes com z >= Z_CALOR_CONF

# Indices posicionais das colunas de interesse (0-based, separador ';')
# 0 Data | 2 Precipitacao(mm) | 6 Radiacao | 7 Temp bulbo seco | 9 Temp MAX | 10 Temp MIN | 15 Umidade rel
COL_DATA, COL_PRECIP, COL_RAD, COL_TEMP, COL_TMAX, COL_TMIN, COL_RH = 0, 2, 6, 7, 9, 10, 15
N_HORAS_DIA = 24

# Limiares fisicos para contagem de extremos
TMAX_EXTREMO = 35.0     # dia muito quente (Tmax >= 35 C)
PRECIP_HEAVY = 50.0     # dia de chuva intensa (>= 50 mm)

REGIOES_NOME = {
    "N": "Norte",
    "NE": "Nordeste",
    "CO": "Centro-Oeste",
    "SE": "Sudeste",
    "S": "Sul",
}

# Direcao esperada do impacto do El Nino por regiao (sinal do efeito)
#   S  -> excesso de chuva
#   N, NE -> seca/estiagem
#   CO, SE -> ondas de calor / variabilidade de chuva
PERFIL_REGIAO = {
    "S": {"chuva": +1, "seca": 0, "calor": 0.4},
    "N": {"chuva": 0, "seca": +1, "calor": 0.6},
    "NE": {"chuva": 0, "seca": +1, "calor": 0.6},
    "CO": {"chuva": 0, "seca": 0.3, "calor": +1},
    "SE": {"chuva": 0, "seca": 0.2, "calor": +1},
}

RE_META = re.compile(r"^([A-Z ]+):;(.*)$")


# ----------------------------------------------------------------------------- #
# 1. Ingestao
# ----------------------------------------------------------------------------- #
def ler_metadados(path: Path) -> dict:
    """Le as 8 linhas de cabecalho (REGIAO, UF, ESTACAO, CODIGO, LAT, LON...)."""
    meta: dict = {}
    with path.open("r", encoding="latin-1") as fh:
        for _ in range(8):
            linha = fh.readline().strip("\n")
            m = RE_META.match(linha)
            if m:
                meta[m.group(1).strip()] = m.group(2).strip()
    return meta


def ler_estacao(path: Path) -> pd.DataFrame:
    """Le o bloco horario de uma estacao e retorna metricas DIARIAS."""
    df = pd.read_csv(
        path,
        sep=";",
        skiprows=9,          # pula metadados + linha de cabecalho
        header=None,
        decimal=",",
        encoding="latin-1",
        engine="c",
        usecols=[COL_DATA, COL_PRECIP, COL_RAD, COL_TEMP, COL_TMAX, COL_TMIN, COL_RH],
        names=["Data", "precip", "rad", "temp", "tmax", "tmin", "rh"],
        on_bad_lines="skip",
    )
    df["Data"] = pd.to_datetime(df["Data"], format="%Y/%m/%d", errors="coerce")
    df = df.dropna(subset=["Data"])
    for c in ("precip", "rad", "temp", "tmax", "tmin", "rh"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Contagem de horas validas ajuda a descartar dias com falha de sensor
    df["n_horas"] = df["temp"].notna().astype(int)

    diario = df.groupby("Data").agg(
        n_horas=("n_horas", "sum"),
        temp=("temp", "mean"),
        tmax=("tmax", "max"),
        tmin=("tmin", "min"),
        rh=("rh", "mean"),
        precip=("precip", "sum"),
        rad=("rad", "mean"),
    )
    # Exige pelo menos metade do dia com leitura de temperatura
    diario = diario[diario["n_horas"] >= N_HORAS_DIA // 2]
    diario["precip"] = diario["precip"].fillna(0.0)
    return diario


def coletar_estacoes() -> pd.DataFrame:
    """Percorre as pastas anuais e devolve a tabela MENSAL por estacao."""
    registros = []
    for ano in ANOS:
        pasta = BASE_DIR / ano
        if not pasta.exists():
            continue
        # glob no Windows e case-insensitive -> deduplicar por nome real
        arquivos = sorted({p for p in pasta.iterdir() if p.suffix.lower() == ".csv"})
        print(f"[{ano}] {len(arquivos)} estacoes encontradas")
        for i, arq in enumerate(arquivos, 1):
            try:
                meta = ler_metadados(arq)
                diario = ler_estacao(arq)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! falha em {arq.name}: {exc}")
                continue
            if diario.empty:
                continue

            mes = diario.groupby(diario.index.to_period("M")).agg(
                temp=("temp", "mean"),
                tmax=("tmax", "mean"),
                tmax_abs=("tmax", "max"),
                tmin=("tmin", "mean"),
                rh=("rh", "mean"),
                precip=("precip", "sum"),
                hot_days=("tmax", lambda s: int((s >= TMAX_EXTREMO).sum())),
                heavy_rain=("precip", lambda s: int((s >= PRECIP_HEAVY).sum())),
                n_dias=("temp", "size"),
            ).reset_index()
            mes = mes.rename(columns={"index": "mes"})
            mes["mes"] = mes.iloc[:, 0].astype(str)

            registros.append(
                pd.DataFrame(
                    {
                        "regiao": meta.get("REGIAO", ""),
                        "uf": meta.get("UF", ""),
                        "estacao": meta.get("ESTACAO", ""),
                        "codigo": meta.get("CODIGO (WMO)", ""),
                        "lat": meta.get("LATITUDE", "").replace(",", "."),
                        "lon": meta.get("LONGITUDE", "").replace(",", "."),
                        "mes": mes["mes"].values,
                        "temp": mes["temp"].values,
                        "tmax": mes["tmax"].values,
                        "tmax_abs": mes["tmax_abs"].values,
                        "tmin": mes["tmin"].values,
                        "rh": mes["rh"].values,
                        "precip": mes["precip"].values,
                        "hot_days": mes["hot_days"].values,
                        "heavy_rain": mes["heavy_rain"].values,
                        "n_dias": mes["n_dias"].values,
                    }
                )
            )
            if i % 50 == 0:
                print(f"  ... {i}/{len(arquivos)}")

    bruto = pd.concat(registros, ignore_index=True)
    bruto["uf"] = bruto["uf"].str.strip()
    bruto["regiao"] = bruto["regiao"].str.strip()
    bruto["mes"] = pd.PeriodIndex(bruto["mes"], freq="M")
    bruto["ano"] = bruto["mes"].dt.year
    bruto["mes_num"] = bruto["mes"].dt.month
    bruto["mes_str"] = bruto["mes"].astype(str)
    bruto["chave"] = bruto["regiao"] + "_" + bruto["uf"] + "_" + bruto["codigo"] + "_" + bruto["estacao"]
    return bruto


# ----------------------------------------------------------------------------- #
# 2. Z-score interno (deseasonalizado)
# ----------------------------------------------------------------------------- #
def calcular_anomalias(df: pd.DataFrame) -> pd.DataFrame:
    """Anomalia = valor - climatologia do mes-do-ano da propria estacao.
    Z = anomalia / desvio-padrao das anomalias da estacao (z-score interno)."""
    df = df.copy()
    for var in ("temp", "tmax", "tmin", "precip", "rh", "hot_days"):
        # climatologia mensal (mes-do-ano) por estacao
        clim = df.groupby(["chave", "mes_num"])[var].transform("mean")
        df[f"{var}_anom"] = df[var] - clim
        # desvio-padrao das anomalias por estacao (medida interna de dispersao)
        dp = df.groupby("chave")[f"{var}_anom"].transform("std")
        dp = dp.replace(0, np.nan)
        df[f"{var}_z"] = df[f"{var}_anom"] / dp
    return df


# ----------------------------------------------------------------------------- #
# 3. Agregacao por UF / regiao / nacional
# ----------------------------------------------------------------------------- #
def agregar(df: pd.DataFrame) -> pd.DataFrame:
    """Para cada (uf, mes) calcula fracao de estacoes anomalas e medias."""
    def _agg(s: pd.DataFrame) -> pd.Series:
        n = max(s["chave"].nunique(), 1)
        return pd.Series(
            {
                "n_est": n,
                "temp_z": s["temp_z"].mean(),
                "precip_z": s["precip_z"].mean(),
                "frac_quente": (s["temp_z"] >= Z_LIMIAR).mean(),
                "frac_frio": (s["temp_z"] <= -Z_LIMIAR).mean(),
                "frac_seco": (s["precip_z"] <= -Z_LIMIAR).mean(),
                "frac_umido": (s["precip_z"] >= Z_LIMIAR).mean(),
                "hot_days": s["hot_days"].sum(),
                "heavy_rain": s["heavy_rain"].sum(),
                "precip_mm_medio": s["precip"].sum() / n,
            }
        )

    resumo = (
        df.groupby(["regiao", "uf", "mes_str", "mes_num", "ano"])
        .apply(_agg, include_groups=False)
        .reset_index()
    )
    return resumo


# ----------------------------------------------------------------------------- #
# 4. Confirmacao da anomalia
# ----------------------------------------------------------------------------- #
def detectar_confirmacao(nacional: pd.DataFrame, anom: pd.DataFrame) -> dict:
    """Confirma a anomalia no 1o mes em que a assinatura de calor e:
       (a) forte  -> temp_z nacional >= Z_CALOR_CONF (1,0 sigma); e
       (b) ampla  -> >= FRAC_CONF (40%) das estacoes com z >= Z_CALOR_CONF.
    Da prioridade ao cenario atual (a partir de 2026); senao usa o 1o do periodo."""
    n = nacional.sort_values("mes_str").reset_index(drop=True)
    atende = ((n["temp_z"] >= Z_CALOR_CONF) & (n["frac_calor_1"] >= FRAC_CONF)).values
    idxs = np.where(atende)[0]
    if len(idxs) == 0:
        return {"confirmado": False, "motivo": "nenhum mes atingiu o criterio amplo de calor"}

    atuais = [j for j in idxs if n.iloc[j]["ano"] >= 2026]
    j = int(atuais[0]) if atuais else int(idxs[0])

    # inicio do aquecimento: recua enquanto o mes anterior mantem sinal positivo
    k = j
    while k > 0 and n.iloc[k - 1]["temp_z"] > 0.3:
        k -= 1

    linha = n.iloc[j]
    ini = n.iloc[k]
    janela = list(n.iloc[k : j + 1]["mes_str"])

    # detalhe regional dentro da janela
    sub = anom[anom["mes_str"].isin(janela)]
    detalhe = {
        reg: {
            "temp_z": round(float(g["temp_z"].mean()), 2),
            "precip_z": round(float(g["precip_z"].mean()), 2),
        }
        for reg, g in sub.groupby("regiao")
    }

    return {
        "confirmado": True,
        "mes_confirmacao": str(linha["mes_str"]),
        "mes_inicio_sustentado": str(ini["mes_str"]),
        "janela_meses": len(janela),
        "meses_janela": janela,
        "temp_z": round(float(linha["temp_z"]), 2),
        "frac_quente": round(float(linha["frac_calor_1"]), 3),
        "n_estacoes": int(linha["n_est"]),
        "criterio": f"temp_z>= {Z_CALOR_CONF} e frac(z>= {Z_CALOR_CONF})>= {FRAC_CONF}",
        "detalhe_regional": detalhe,
        "todos_meses_criterio": [str(n.iloc[i]["mes_str"]) for i in idxs],
    }


# ----------------------------------------------------------------------------- #
# 5. Ranking dos estados mais impactados
# ----------------------------------------------------------------------------- #
def ranquear_estados(df: pd.DataFrame, periodo: list[str]) -> list[dict]:
    """Calcula um indice de impacto por UF, ponderando pela direcao esperada
    do El Nino na regiao, considerando o periodo informado (ex.: 2026)."""
    sub = df[df["mes_str"].isin(periodo)]
    saida = []
    for (regiao, uf), s in sub.groupby(["regiao", "uf"]):
        perfil = PERFIL_REGIAO.get(regiao, {"chuva": 0, "seca": 0, "calor": 0})
        # medias normalizadas
        calor = float(np.nanmean(np.clip(s["temp_z"], 0, None)))          # so calor
        seca = float(np.nanmean(np.clip(-s["precip_z"], 0, None)))         # deficit
        chuva = float(np.nanmean(np.clip(s["precip_z"], 0, None)))         # excesso

        score = (
            perfil["calor"] * calor
            + perfil["seca"] * seca
            + perfil["chuva"] * chuva
        )
        saida.append(
            {
                "regiao": regiao,
                "regiao_nome": REGIOES_NOME.get(regiao, regiao),
                "uf": uf,
                "n_estacoes": int(s["chave"].nunique()),
                "indice_impacto": round(score, 3),
                "calor_z": round(calor, 2),
                "seca_z": round(seca, 2),
                "chuva_z": round(chuva, 2),
                "dias_calor_extremo": int(s["hot_days"].sum()),
                "dias_chuva_intensa": int(s["heavy_rain"].sum()),
                "perc_meses_quentes": round(float((s["temp_z"] >= Z_LIMIAR).mean()) * 100, 1),
                "perc_meses_secos": round(float((s["precip_z"] <= -Z_LIMIAR).mean()) * 100, 1),
                "perc_meses_umidos": round(float((s["precip_z"] >= Z_LIMIAR).mean()) * 100, 1),
            }
        )
    saida.sort(key=lambda d: d["indice_impacto"], reverse=True)
    for pos, item in enumerate(saida, 1):
        item["ranking"] = pos
    return saida


# ----------------------------------------------------------------------------- #
# Orquestracao
# ----------------------------------------------------------------------------- #
def main() -> None:
    t0 = datetime.now()
    cache = SAIDA / "estacoes_mensal.csv"
    if cache.exists() and os.environ.get("ELNINO_FORCE") != "1":
        print("Carregando cache estacoes_mensal.csv (use ELNINO_FORCE=1 p/ reprocessar)...")
        bruto = pd.read_csv(cache)
        bruto["mes"] = pd.PeriodIndex(bruto["mes"], freq="M")
        bruto["ano"] = bruto["mes"].dt.year
        bruto["mes_num"] = bruto["mes"].dt.month
        bruto["mes_str"] = bruto["mes"].astype(str)
    else:
        print("Lendo estacoes...")
        bruto = coletar_estacoes()
        bruto.to_csv(cache, index=False, encoding="utf-8-sig")
    print(f"Tabela mensal: {bruto.shape[0]} linhas, "
          f"{bruto['chave'].nunique()} estacoes, {bruto['uf'].nunique()} UFs")

    print("Calculando anomalias (z-score interno)...")
    anom = calcular_anomalias(bruto)
    anom.to_csv(SAIDA / "estacoes_anomalias.csv", index=False, encoding="utf-8-sig")

    print("Agregando por UF/regiao...")
    uf = agregar(anom)

    # serie nacional (media ponderada simples das UFs com dados)
    def _nac(s: pd.DataFrame) -> pd.Series:
        return pd.Series(
            {
                "n_est": s["chave"].nunique(),
                "temp_z": s["temp_z"].mean(),
                "precip_z": s["precip_z"].mean(),
                "frac_quente": (s["temp_z"] >= Z_LIMIAR).mean(),
                "frac_calor_1": (s["temp_z"] >= Z_CALOR_CONF).mean(),
                "frac_seco": (s["precip_z"] <= -Z_LIMIAR).mean(),
                "frac_umido": (s["precip_z"] >= Z_LIMIAR).mean(),
                "hot_days": s["hot_days"].sum(),
            }
        )

    nacional = (
        anom.groupby(["mes_str", "mes_num", "ano"])
        .apply(_nac, include_groups=False)
        .reset_index()
        .sort_values("mes_str")
    )
    uf.to_csv(SAIDA / "resumo_uf.csv", index=False, encoding="utf-8-sig")
    nacional.to_csv(SAIDA / "resumo_nacional.csv", index=False, encoding="utf-8-sig")

    print("Detectando confirmacao da anomalia...")
    confirmacao = detectar_confirmacao(nacional, anom)

    # periodo de impacto = da confirmacao/inicio da anomalia ate o ultimo mes com dados
    if confirmacao.get("confirmado"):
        inicio = confirmacao["mes_inicio_sustentado"]
        periodo_impacto = sorted(anom[anom["mes_str"] >= inicio]["mes_str"].unique().tolist())
    else:
        periodo_impacto = sorted(anom[anom["ano"] == 2026]["mes_str"].unique().tolist())
    ranking = ranquear_estados(anom, periodo_impacto)

    # serie temporal para o relatorio/app
    serie = nacional[
        ["mes_str", "temp_z", "precip_z", "frac_quente", "frac_calor_1",
         "frac_seco", "frac_umido", "hot_days", "n_est"]
    ].to_dict(orient="records")

    fatos = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "periodo_dados": {"min": str(anom["mes_str"].min()), "max": str(anom["mes_str"].max())},
        "n_estacoes": int(anom["chave"].nunique()),
        "n_ufs": int(anom["uf"].nunique()),
        "n_observacoes_mensais": int(len(anom)),
        "z_limiar": Z_LIMIAR,
        "z_calor_conf": Z_CALOR_CONF,
        "frac_conf": FRAC_CONF,
        "confirmacao": confirmacao,
        "periodo_impacto": periodo_impacto,
        "periodo_impacto_label": f"{periodo_impacto[0]} a {periodo_impacto[-1]}" if periodo_impacto else "-",
        "ranking_estados": ranking,
        "serie_nacional": serie,
        "top_impactados": ranking[:8],
        "resumo_regioes": _resumo_regioes(ranking),
    }
    (SAIDA / "facts.json").write_text(
        json.dumps(fatos, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n===== CONFIRMACAO =====")
    print(json.dumps(confirmacao, ensure_ascii=False, indent=2))
    print(f"\n===== TOP 10 ESTADOS MAIS IMPACTADOS ({fatos['periodo_impacto_label']}) =====")
    for r in ranking[:10]:
        print(
            f"{r['ranking']:>2}. {r['uf']} ({r['regiao_nome']}) "
            f"indice={r['indice_impacto']:.2f} | calor_z={r['calor_z']:.2f} "
            f"seca_z={r['seca_z']:.2f} chuva_z={r['chuva_z']:.2f} "
            f"| %meses_quentes={r['perc_meses_quentes']}"
        )
    print(f"\nConcluido em {(datetime.now() - t0).total_seconds():.1f}s -> {SAIDA}")


def _resumo_regioes(ranking: list[dict]) -> list[dict]:
    reg = {}
    for r in ranking:
        reg.setdefault(r["regiao"], []).append(r["indice_impacto"])
    out = []
    for cod, vals in reg.items():
        out.append(
            {
                "regiao": cod,
                "regiao_nome": REGIOES_NOME.get(cod, cod),
                "indice_medio": round(float(np.mean(vals)), 3),
                "n_ufs": len(vals),
            }
        )
    out.sort(key=lambda d: d["indice_medio"], reverse=True)
    return out


if __name__ == "__main__":
    main()
