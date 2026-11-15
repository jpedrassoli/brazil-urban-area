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
