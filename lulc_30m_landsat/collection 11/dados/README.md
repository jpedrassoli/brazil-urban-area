# Dados da Coleção 11

## Amostras de treino e validação

**Arquivo:** [`amostras_col11_stable_samples_by_range_merged_v1.csv.gz`](amostras_col11_stable_samples_by_range_merged_v1.csv.gz)
(CSV compactado, 6,9 MB, 314.186 pontos)

É a tabela de amostras usada na classificação da Coleção 11 (`stable_samples_by_range_merged_v1`),
exportada do Earth Engine em 2026-11-14 para que qualquer pessoa possa reproduzir o método sem
depender do asset original. Veja como ela foi gerada em
[`../codes_producao/README.md`](../codes_producao/README.md#como-as-amostras-chegaram-à-classificação).

- sha256 do arquivo: `1bb0e75730ccc0f7775021d6287f8f79cad6ebb37e2d54a8c1eda16a0a083057`
- asset de origem: `projects/ee-ers/assets/mapbiomas/col11/samples/stable_samples_by_range_merged_v1`

### Colunas

| Coluna | Conteúdo |
|---|---|
| `id_original` | identificador do ponto (`system:index`) no asset de origem |
| `longitude`, `latitude` | coordenadas, graus decimais (WGS 84) |
| `class` | 1 urbano, 2 vegetação (florestal e campestre), 3 água, 4 agropecuária |
| `range` | janela de estabilidade: `1985_to_2020`, `1993_to_2020`, `2001_to_2020` ou `2009_to_2020` |
| `type` | `classification` (treino, 80%) ou `validation` (validação, 20%) |
| `grid_name` | carta 1:250.000 cuja super carta originou o ponto |
| `random` | valor aleatório usado na separação treino/validação |

Contagens: 251.175 de treino e 63.011 de validação. Por janela: 74.369 / 75.064 / 81.616 / 83.137.

### Como subir no seu Earth Engine

1. Descompacte o arquivo (`.csv.gz` → `.csv`).
2. No Code Editor, aba **Assets** → **NEW** → **CSV file (.csv)**.
3. Escolha o arquivo, defina o caminho do asset e, nas opções avançadas, informe
   `longitude` como coluna X e `latitude` como coluna Y.
4. Depois do upload, aponte `samples.table` em `collection 12/config/col12.yaml` para o seu asset.

As amostras são derivadas das coleções de cobertura e uso da terra do MapBiomas. Ao usar, cite o
MapBiomas.
