# Resultados das verificações contra a Coleção 11

## Mosaico anual (`mb_urban.mosaic`, codificação `col11`)

- **Data:** 2026-11-14
- **Referência:** `mosaic_production.js` de produção da Col 11 (commit `bf9c98b0`), rodado no Code
  Editor com [`mosaico_col11_ponto.js`](mosaico_col11_ponto.js)
- **Caso:** carta `SF-23-Y-C`, ano 2020, ponto (-46.633, -23.55), super carta como contexto
- **Resultado:** 42 bandas nas duas versões. As 24 bandas conferidas (AWEIsh a MNDWI, em ordem
  alfabética) deram **diferença zero**. As 18 restantes não foram transcritas do Console.

## Classificação (`mb_urban.classify`, codificação `col11`, formato por ano)

- **Data:** 2026-11-14
- **Referência:** probabilidades exportadas na produção da Col 11 (`classification_batch_v3.js`,
  commit `0c0239bf`), lidas com `mb_urban.col11.probability`
- **Caso:** carta `SF-23-Y-C`, anos 1985, 2005 e 2020, tabela de amostras de produção da Col 11
- **Resultado:** **100% dos pixels idênticos** nas 4 bandas de probabilidade, nos três anos
  (comparação na resolução de 30 m, sobre toda a carta)
- **Tempo:** 12 a 16 minutos por tarefa anual, rodando 4 tarefas simultâneas na mesma conta

## Pré-filtro + pós-processamento (`mb_urban.prefilter` e `mb_urban.postprocess`)

- **Data:** 2026-11-14
- **Referência:** mapa final oficial da Col 11, `URBAN/classification_sf/SF-23-Y-C_v6` (versão `C11_v6_SF`)
- **Caso:** carta `SF-23-Y-C`, 41 anos, refeito a partir das probabilidades da Col 11
  (`postprocess.probability_source: col11`)
- **Resultado:** 4 anos idênticos e 37 com diferença de **1 a 13 pixels** em 20,6 milhões
  (no máximo 0,0005% dos ~3 milhões de pixels urbanos). As diferenças são manchas pequenas, com
  tamanho perto dos limites do filtro espacial (ruído de 10 px), no interior da carta. Isso é
  compatível com o comportamento conhecido de `connectedPixelCount`, que conta componentes por
  bloco de processamento e pode variar perto desses limites conforme a divisão em blocos de cada
  exportação. Não é diferença de método.
- **Tempo:** 14 minutos, 33 EECU-hora, para a carta inteira e os 41 anos.

## Limiar por carta: porte × tabela da Col 11 (2026-11-15)

`mb_urban.thresholds` rodado com as probabilidades da Col 11 e os pontos de validação da tabela de amostras
da Col 11 (janela do ano), nas 12 cartas de teste, 41 anos. Comparado com `col11/thresholdMedianByCarta`
(cópia em `dados/col11_limiares_por_carta.csv`). `cutPercentile` é a banda `percentil` usada pelo pré-filtro.

| Carta | cutPercentile porte | cutPercentile Col 11 | Youden porte | Youden Col 11 |
|---|---|---|---|---|
| SF-23-Y-C | 62,5 | 62,5 | 27 | 28 |
| SF-23-Z-B | 63,6 | 62,7 | 24 | 29 |
| SE-23-Z-C | 56,2 | 53,9 | 26 | 30 |
| SD-23-Y-C | 57,0 | 44,8 | 37 | 29 |
| SH-22-Y-B | 69,6 | 65,8 | 28 | 38 |
| SC-25-V-A | 46,2 | 44,9 | 26 | 29 |
| SC-24-V-C | 51,1 | 48,8 | 26 | 38 |
| SA-20-Z-D | 80,8 | 57,8 | 64 | 34 |
| SA-22-X-D | 60,8 | 53,6 | 24 | 31 |
| SC-21-Z-C | 59,8 | 64,8 | 35 | 33 |
| SE-21-Y-D | 32,8 | 33,6 | 18 | 23 |
| NA-22-V-B | sem dados | 51,9 (mediana nacional) | sem dados | 30 |

Leitura: a fórmula reproduz a Col 11 onde os conjuntos de validação se parecem (São Paulo idêntico; Recife,
Corumbá, Rio e Petrolina a 1–3 pontos). Diverge onde a validação da Col 11 foi outra: Brasília (sem amostras
estáveis na Col 11) e Manaus (na Col 11 a probabilidade da carta veio da Col 10). Com a tabela de amostras
da Col 11 há em média 63 pontos urbanos por carta-ano (a Col 10 usava 220). Conclusão: método recuperado; os
pontos de validação exatos da Col 11 não são conhecidos. Para a Col 12, os limiares serão calculados com a
validação da tabela nova.
