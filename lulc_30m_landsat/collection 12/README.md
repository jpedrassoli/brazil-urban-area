# Coleção 12 — Áreas Urbanizadas (Landsat 30 m)

Migração para Python do pipeline da [Coleção 11](../collection%2011/codes), que rodava em JavaScript
no Code Editor do Google Earth Engine.

> **Em desenvolvimento** na branch `col12`. Os módulos são portados etapa por etapa e
> conferidos contra os resultados da Coleção 11 antes de qualquer otimização.

## Estrutura

```
config/col12.yaml   configuração central (anos, contas, destino dos assets, grades, mosaico)
mb_urban/
  config.py         leitura da configuração e montagem de caminhos de asset
  auth.py           login e inicialização em várias contas do Earth Engine
  grids.py          cartas 1:250.000, super cartas (vizinhança) e fatias por conta
notebooks/
  colab_launcher.ipynb   para a equipe rodar uma fatia do processamento na própria conta
```

## Uso local

```bash
pip install -e "lulc_30m_landsat/collection 12"
python -m mb_urban.auth login conta1     # uma vez por conta
python -m mb_urban.auth check conta1
```

## Teste → produção

O destino dos assets fica em `config/col12.yaml`:

```yaml
destination: teste      # trocar para "producao"
```

## Rodar pela equipe (Colab)

Abra `notebooks/colab_launcher.ipynb` no Colab, entre com a sua conta do Earth Engine e informe
a etapa e a fatia que lhe cabem.
