# Coleção 11 — scripts exatamente como rodaram (snapshot de produção)

Esta pasta guarda **as versões exatas** dos scripts do Code Editor do Google Earth Engine que
geraram a Coleção 11 de Áreas Urbanizadas, para que o método possa ser auditado. A pasta
[`../codes`](../codes) traz a versão documentada e comentada desses scripts. Ela foi preparada para
publicação, e em alguns pontos difere do que rodou (veja abaixo).

## Por que existe

Os scripts da Col 11 usam `require(...)` para módulos que ficavam em repositórios pessoais do Code
Editor (`users/edimilsonrodriguessantos/mapbiomas`, `users/mayhirye/...`), que o público não acessa.
Aqui cada módulo aparece no caminho do seu `require`. Exemplo:

```
require('users/edimilsonrodriguessantos/mapbiomas:Col11/results/batchResults.js')
  →  04_pos_processamento/users/edimilsonrodriguessantos/mapbiomas/Col11/results/batchResults.js
```

## Como as versões foram identificadas

1. Os repositórios de scripts do Code Editor são repositórios git
   (`earthengine.googlesource.com`). Eles foram clonados com todo o histórico.
2. Cada etapa foi **datada pelos assets que gerou no Earth Engine**, usando o horário de gravação
   dos assets.
3. Para cada arquivo de cada etapa, vale **o último commit antes desse horário**.
4. O resultado está em [`MANIFEST.csv`](MANIFEST.csv): require, commit, data, sha256 e quantas linhas
   de código (sem comentários) diferem do arquivo correspondente em `../codes`.
5. O snapshot é gerado por [`gerar_snapshot.py`](gerar_snapshot.py), que pode ser rodado de novo
   para conferência.

## Etapas e evidências

| Etapa | Asset que data a etapa | Horário de referência (UTC) |
|---|---|---|
| `00_camadas_referencia` | `Mask_Spatial_v9` (gerado em 2025-05-26, na Col 10) | cópia pública dos scripts, 2025-07-14 |
| `01_amostras` | `col11/samples/stable_samples_by_range_merged_v1` | 2026-05-15 19:39 |
| `02_classificacao` | 20.864 imagens de probabilidade em 16 coleções (2026-05-15 a 05-26) | 2026-05-16 13:30 |
| `03_limiares` | `col11/thresholdMedianByCartaImg` | 2026-05-27 04:30 |
| `04_pos_processamento` | `URBAN/classification_sf`, versão `C11_v6_SF`, 522 cartas (2026-06-02 a 06-05) | 2026-06-02 14:12 |
| `05_vegetacao_intraurbana` | `URBAN/vegintraurb/prob_intraurb_v1` | 2026-07-25 21:45 |

Na classificação, a versão de produção de `classification_batch_v3.js` foi salva em 2026-05-16 13:29.
Os commits seguintes, durante as rodadas, só trocam a lista de anos (`years`) e, num reprocessamento
de 2026-05-25, a lista de cartas. São parâmetros de cada lote, não mudanças de método.

## Diferenças entre `../codes` e o que rodou

| Arquivo em `../codes` | O que rodou | Diferença |
|---|---|---|
| `index_lib.js`, `renameBands.js`, `preProcessing_lib.js`, `class_lib.js`, `mosaic_production.js`, `posProcessingFilter.js` | ver MANIFEST | **nenhuma** no código |
| `temporalStabByRegion.js` | `Col11/filters/batchFilters.js` | mesmo código. Foi publicado com outro nome, mas é o módulo que o pós-processamento chama |
| `classification_batch.js` | `Col11/classification/classification_batch_v3.js` | mesmo método. A lista `cartasParaClassificacao` (522 cartas) existia em `mb_batch/listsAndDicts.js` na produção e foi removida da versão publicada |
| `mb_batch/listsAndDicts.js` | idem | a versão publicada é um recorte: faltam as listas usadas na produção |
| `mb_batch/collections.js` | idem (duas versões: amostras e pós-processamento) | a versão publicada omite funções que não são chamadas |
| `batchResults.js` | `Col11/results/batchResults.js` | **a versão publicada é a de julho (vegetação intraurbana)**. No pós-processamento de junho, `getImgAllProbCol11`, usada nas regras de água, vegetação e outros do pré-filtro, lia a coleção **filtrada**: sem as cartas sem amostras estáveis e sem as cartas do Norte. A versão publicada lê a coleção completa |
| `stableSamples.js` | `Col11/preProcessing/samplesCreation_v4.js` | mesmo método. A publicada traz também um trecho modelo para juntar as amostras exportadas |
| `meanThresholdsByGridAsImage.js` | `meanThresholdsByGridAsImage.js` (raiz do repositório, não a de `Col10/filtros`) | a de produção lê `col11/thresholdMedianByCarta` e grava `col11/thresholdMedianByCartaImg`. A publicada aponta para a Col 10 |
| `veg_urb.js` | `Col11/vegUrb/veg_urb_rev6.js` | mesmo código, só a geometria de teste |
| `buildingsAndBuffers.js`, `referenceLayers.js` | cópias públicas de `users/mayhirye/Publ` | mesmo código (só a geometria de teste). São da Col 10: a máscara espacial `Mask_Spatial_v9` foi reaproveitada na Col 11 |

## Como as amostras chegaram à classificação

1. `samplesCreation_v4.js` sorteia 250 pontos por classe em cada super carta, sobre as áreas estáveis
   das Coleções 6 a 10, em quatro janelas (`1985_to_2020`, `1993_to_2020`, `2001_to_2020`,
   `2009_to_2020`).
2. Os lotes exportados viraram as tabelas `stable_samples_by_range_v2`, `v2_1` e `v2_1_adhoc`.
3. `visSamplesByGrid_v2.js` junta as três e separa, por janela e por urbano/não urbano, **80% para
   treino** (`type = classification`) e **20% para validação** (`type = validation`), gravando
   `stable_samples_by_range_merged_v1`. É a tabela que a classificação lê.

A tabela final de amostras também está publicada como CSV em [`../dados`](../dados), com instruções para subir no Earth Engine.

## Lacunas conhecidas

- **Montagem de `stable_samples_by_range_v2`, `v2_1` e `v2_1_adhoc`:** os scripts de amostragem
  ad hoc (`samplesCreation_v4_adhoc*.js`) e a junção dos lotes em `v2` não foram datados nem
  incluídos. A tabela final (`merged_v1`) existe e é a usada.

- **Limiares da Col 11:** a tabela `col11/thresholdMedianByCarta` saiu de um notebook Python
  (ROC / índice de Youden por carta). O notebook em `../codes/accPreProcessingThreshold.ipynb` é a
  versão da Col 10 (lê e grava arquivos `_col10`). A versão usada na Col 11 não foi localizada.
- **Camadas de referência:** só existem as cópias públicas dos scripts, feitas em 2025-07-14, depois
  do asset (2025-05-26). O código coincide com o publicado, mas a versão exata usada não pôde ser datada.
- **`users/mapbiomas/modules:Palettes.js`** é um módulo público do MapBiomas, usado só para
  visualização. Não foi incluído.

## Parâmetros de produção do pós-processamento (`C11_v6_SF`)

Gravados nos metadados de cada imagem final e conferidos no script:

- ponto de quebra: `BP_PERCENTUAL_MINIMO = 0.5`, `BP_ANOS_MINIMOS = 5`
- filtro espacial: buracos com menos de 280 px preenchidos e ruído com menos de 10 px removido, com
  a máscara `Mask_Spatial_v9`
- os comentários do script ("v3b", "70%", "44 pixels") são de versões anteriores e **não**
  correspondem aos valores usados
