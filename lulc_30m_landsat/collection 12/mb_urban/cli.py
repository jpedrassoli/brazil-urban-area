"""Linha de comando do pacote: `python -m mb_urban <comando>`.

  estado                       resumo local (git, fila, falhas ainda abertas); grava logs/estado.json. Não usa o Earth Engine.
  preflight [--carta C ...]    confere amostras de treino e limiar antes de classificar (lê o Earth Engine).
  classificar --carta C ...    envia as probabilidades [--anos A B] [--rodada R] [--fallback] [--conta N] [--sem-esperar]
  pos --carta C ...            pós-processamento [--rodada R] [--limiar-reserva youden|P] [--conta N] [--sem-esperar]

`--rodada R` grava em pastas próprias (`probabilidades__R`, `mapa_final__R`), sem tocar nas outras rodadas.
Sem `--rodada` valem as pastas da configuração (a rodada "base")."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import config


def _cartas(args, cfg) -> list[str]:
    from . import grids
    return args.carta or grids.cartas_in_scope(cfg)


def cmd_estado(args, cfg) -> dict:
    """Resumo gerado dos arquivos locais: substitui a leitura manual de vários logs."""
    log = config.PACKAGE_ROOT / "logs"
    est: dict = {"codigo": config.code_version(), "destino": cfg.get("destination"), "contas": {}, "falhas_abertas": []}
    for f in sorted(log.glob("registro_conta*.json")):
        if "backup" in f.name:
            continue
        reg = json.loads(f.read_text(encoding="utf-8"))
        cont: dict = {}
        for r in reg.values():
            cont[r["estado"]] = cont.get(r["estado"], 0) + 1
        est["contas"][f.stem.replace("registro_", "")] = cont
    concluidas = set()
    for f in log.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("estado") == "COMPLETED":
                concluidas.add(ev.get("tarefa"))
    falhas = log / "falhas.jsonl"
    if falhas.exists():
        for line in falhas.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("acao") == "precisa de correção" and ev.get("tarefa") not in concluidas:
                est["falhas_abertas"].append({k: ev.get(k) for k in ("quando", "tarefa", "tipo", "erro")})
    try:
        dirty = subprocess.run(["git", "-C", str(config.PACKAGE_ROOT), "status", "--short"], capture_output=True,
                               text=True).stdout.strip().splitlines()
        est["alteracoes_nao_salvas"] = len(dirty)
    except OSError:
        pass
    (log / "estado.json").write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding="utf-8")
    return est


def cmd_preflight(args, cfg):
    from . import auth, preflight
    auth.init(args.conta, cfg)
    return preflight.check(_cartas(args, cfg), cfg)


def cmd_classificar(args, cfg):
    from . import auth, classify, tasks
    cfg = config.apply_run(cfg, args.rodada)
    if args.fallback:
        cfg["classification"]["sample_fallback"] = {"enabled": True}
    auth.init(args.conta, cfg)
    anos = list(range(args.anos[0], args.anos[1] + 1)) if args.anos else None
    specs = [s for c in _cartas(args, cfg) for s in classify.export_tasks(c, anos, cfg=cfg)]
    return tasks.run_queue(specs, account=args.conta, wait=not args.sem_esperar, poll_seconds=300,
                           log_name=f"cli_classificar_{args.conta}", cfg=cfg)


def cmd_pos(args, cfg):
    import ee
    from . import auth, grids, postprocess, tasks, thresholds
    cfg = config.apply_run(cfg, args.rodada)
    auth.init(args.conta, cfg)
    if args.limiar_reserva:
        # Limiar de reserva para cartas sem pontos urbanos: "youden" = mediana nacional do limiar de Youden das
        # cartas com dados; ou um valor fixo. Vale para UMA carta por vez (a imagem de limiar é por carta).
        cartas = _cartas(args, cfg)
        if len(cartas) != 1:
            raise SystemExit("--limiar-reserva exige exatamente uma --carta")
        c = cartas[0]
        tabela = thresholds.col11_table()
        valor = (float(tabela.loc[tabela["n_years_available"] > 0, "threshold"].median())
                 if args.limiar_reserva == "youden" else float(args.limiar_reserva))
        img_id = config.asset_path("limiares", f"limiar_reserva_{c}_{args.rodada or 'base'}", cfg=cfg)
        reg = grids.carta_geometry(c, cfg).buffer(5000).bounds()
        img = (ee.Image.constant(valor).rename("percentil").toFloat()
               .addBands(ee.Image.constant(valor).rename("threshold").toFloat())
               .set({"carta": c, "regra": f"limiar de reserva {args.limiar_reserva}", "valor": valor}))
        spec = (f"limiar_reserva_{c}", img_id, lambda: ee.batch.Export.image.toAsset(
            image=img, description=config.task_description(f"limiar_reserva_{c}", cfg), assetId=img_id,
            region=reg, scale=30, crs="EPSG:4326", maxPixels=1e9))
        tasks.run_queue([spec], account=args.conta, wait=True, poll_seconds=60, log_name=f"cli_limiar_{args.conta}", cfg=cfg)
        cfg["postprocess"]["threshold_image"] = img_id
    return tasks.run_queue(postprocess.export_tasks(_cartas(args, cfg), cfg), account=args.conta,
                           wait=not args.sem_esperar, poll_seconds=120, log_name=f"cli_pos_{args.conta}", cfg=cfg)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m mb_urban", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("estado", "preflight", "classificar", "pos"):
        p = sub.add_parser(nome)
        p.add_argument("--carta", nargs="+")
        p.add_argument("--conta", default="default")
        if nome in ("classificar", "pos"):
            p.add_argument("--rodada")
            p.add_argument("--sem-esperar", action="store_true")
        if nome == "classificar":
            p.add_argument("--anos", nargs=2, type=int, metavar=("A", "B"))
            p.add_argument("--fallback", action="store_true")
        if nome == "pos":
            p.add_argument("--limiar-reserva", metavar="youden|P")
    a = ap.parse_args(argv)
    cfg = config.load()
    r = {"estado": cmd_estado, "preflight": cmd_preflight, "classificar": cmd_classificar, "pos": cmd_pos}[a.cmd](a, cfg)
    if r is not None:
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str) if isinstance(r, dict) else r.to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
