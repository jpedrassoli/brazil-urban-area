"""Registro de rastreabilidade por carta, FORA do Earth Engine.

Para cada carta, monta um dicionário que explica em detalhe como ela foi gerada: fonte do mosaico, janela de
amostras de cada ano, classes que existiam no treino de cada janela, parâmetros da classificação e do
pós-processamento, de onde veio o limiar, opções de teste ligadas, versão do código e hash da configuração,
avisos automáticos e, se informadas, as métricas de acurácia (veja `evaluate.carta_metrics`).

O resultado é texto/JSON simples (uma ficha por carta e um índice em CSV), para guardar em arquivos versionados
ou em tabelas de trabalho, sem gravar nada nos assets. Só LÊ o Earth Engine (contagem de amostras).
"""
from __future__ import annotations

import datetime as dt

import ee

from . import classify, config, grids, mosaic, samples

# opções de teste que, quando ligadas, mudam o método em relação à Col 11 (padrão = desligadas)
_OPCOES_TESTE = {
    "thresholds.calibration_split": False, "thresholds.calibration_points": False,
    "thresholds.pool_years": 0, "thresholds.bootstrap": 0,
    "evaluation.independent_points": None,
}


def _get(cfg: dict, dotted: str):
    cur = cfg
    for k in dotted.split("."):
        cur = (cur or {}).get(k)
    return cur


def _faixas(janela_por_ano: dict[int, str]) -> list[dict]:
    """Junta anos seguidos que usam a mesma janela: [{"anos": "1985-1992", "janela": "1985_to_2020"}, ...]."""
    out, ini, atual = [], None, None
    for y in sorted(janela_por_ano):
        j = janela_por_ano[y]
        if j != atual:
            if atual is not None:
                out.append({"anos": f"{ini}-{prev}", "janela": atual})
            ini, atual = y, j
        prev = y
    out.append({"anos": f"{ini}-{prev}", "janela": atual})
    return out


def training_counts(carta: str, cfg: dict, table: ee.FeatureCollection | None = None) -> dict:
    """Amostras de TREINO da super carta, por janela e classe (leitura do Earth Engine).
    `table` permite testar com outra tabela de amostras (padrão: a da configuração)."""
    ctx = grids.context(carta, cfg)
    base = (table if table is not None else samples.table(cfg)).filter(ee.Filter.eq("type", "classification")).filterBounds(ctx)
    out = {}
    for j in samples.windows(cfg):
        h = base.filter(ee.Filter.eq("range", j)).aggregate_histogram("class").getInfo() or {}
        out[j] = {str(int(float(k))): int(v) for k, v in sorted(h.items())}
    return out


def provenance(carta: str, cfg: dict | None = None, with_ee: bool = True) -> dict:
    """Ficha de rastreabilidade de uma carta. `with_ee=False` evita qualquer chamada ao Earth Engine."""
    cfg = cfg or config.load()
    m, s, c, p = cfg["mosaic"], cfg["samples"], cfg["classification"], cfg["postprocess"]
    years = config.years(cfg)
    faixas = _faixas({y: classify.window_for_year(y, cfg) for y in years})
    rec: dict = {
        "carta": carta, "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "colecao": cfg["collection"], "anos": [years[0], years[-1]], "destino": cfg.get("destination"),
        "codigo": {"versao": config.code_version(), "config_sha256": config.config_hash(cfg)},
        "mosaico": {"fonte": mosaic.source_for(carta, cfg), "codificacao": m.get("encoding", "col12"),
                    "versao": m.get("version", 1)},
        "amostras": {"tabela": s["table"], "janela_por_faixa_de_anos": faixas,
                     "colecoes_de_estabilidade": s["stability_collections"], "modo": s.get("stability_mode"),
                     "janela_recente": s.get("recent_window"), "pontos_por_classe": s["points_per_class"]},
        "classificacao": {"classificador": c.get("classifier", "random_forest"), "arvores": c["trees"],
                          "amostras_urbanas": c["urban_samples"], "balanceamento": c["balance"],
                          "rotulo_das_bandas": c.get("band_labels", "by_class"), "versao": c.get("version", 1),
                          "saida": c["output"]},
        "limiar": {"imagem": p["threshold_image"], "origem": "Col 11" if "thresholdMedianByCartaImg" in p["threshold_image"] else "outra",
                   "fator_final": p["final_factor"], "fator_vizinhanca": p["neighborhood_factor"]},
        "pos_processamento": {"janela_temporal_anos": p["temporal_window"], "raio_vizinhanca_px": p["kernel_radius_px"],
                              "ponto_de_quebra": {"fracao_minima": p["breakpoint_min_fraction"], "anos_minimos": p["breakpoint_min_years"]},
                              "buracos_px": p["hole_px"], "ruido_px": p["noise_px"], "irs_ate": p["irs_last_year"],
                              "versao": p["version"]},
        "opcoes_de_teste_ligadas": {k: _get(cfg, k) for k, padrao in _OPCOES_TESTE.items() if _get(cfg, k) != padrao},
        "produtos": {"probabilidades": f"{config.asset_path(c['folder'], cfg=cfg)} (grid={carta}, version={c.get('version', 1)})",
                     "mapa_final": config.asset_path(p["folder"], f"mapa_{carta}", cfg=cfg)},
        "avisos": [],
    }
    if c.get("classifier", "random_forest") != "random_forest":
        rec["opcoes_de_teste_ligadas"]["classification.classifier"] = c["classifier"]
    if c.get("band_labels", "by_class") == "by_position":
        rec["avisos"].append("rótulo das bandas por posição (comportamento da Col 11): classe ausente no treino desloca as bandas")
    if with_ee:
        cont = grids.context_fc(carta, cfg).aggregate_array(cfg["grids"]["grid_field"]).getInfo()
        cnt = training_counts(carta, cfg)
        rec["contexto_cartas"] = sorted(cont)
        rec["amostras_treino_por_janela"] = cnt
        for j, h in cnt.items():
            faltam = [k for k in ("1", "2", "3", "4") if k not in h]
            if faltam:
                rec["avisos"].append(f"janela {j}: sem amostras de treino das classes {', '.join(faltam)} na super carta")
    rec["pipeline_texto"] = texto(rec)
    return rec


def texto(rec: dict) -> str:
    """Resumo legível do caminho que a carta seguiu."""
    mo, am, cl, li, po = rec["mosaico"], rec["amostras"], rec["classificacao"], rec["limiar"], rec["pos_processamento"]
    faixas = "; ".join(f"{f['anos']} -> janela {f['janela']}" for f in am["janela_por_faixa_de_anos"])
    linhas = [
        f"Carta {rec['carta']}, Coleção {rec['colecao']}, anos {rec['anos'][0]}-{rec['anos'][1]}.",
        f"Mosaico: {mo['fonte']} (codificação {mo['codificacao']}, versão {mo['versao']}).",
        f"Amostras de treino: tabela {am['tabela']}; janela por ano: {faixas}.",
        f"Classificação: {cl['classificador']} com {cl['arvores']} árvores, {cl['amostras_urbanas']} amostras urbanas e "
        f"{cl['amostras_urbanas'] * cl['balanceamento']} não urbanas; bandas rotuladas por {cl['rotulo_das_bandas']}.",
        f"Limiar: {li['origem']} ({li['imagem']}), fator final {li['fator_final']}.",
        f"Pós-processamento: média temporal ±{po['janela_temporal_anos']} anos, vizinhança {po['raio_vizinhanca_px']} px, "
        f"ponto de quebra {po['ponto_de_quebra']['fracao_minima']:.0%} / {po['ponto_de_quebra']['anos_minimos']} anos, "
        f"buracos < {po['buracos_px']} px, ruído < {po['ruido_px']} px, IRS até {po['irs_ate']}.",
        "Opções de teste ligadas: " + (", ".join(f"{k}={v}" for k, v in rec["opcoes_de_teste_ligadas"].items()) or "nenhuma") + ".",
        f"Código {rec['codigo']['versao']}, configuração {rec['codigo']['config_sha256'][:12]}.",
    ]
    if rec["avisos"]:
        linhas.append("AVISOS: " + " | ".join(rec["avisos"]))
    return "\n".join(linhas)
