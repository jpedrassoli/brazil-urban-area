"""Autenticação em várias contas do Earth Engine.

Uso local (uma vez por conta):
    python -m mb_urban.auth login conta1
    python -m mb_urban.auth login conta2
    python -m mb_urban.auth check conta1

No código:
    from mb_urban import auth
    auth.init("conta1")        # ou auth.init() para o login padrão (Colab / equipe)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import ee
from google.oauth2.credentials import Credentials

from . import config


def _account(name: str, cfg: dict) -> dict:
    try:
        return cfg["accounts"][name]
    except KeyError:
        raise KeyError(f"Conta '{name}' não existe em accounts: {list(cfg['accounts'])}") from None


def _cred_file(name: str, cfg: dict) -> Path | None:
    path = _account(name, cfg).get("credentials")
    return Path(path).expanduser() if path else None


def login(name: str, cfg: dict | None = None) -> Path:
    """Abre o login do Google para a conta e guarda as credenciais num arquivo próprio."""
    cfg = cfg or config.load()
    target = _cred_file(name, cfg)
    if target is None:
        raise ValueError(f"A conta '{name}' usa o login padrão; rode apenas ee.Authenticate().")
    ee.Authenticate(force=True)
    default = Path(ee.oauth.get_credentials_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(default, target)
    return target


def init(name: str = "default", cfg: dict | None = None) -> str:
    """Inicializa o ee com a conta escolhida e o projeto do Cloud da configuração."""
    cfg = cfg or config.load()
    project = cfg["cloud_project"]
    path = _cred_file(name, cfg)
    if path is None:
        ee.Initialize(project=project)
        return name
    if not path.exists():
        raise FileNotFoundError(f"Sem credenciais para '{name}'. Rode: python -m mb_urban.auth login {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    creds = Credentials(
        None,
        refresh_token=data["refresh_token"],
        token_uri=ee.oauth.TOKEN_URI,
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
    )
    ee.Initialize(credentials=creds, project=project)
    return name


def check(name: str = "default", cfg: dict | None = None) -> dict:
    """Confere o acesso: projeto, pastas raiz de assets e o destino configurado."""
    cfg = cfg or config.load()
    init(name, cfg)
    roots = [r["id"] for r in ee.data.getAssetRoots()]
    dest = config.destination_root(cfg)
    try:
        ee.data.getAsset(dest)
        dest_ok = True
    except ee.EEException:
        dest_ok = False
    return {"account": name, "project": cfg["cloud_project"], "asset_roots": roots,
            "destination": dest, "destination_exists": dest_ok}


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "check"
    acc = args[1] if len(args) > 1 else "default"
    if cmd == "login":
        print("Credenciais salvas em", login(acc))
    elif cmd == "check":
        print(json.dumps(check(acc), indent=2, ensure_ascii=False))
    else:
        sys.exit("uso: python -m mb_urban.auth [login|check] <conta>")
