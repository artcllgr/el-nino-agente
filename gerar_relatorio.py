# -*- coding: utf-8 -*-
"""
Gera o relatorio HTML (com graficos) a partir de saida/facts.json.
Uso: python gerar_relatorio.py
Saida: relatorio_el_nino.html
"""
from __future__ import annotations

import base64
import io
import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BASE = Path(__file__).resolve().parent
SAIDA = BASE / "saida"
FACTS = SAIDA / "facts.json"
DEST = BASE / "relatorio_el_nino.html"


def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def grafico_serie(serie: list[dict]) -> str:
    meses = [s["mes_str"] for s in serie]
    temp_z = [s["temp_z"] for s in serie]
    prec_z = [s["precip_z"] for s in serie]
    frac = [s["frac_quente"] * 100 for s in serie]

    fig, ax1 = plt.subplots(figsize=(11, 4.5))
    ax1.axhline(0, color="#888", lw=0.8)
    ax1.axhspan(1.5, 3, color="#ffd6d6", alpha=0.5, zorder=0)
    ax1.axhspan(-3, -1.5, color="#d6e4ff", alpha=0.5, zorder=0)
    ax1.plot(meses, temp_z, "-o", ms=3, color="#c0392b", label="Anomalia temp. (z)")
    ax1.plot(meses, prec_z, "-s", ms=3, color="#2471a3", label="Anomalia chuva (z)")
    ax1.set_ylabel("Z-score interno")
    ax1.set_ylim(-3, 3)
    ax1.tick_params(axis="x", rotation=90, labelsize=7)
    ax2 = ax1.twinx()
    ax2.bar(meses, frac, alpha=0.18, color="#e67e22", width=0.6)
    ax2.set_ylabel("% estacoes quentes (z>=1.5)", color="#b9770e")
    ax2.set_ylim(0, 100)
    ax1.legend(loc="upper left", fontsize=8)
    ax1.set_title("Evolucao mensal das anomalias (2024-2026)")
    return fig_to_b64(fig)


def grafico_ranking(ranking: list[dict], periodo: str, top: int = 15) -> str:
    top_r = ranking[:top][::-1]
    nomes = [f"{r['uf']} ({r['regiao_nome'][:3]})" for r in top_r]
    vals = [r["indice_impacto"] for r in top_r]
    cores = [
        {"S": "#2471a3", "N": "#c0392b", "NE": "#e67e22", "CO": "#8e44ad", "SE": "#16a085"}[r["regiao"]]
        for r in top_r
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(nomes, vals, color=cores)
    ax.set_xlabel("Indice de impacto (regiao-aware)")
    ax.set_title(f"Top {top} estados mais impactados pelo El Nino ({periodo})")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:.2f}", va="center", fontsize=7)
    return fig_to_b64(fig)


def grafico_regioes(resumo: list[dict]) -> str:
    nomes = [r["regiao_nome"] for r in resumo]
    vals = [r["indice_medio"] for r in resumo]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(nomes, vals, color=["#c0392b", "#e67e22", "#8e44ad", "#16a085", "#2471a3"][: len(nomes)])
    ax.set_ylabel("Indice medio")
    ax.set_title("Impacto medio por regiao")
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
    return fig_to_b64(fig)


def html(facts: dict) -> str:
    conf = facts["confirmacao"]
    periodo = facts.get("periodo_impacto_label", "2026")
    if conf.get("confirmado"):
        det = conf.get("detalhe_regional", {})
        ordem = ["CO", "S", "SE", "N", "NE"]
        nomes_reg = {"CO": "Centro-Oeste", "S": "Sul", "SE": "Sudeste", "N": "Norte", "NE": "Nordeste"}
        linhas_det = "".join(
            f"<li><b>{nomes_reg.get(r, r)}</b>: temperatura {det[r]['temp_z']:+.2f}&sigma;, "
            f"chuva {det[r]['precip_z']:+.2f}&sigma;</li>"
            for r in ordem if r in det
        )
        bloco_conf = (
            f"<p><b>Anomalia confirmada em <span class='hl'>{conf['mes_confirmacao']}</span></b>, "
            f"com in&iacute;cio do aquecimento em {conf.get('mes_inicio_sustentado','-')}. "
            f"Nesse m&ecirc;s, <b>{conf['frac_quente']*100:.0f}%</b> das {conf['n_estacoes']} esta&ccedil;&otilde;es "
            f"apresentaram anomalia de temperatura z&nbsp;&ge;&nbsp;{facts['z_calor_conf']} "
            f"(z m&eacute;dio nacional = {conf['temp_z']:+.2f}&sigma;).</p>"
            f"<p>Crit&eacute;rio de confirma&ccedil;&atilde;o: <code>{conf.get('criterio','')}</code>. "
            f"Meses que atenderam ao crit&eacute;rio: {', '.join(conf.get('todos_meses_criterio', [])) or '-'}.</p>"
            f"<p><b>Assinatura regional na janela</b> ({', '.join(conf.get('meses_janela', []))}):</p>"
            f"<ul>{linhas_det}</ul>"
        )
    else:
        bloco_conf = f"<p>Sinal n&atilde;o sustentado no per&iacute;odo. {conf.get('motivo','')}</p>"

    linhas = []
    for r in facts["ranking_estados"]:
        linhas.append(
            "<tr>"
            f"<td>{r['ranking']}</td><td><b>{r['uf']}</b></td><td>{r['regiao_nome']}</td>"
            f"<td>{r['indice_impacto']:.2f}</td><td>{r['calor_z']:.2f}</td>"
            f"<td>{r['seca_z']:.2f}</td><td>{r['chuva_z']:.2f}</td>"
            f"<td>{r['perc_meses_quentes']:.0f}%</td><td>{r['dias_calor_extremo']}</td>"
            f"<td>{r['n_estacoes']}</td></tr>"
        )
    tabela = "\n".join(linhas)

    g_serie = grafico_serie(facts["serie_nacional"])
    g_rank = grafico_ranking(facts["ranking_estados"], periodo)
    g_reg = grafico_regioes(facts["resumo_regioes"])

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatorio El Nino 2024-2026 (INMET)</title>
<style>
 body{{font-family:Segoe UI,Arial,sans-serif;max-width:1080px;margin:0 auto;padding:32px;color:#1b1b1b;line-height:1.55}}
 h1{{border-bottom:3px solid #c0392b;padding-bottom:8px}}
 h2{{margin-top:34px;color:#8e1b12;border-left:5px solid #c0392b;padding-left:10px}}
 .meta{{color:#666;font-size:.9em}}
 .hl{{background:#ffe08a;padding:1px 6px;border-radius:4px;font-weight:bold}}
 .cards{{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}}
 .card{{flex:1;min-width:150px;background:#faf5f4;border:1px solid #f0d9d6;border-radius:10px;padding:14px}}
 .card b{{display:block;font-size:1.7em;color:#c0392b}}
 img{{width:100%;border:1px solid #eee;border-radius:8px;margin:10px 0}}
 table{{border-collapse:collapse;width:100%;font-size:.86em}}
 th,td{{border:1px solid #e2e2e2;padding:6px 8px;text-align:center}}
 th{{background:#f3ecea}}
 tr:nth-child(even){{background:#fafafa}}
 .tag{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75em;color:#fff}}
 .nota{{background:#f4f8ff;border-left:4px solid #2471a3;padding:10px 14px;border-radius:6px;font-size:.92em}}
 a{{color:#2471a3}}
</style></head><body>
<h1>El Nino &mdash; Analise de Anomalias Climaticas no Brasil</h1>
<p class="meta">Fonte: dados horarios das estacoes automaticas do INMET (2024, 2025, 2026).
Gerado em {facts['gerado_em']} &middot; Periodo: {facts['periodo_dados']['min']} a {facts['periodo_dados']['max']}
&middot; {facts['n_estacoes']} estacoes &middot; {facts['n_ufs']} UFs.</p>

<div class="cards">
  <div class="card"><b>{facts['n_estacoes']}</b>estacoes analisadas</div>
  <div class="card"><b>{facts['n_ufs']}</b>estados (UFs)</div>
  <div class="card"><b>{facts['n_observacoes_mensais']:,}</b>observacoes mensais</div>
  <div class="card"><b>{facts['z_limiar']}</b>limiar de z-score</div>
</div>

<h2>1. Quando a anomalia foi confirmada</h2>
{bloco_conf}
<p>Metodo: para cada estacao, a anomalia mensal e a diferenca em relacao a climatologia do
mes-do-ano da propria estacao; o <i>z-score interno</i> e essa anomalia dividida pelo desvio-padrao
das anomalias da estacao (z-score calculado dentro do proprio periodo 2024-2026). Considera-se
anomala a estacao-mes com |z| &ge; {facts['z_limiar']}.</p>

<h2>2. Impacto por regiao</h2>
<img src="data:image/png;base64,{g_reg}" alt="Impacto por regiao">
<p>O indice pondera a direcao esperada do El Nino em cada regiao: excesso de chuva no
<b>Sul</b>; seca no <b>Norte</b> e <b>Nordeste</b>; ondas de calor e variabilidade de chuva no
<b>Centro-Oeste</b> e <b>Sudeste</b>.</p>

<h2>3. Estados mais impactados ({periodo})</h2>
<img src="data:image/png;base64,{g_rank}" alt="Ranking de estados">
<p class="meta">Indice region-aware calculado sobre o per&iacute;odo {periodo} (da confirma&ccedil;&atilde;o/in&iacute;cio da anomalia at&eacute; o &uacute;ltimo m&ecirc;s com dados).</p>
<table>
<thead><tr><th>#</th><th>UF</th><th>Regiao</th><th>Indice</th><th>Calor (z)</th>
<th>Seca (z)</th><th>Chuva (z)</th><th>% meses quentes</th><th>Dias Tmax&ge;35</th><th>Estacoes</th></tr></thead>
<tbody>
{tabela}
</tbody></table>

<h2>4. Evolucao temporal</h2>
<img src="data:image/png;base64,{g_serie}" alt="Serie temporal de anomalias">

<h2>5. Recurso oficial e orientacoes</h2>
<div class="nota">
Para acompanhar orientacoes oficiais de saude e avisos de calor extremo, consulte o
<b>Portal Gov.br - El Nino</b>:
<a href="https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/e/el-nino" target="_blank">
gov.br/saude/el-nino</a>.<br>
Em emergencias: <b>Defesa Civil 199</b> &middot; <b>SAMU 192</b> &middot; <b>Bombeiros 193</b>.
</div>

<p class="meta">Analise gerada automaticamente a partir dos dados do INMET. O indice de impacto e
um indicador comparativo derivado dos proprios dados, nao substitui boletins oficiais de
monitoramento (INMET, ANA, CPTEC/INPE, Defesa Civil).</p>
</body></html>"""


def main() -> None:
    if not FACTS.exists():
        raise SystemExit("facts.json nao encontrado. Rode analise_el_nino.py primeiro.")
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    DEST.write_text(html(facts), encoding="utf-8")
    print(f"Relatorio gerado: {DEST}")


if __name__ == "__main__":
    main()
