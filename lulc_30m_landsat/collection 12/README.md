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
  landsat.py        coleções Landsat 4–9 (C2): bandas, máscara de nuvem, escala
  indices.py        índices espectrais e mistura espectral (porte de index_lib.js)
  mosaic.py         mosaico anual de 42 bandas; fonte "on_the_fly" ou "asset"
  tasks.py          acompanhamento de tarefas por conta
notebooks/          um notebook por etapa, rodável localmente (VS Code) ou no Colab
  01_mosaico.ipynb
verificacao/        scripts JS para conferir o porte contra a Col 11 no Code Editor
```

As saídas dos notebooks são removidas automaticamente nos commits (`nbstripout`),
para não publicar caminhos, mensagens de erro ou dados de conta.

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

Abra o notebook da etapa no Colab (direto do GitHub, branch `col12`). O primeiro bloco instala o
pacote; depois é só entrar com a sua conta do Earth Engine e informar a fatia que lhe cabe.
