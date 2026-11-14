"""Gera o snapshot dos scripts GEE exatamente como estavam quando a Coleção 11 foi produzida.

Fonte: repositórios de scripts do Code Editor (git em earthengine.googlesource.com), clonados
localmente. Para cada etapa, a versão de cada arquivo é a do último commit ANTES do horário de
referência da etapa (datado pelos assets que a etapa gerou no Earth Engine).

Uso (a partir da pasta MB_12, com os clones em referencias_gee/):
    python -I "brazil-urban-area/lulc_30m_landsat/collection 11/codes_producao/gerar_snapshot.py" referencias_gee

Saída: pastas por etapa + MANIFEST.csv (commit, data e sha256 de cada arquivo).
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
PUBLISHED = OUT.parent / "codes"

ED = ("users/edimilsonrodriguessantos/mapbiomas", "edimilson_mapbiomas")
MA = ("users/mayhirye/Publ", "mayhirye_Publ")

# etapa, horário de referência (UTC), asset que data a etapa, [(repo, caminho no repo, publicado equivalente)]
STAGES = [
    ("00_camadas_referencia", "2026-12-31T00:00:00Z",
     "Mask_Spatial_v9 (2025-05-26; scripts conhecidos só pela cópia pública de 2025-07-14)", [
        (MA, "Col10/3-MaskBuildings_v2 (copy)", "buildingsAndBuffers.js"),
        (MA, "Col10/4-Mask_Spatial_v9 (copy)", "referenceLayers.js"),
    ]),
    ("01_amostras", "2026-05-15T19:39:39Z",
     "col11/samples/stable_samples_by_range_merged_v1 (2026-05-15 19:39 UTC)", [
        (ED, "Col11/preProcessing/samplesCreation_v4.js", "stableSamples.js"),
        (ED, "mb_batch/collections.js", "mb_batch/collections.js"),
        (ED, "mb_batch/listsAndDicts.js", "mb_batch/listsAndDicts.js"),
    ]),
    ("02_classificacao", "2026-05-16T13:30:00Z",
     "PROB-COL11-V1 e coleções de classificação (2026-05-15 a 2026-05-26); versão de produção do "
     "script salva em 2026-05-16 13:29 UTC — commits seguintes só trocam anos/cartas de cada lote", [
        (ED, "Col11/classification/classification_batch_v3.js", "classification_batch.js"),
        (ED, "Col11/classification/class_lib.js", "class_lib.js"),
        (ED, "Col10/classificacao/mosaic_production.js", "mosaic_production.js"),
        (ED, "Col10/classificacao/index_lib.js", "index_lib.js"),
        (ED, "Col10/classificacao/preProcessing_lib.js", "preProcessing_lib.js"),
        (ED, "Col10/classificacao/renameBands.js", "renameBands.js"),
        (ED, "mb_batch/listsAndDicts.js", "mb_batch/listsAndDicts.js"),
    ]),
    ("03_limiares", "2026-05-27T04:30:03Z",
     "col11/thresholdMedianByCartaImg (2026-05-27 04:30 UTC)", [
        (ED, "meanThresholdsByGridAsImage.js", "meanThresholdsByGridAsImage.js"),
    ]),
    ("04_pos_processamento", "2026-06-02T14:12:12Z",
     "URBAN/classification_sf versão C11_v6_SF (522 cartas, 2026-06-02 14:12 a 2026-06-05 08:58 UTC)", [
        (ED, "Col11/filters/spatialAndTemporalFilters.js", "posProcessingFilter.js"),
        (ED, "Col11/filters/batchFilters.js", "temporalStabByRegion.js"),
        (ED, "Col11/results/batchResults.js", "batchResults.js"),
        (ED, "mb_batch/collections.js", "mb_batch/collections.js"),
    ]),
    ("05_vegetacao_intraurbana", "2026-07-25T21:45:07Z",
     "URBAN/vegintraurb/prob_intraurb_v1 (2026-07-25 21:45 UTC)", [
        (ED, "Col11/vegUrb/veg_urb_rev6.js", "veg_urb.js"),
        (ED, "Col11/results/batchResults.js", "batchResults.js"),
    ]),
]


def git(repo_dir: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, check=True).stdout.decode("utf-8")


def code_lines(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines()
            if l.strip() and not l.strip().startswith(("//", "/*", "*"))]


def main(clones: Path) -> None:
    rows = []
    for stage, cutoff, evidence, files in STAGES:
        for (ee_repo, local), path, published in files:
            repo_dir = clones / local
            commit = git(repo_dir, "rev-list", "-1", f"--before={cutoff}", "HEAD", "--", path).strip()
            if not commit:
                raise SystemExit(f"sem versão de {path} antes de {cutoff}")
            date = git(repo_dir, "show", "-s", "--format=%cI", commit).strip()
            content = subprocess.run(["git", "-C", str(repo_dir), "show", f"{commit}:{path}"],
                                     capture_output=True, check=True).stdout
            name = path if path.endswith(".js") else path + ".js"
            dest = OUT / stage / ee_repo / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            pub = PUBLISHED / published
            diff = "-"
            if pub.exists():
                d = [l for l in difflib.unified_diff(code_lines(pub.read_text(encoding="utf-8")),
                                                     code_lines(content.decode("utf-8", "replace")),
                                                     lineterm="", n=0)
                     if not l.startswith(("---", "+++", "@@"))]
                diff = str(len(d))
            rows.append({
                "etapa": stage,
                "require_gee": f"{ee_repo}:{path}",
                "arquivo_snapshot": dest.relative_to(OUT).as_posix(),
                "commit_gee": commit,
                "data_commit": date,
                "referencia_da_etapa": cutoff,
                "evidencia": evidence,
                "sha256": hashlib.sha256(content).hexdigest(),
                "publicado_em_codes": published,
                "linhas_de_codigo_diferentes_do_publicado": diff,
            })
    with open(OUT / "MANIFEST.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['etapa']:<26} {r['require_gee']:<75} {r['commit_gee'][:8]} {r['data_commit'][:16]} dif={r['linhas_de_codigo_diferentes_do_publicado']}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "referencias_gee"))
