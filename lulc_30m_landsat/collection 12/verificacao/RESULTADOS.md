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
