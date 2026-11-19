# Análise de Áreas Queimadas AQ1km

Aplicação web e interface de linha de comando para analisar áreas queimadas no território brasileiro a partir dos dados mensais **AQ1km do Programa Queimadas (INPE)** e dos limites municipais do **IBGE**.

O sistema cruza espacialmente as cicatrizes de fogo com os municípios de uma unidade federativa, calcula a área intersectada em quilômetros quadrados e apresenta um ranking e um mapa interativo.

## Funcionalidades

- Consulta mensal dos dados publicados pelo INPE.
- Seleção de estado e mês na aplicação web.
- Cruzamento geoespacial entre polígonos AQ1km e limites municipais.
- Cálculo da área queimada por município em km².
- Ranking dos municípios mais afetados.
- Mapa interativo com camadas e informações ao passar o cursor.
- Exportação dos resultados em formato CSV.
- Execução por linha de comando para análise de arquivos locais.

## Tecnologias

- Python 3.10 ou superior
- Flask
- GeoPandas
- Pandas
- Folium
- Requests
- INPE — Programa Queimadas, coleção AQ1km
- IBGE — API de malhas territoriais e localidades

## Estrutura do projeto

```text
.
├── analise_queimadas.py  # Funções geoespaciais e interface CLI
├── webapp.py             # Aplicação Flask e interface web
├── requirements.txt      # Dependências Python
├── .gitignore            # Arquivos locais e gerados ignorados pelo Git
└── README.md             # Documentação do projeto
```

## Instalação

No Windows, abra o terminal na pasta do projeto e execute:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Executar a aplicação web

```powershell
python webapp.py
```

Acesse `http://127.0.0.1:5001` no navegador.

A aplicação consulta automaticamente os arquivos mensais disponíveis no servidor do INPE. Para cada consulta, os polígonos AQ1km são cruzados com os municípios da unidade federativa selecionada.

## Executar pela linha de comando

O script aceita Shapefile, GeoPackage ou GeoJSON como entrada:

```powershell
python analise_queimadas.py `
  --queimadas caminho\arquivo_queimadas.shp `
  --municipios caminho\municipios.gpkg `
  --estado MT `
  --mes 8 `
  --ano 2025 `
  --saida resultado_mato_grosso
```

Serão gerados:

- `resultado_mato_grosso.csv` — ranking da área queimada por município.
- `resultado_mato_grosso.html` — mapa interativo.

### Argumentos disponíveis

| Argumento | Obrigatório | Descrição |
|---|---:|---|
| `--queimadas` | Sim | Arquivo vetorial contendo os polígonos AQ1km |
| `--municipios` | Sim | Arquivo vetorial contendo os municípios |
| `--estado` | Sim | Sigla da UF, por exemplo `MT` |
| `--mes` | Sim | Mês de análise, de `1` a `12` |
| `--ano` | Não | Ano de análise; usa o ano atual por padrão |
| `--campo-data` | Não | Campo da data no arquivo de queimadas |
| `--campo-uf` | Não | Campo da UF nos municípios; padrão: `SIGLA_UF` |
| `--campo-municipio` | Não | Campo do município; padrão: `NM_MUN` |
| `--saida` | Não | Prefixo dos arquivos gerados |

## Metodologia

1. Os polígonos de queimadas são filtrados pelo mês e ano selecionados.
2. Os dados são reprojetados para o sistema `EPSG:6933`, adequado ao cálculo de áreas em escala regional.
3. Os limites municipais são convertidos para o mesmo sistema.
4. As geometrias são intersectadas e a área de cada intersecção é somada por município.
5. O mapa final é apresentado em `EPSG:4326` (WGS84), compatível com visualização web.

Os municípios que não apresentam intersecção recebem área igual a zero.

## Fontes de dados

- **INPE — Programa Queimadas:** [dados abertos de área queimada](https://terrabrasilis.dpi.inpe.br/queimadas/portal/pages/secao_downloads/dados-abertos/)
- **IBGE — Malhas territoriais:** [API de malhas](https://servicodados.ibge.gov.br/api/v3/malhas/)
- **IBGE — Localidades:** [API de municípios](https://servicodados.ibge.gov.br/api/v1/localidades/)

## Observações

- A disponibilidade dos dados depende da publicação dos arquivos pelo INPE.
- Cicatrizes AQ1km representam polígonos de área queimada derivados de sensores e podem incluir limites de detecção ou registros de nuvens.
- Os resultados devem ser usados como apoio à análise ambiental e não substituem validação de campo ou relatórios oficiais.
- Resultados recentes podem não estar disponíveis imediatamente após o período de observação.

## Licença

Enzo Suzuki

Cauã Isaque
