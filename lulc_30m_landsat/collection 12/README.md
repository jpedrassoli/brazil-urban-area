# Coleção 12 — Áreas Urbanizadas (Landsat 30 m)

Migração para Python do pipeline da Coleção 11, que rodava em JavaScript no Code Editor do Google
Earth Engine. **Ponto de partida:** as versões exatas de produção da Col 11, auditadas e publicadas em
[`collection 11/codes_producao`](../collection%2011/codes_producao). Cada módulo Python cita o arquivo
e o commit de produção que porta.

> **Em desenvolvimento** na branch `col12`. Os módulos são portados etapa por etapa e
> conferidos contra os resultados da Coleção 11 antes de qualquer otimização.

## Estrutura

```
config/col12.yaml   configuração central (anos, projeto, destino dos assets, grades, mosaico)
mb_urban/
  config.py         leitura da configuração e montagem de caminhos de asset
  auth.py           login e inicialização do Earth Engine
  grids.py          cartas 1:250.000, super cartas (vizinhança) e divisão em lotes
  landsat.py        coleções Landsat 4–9 (C2): bandas, máscara de nuvem, escala
  indices.py        índices espectrais e mistura espectral (porte de index_lib.js)
  mosaic.py         mosaico anual de 42 bandas; fonte "on_the_fly" ou "asset"
  samples.py        amostras estáveis entre coleções do MapBiomas, treino/validação
  classify.py       Random Forest por carta e ano: probabilidade de 4 classes
  tasks.py          fila de exportação e acompanhamento de tarefas
  col11.py          acesso aos resultados da Col 11, para comparação
notebooks/          um notebook por etapa, rodável localmente (VS Code) ou no Colab
  01_mosaico.ipynb
  02_amostras.ipynb
  03_classificacao.ipynb
verificacao/        scripts JS para conferir o porte contra a versão de produção da Col 11 no Code Editor
```

As saídas dos notebooks são removidas automaticamente nos commits (`nbstripout`),
para não publicar caminhos, mensagens de erro ou dados de conta.

## Como rodar com a sua conta

Qualquer pessoa com uma conta do Google Earth Engine pode rodar as etapas, no Colab ou no próprio
computador.

### Antes de começar

- **Conta do Earth Engine** ligada a um **projeto do Google Cloud** registrado para uso do Earth Engine.
- **Permissão de escrita** na pasta de assets onde os resultados serão gravados (campo `destinations`
  da configuração). Para testes, use uma pasta sua.

### Opção 1 — Colab (sem instalar nada)

1. Abra o notebook da etapa (`notebooks/`) no Colab: no GitHub, abra o arquivo e troque
   `github.com` por `githubtocolab.com` na barra de endereço.
2. Rode o primeiro bloco: ele baixa o código e instala o pacote.
3. Rode o bloco de conta: abre o login do Google para você autorizar a sua conta do Earth Engine.
4. Ajuste os parâmetros do notebook (carta, ano) e siga os blocos em ordem.

### Opção 2 — no seu computador

```bash
git clone -b col12 https://github.com/jpedrassoli/brazil-urban-area.git
cd brazil-urban-area
pip install -e "lulc_30m_landsat/collection 12"
earthengine authenticate                      # login padrão do Earth Engine
python -m mb_urban.auth check default         # confere projeto e pasta de destino
```

Depois abra os notebooks no VS Code ou no Jupyter e use a conta `default`.

### Sua própria configuração

O arquivo `config/col12.yaml` traz os valores do projeto. Para usar outro projeto do Cloud ou outra
pasta de destino sem alterar o arquivo versionado, copie-o, edite a cópia e aponte para ela:

```bash
# Linux/macOS
export MB_URBAN_CONFIG=/caminho/para/minha_config.yaml
# Windows (PowerShell)
$env:MB_URBAN_CONFIG = "C:\caminho\para\minha_config.yaml"
```

Campos que normalmente mudam: `cloud_project` e `destinations`.

### Teste → produção

O destino dos assets fica em `config/col12.yaml`:

```yaml
destination: teste      # trocar para "producao"
```
