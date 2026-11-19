import io
import os
import re
import tempfile
import uuid
import zipfile
from functools import lru_cache
from pathlib import Path, PurePosixPath

import geopandas as gpd
import pandas as pd
import requests
from flask import Flask, Response, abort, render_template_string, request, send_file

from analise_queimadas import analisar_camadas


app = Flask(__name__)
INPE_SHP_URL = (
    "https://dataserver-coids.inpe.br/queimadas/queimadas/"
    "area_queimada/colecao2/shp/"
)
IBGE_MALHAS_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/estados"
IBGE_MUNICIPIOS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
TIMEOUT = (10, 90)
MAX_ARCHIVE_SIZE = 100_000_000
UFS = [
    ("AC", "Acre"), ("AL", "Alagoas"), ("AP", "Amapá"), ("AM", "Amazonas"),
    ("BA", "Bahia"), ("CE", "Ceará"), ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"), ("GO", "Goiás"), ("MA", "Maranhão"),
    ("MT", "Mato Grosso"), ("MS", "Mato Grosso do Sul"), ("MG", "Minas Gerais"),
    ("PA", "Pará"), ("PB", "Paraíba"), ("PR", "Paraná"), ("PE", "Pernambuco"),
    ("PI", "Piauí"), ("RJ", "Rio de Janeiro"), ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"), ("RO", "Rondônia"), ("RR", "Roraima"),
    ("SC", "Santa Catarina"), ("SP", "São Paulo"), ("SE", "Sergipe"),
    ("TO", "Tocantins"),
]
MESES = [
    (1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"),
    (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"),
    (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro"),
]
resultados = {}

PAGE = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Queimadas AQ1km — análise municipal</title>
  <style>
    :root { color-scheme: light; font-family: Inter, "Segoe UI", Arial, sans-serif; color: #172b2b; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f2f5f2; }
    header { background: #173c35; color: white; padding: 22px max(24px, calc((100% - 1120px)/2)); }
    header small { color: #c8ddd3; letter-spacing: .12em; text-transform: uppercase; }
    header h1 { margin: 7px 0 0; font-size: clamp(24px, 4vw, 36px); }
    main { max-width: 1120px; margin: 28px auto; padding: 0 20px 40px; }
    .intro, .panel, .result { background: white; border: 1px solid #dce5df; border-radius: 12px; padding: 22px; }
    .intro { margin-bottom: 18px; }
    .intro p { margin: 8px 0 0; line-height: 1.55; color: #53645e; }
    form { display: grid; grid-template-columns: minmax(210px, 1fr) minmax(210px, 1fr) auto; gap: 14px; align-items: end; }
    label { display: grid; gap: 7px; font-size: 14px; font-weight: 650; }
    select, button { min-height: 44px; padding: 10px 12px; border: 1px solid #bdcbc3; border-radius: 7px; font: inherit; background: white; }
    button { border: 0; background: #17684f; color: white; padding: 10px 20px; font-weight: 700; cursor: pointer; }
    button:hover { background: #10513d; }
    button:disabled { opacity: .6; cursor: wait; }
    .hint { margin: 14px 0 0; color: #63736d; font-size: 13px; }
    .error { margin: 16px 0 0; padding: 13px 15px; border-radius: 7px; color: #8d241d; background: #fff0ed; }
    .result { margin-top: 20px; }
    .winner { padding: 17px; background: #edf6ef; border-left: 4px solid #258058; border-radius: 6px; }
    .winner strong { display: block; color: #4f6258; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; }
    .winner .name { font-size: 25px; font-weight: 750; margin-top: 5px; }
    .winner .area { font-size: 17px; margin-top: 4px; }
    .result-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; margin: 20px 0 12px; }
    .result-head h2 { margin: 0; font-size: 19px; }
    .download { color: #17684f; font-weight: 650; }
    iframe { display: block; width: 100%; height: 610px; border: 1px solid #d1dcd5; border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; margin-top: 18px; }
    th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid #e8eeea; }
    th { color: #56665e; font-size: 13px; }
    td:last-child, th:last-child { text-align: right; }
    footer { margin-top: 18px; color: #66776f; font-size: 12px; }
    footer a { color: #17684f; }
    @media (max-width: 700px) { form { grid-template-columns: 1fr; } main { margin-top: 16px; } iframe { height: 480px; } }
  </style>
</head>
<body>
<header>
  <small>Monitoramento de queimadas · INPE</small>
  <h1>Área queimada por município</h1>
</header>
<main>
  <section class="intro">
    <strong>Descubra onde a área queimada foi maior.</strong>
    <p>Selecione um estado e um mês com dados publicados. O sistema baixa o AQ1km do INPE,
       cruza os polígonos com os limites municipais do IBGE e calcula a área em km².</p>
  </section>
  <section class="panel">
    <form method="post" id="analise">
      <label>Estado
        <select name="estado" required>
          {% for uf, nome in ufs %}
            <option value="{{ uf }}" {% if uf == estado %}selected{% endif %}>{{ nome }} ({{ uf }})</option>
          {% endfor %}
        </select>
      </label>
      <label>Mês de {{ ano }}
        <select name="mes" required {% if not meses_disponiveis %}disabled{% endif %}>
          {% for numero, nome in meses %}
            {% if numero in meses_disponiveis %}
              <option value="{{ numero }}" {% if numero == mes %}selected{% endif %}>{{ nome }}</option>
            {% endif %}
          {% endfor %}
        </select>
      </label>
      <button type="submit" {% if not meses_disponiveis %}disabled{% endif %}>Analisar e gerar mapa</button>
    </form>
    {% if meses_disponiveis %}
      <p class="hint">Dados mensais disponíveis no INPE para {{ ano }} até {{ nome_ultimo_mes }}.</p>
    {% endif %}
    {% if erro %}<p class="error" role="alert">{{ erro }}</p>{% endif %}
  </section>
  {% if tem_resultado %}
    <section class="result">
      <div class="winner">
        <strong>Município com maior área queimada · {{ nome_estado }} · {{ nome_mes }}/{{ ano }}</strong>
        <div class="name">{{ resultado.municipio }}</div>
        <div class="area">{{ "%.2f"|format(resultado.area_km2) }} km² queimados</div>
      </div>
      <div class="result-head">
        <h2>Mapa interativo</h2>
        <a class="download" href="{{ url_for('baixar_csv', token=token) }}">Baixar ranking completo (CSV)</a>
      </div>
      <iframe title="Mapa interativo das áreas queimadas" src="{{ url_for('mapa', token=token) }}"></iframe>
      <p class="hint">Como ler: as cicatrizes vermelhas são os polígonos AQ1km do INPE; o preenchimento amarelo a laranja compara a área queimada total de cada município. Passe o mouse para ver os valores e use “Camadas” para ligar ou desligar cada visualização.</p>
      <h2>Municípios com maior área queimada</h2>
      <table>
        <thead><tr><th>Posição</th><th>Município</th><th>Área queimada (km²)</th></tr></thead>
        <tbody>
        {% for linha in ranking %}
          <tr><td>{{ loop.index }}</td><td>{{ linha.municipio }}</td><td>{{ "%.2f"|format(linha.area_km2) }}</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </section>
  {% endif %}
  <footer>
    Fontes: <a href="https://terrabrasilis.dpi.inpe.br/queimadas/portal/pages/secao_downloads/dados-abertos/">Programa Queimadas/INPE — AQ1km mensal</a>
    · <a href="https://servicodados.ibge.gov.br/api/v3/malhas/">IBGE — Malhas territoriais</a>.
    A disponibilidade depende da publicação dos arquivos pelo INPE.
  </footer>
</main>
<script>
  document.getElementById("analise").addEventListener("submit", function () {
    const button = this.querySelector("button");
    button.disabled = true;
    button.textContent = "Baixando dados e calculando…";
  });
</script>
</body>
</html>
"""


def obter_arquivos_disponiveis(ano):
    resposta = requests.get(INPE_SHP_URL, timeout=TIMEOUT)
    resposta.raise_for_status()
    pattern = rf'href="({ano}_(\d{{2}})_01_aq1km_V6\.zip)"'
    arquivos = {}
    for arquivo, mes in re.findall(pattern, resposta.text, flags=re.IGNORECASE):
        arquivos[int(mes)] = arquivo
    return sorted(arquivos.items())


@lru_cache(maxsize=2)
def carregar_queimadas(nome_arquivo):
    resposta = requests.get(INPE_SHP_URL + nome_arquivo, timeout=TIMEOUT, stream=True)
    resposta.raise_for_status()
    blocos = []
    tamanho = 0
    for bloco in resposta.iter_content(chunk_size=1024 * 1024):
        tamanho += len(bloco)
        if tamanho > MAX_ARCHIVE_SIZE:
            raise ValueError("O arquivo mensal do INPE excedeu o limite de tamanho esperado.")
        blocos.append(bloco)
    conteudo = b"".join(blocos)

    try:
        arquivo_zip = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as error:
        raise ValueError("O arquivo mensal baixado do INPE não é um ZIP válido.") from error

    with arquivo_zip, tempfile.TemporaryDirectory() as pasta:
        shapefiles = [
            item for item in arquivo_zip.namelist()
            if PurePosixPath(item).suffix.lower() == ".shp"
        ]
        if len(shapefiles) != 1:
            raise ValueError("O ZIP mensal do INPE não contém exatamente um Shapefile.")
        shp = PurePosixPath(shapefiles[0])
        prefixo = shp.stem.casefold()
        extensoes = {".shp", ".shx", ".dbf", ".prj", ".cpg"}
        membros = {}
        for item in arquivo_zip.namelist():
            caminho = PurePosixPath(item)
            if caminho.stem.casefold() == prefixo and caminho.suffix.lower() in extensoes:
                membros[caminho.suffix.lower()] = item
        if not {".shp", ".shx", ".dbf", ".prj"}.issubset(membros):
            raise ValueError("O Shapefile mensal do INPE está incompleto.")
        caminhos = {}
        for extensao, membro in membros.items():
            destino = Path(pasta) / f"dados{extensao}"
            destino.write_bytes(arquivo_zip.read(membro))
            caminhos[extensao] = destino
        return gpd.read_file(caminhos[".shp"])


@lru_cache(maxsize=27)
def carregar_municipios(uf):
    url_malhas = (
        f"{IBGE_MALHAS_URL}/{uf}"
        "?formato=application/vnd.geo+json&intrarregiao=municipio"
    )
    resposta_malhas = requests.get(url_malhas, timeout=TIMEOUT)
    resposta_malhas.raise_for_status()
    malhas = gpd.GeoDataFrame.from_features(
        resposta_malhas.json()["features"], crs="EPSG:4326"
    )
    if "codarea" not in malhas.columns:
        raise ValueError("A resposta do IBGE não trouxe os códigos municipais esperados.")

    resposta_nomes = requests.get(
        f"{IBGE_MUNICIPIOS_URL}/{uf}/municipios", timeout=TIMEOUT
    )
    resposta_nomes.raise_for_status()
    nomes = {
        str(municipio["id"]): municipio["nome"]
        for municipio in resposta_nomes.json()
    }
    malhas["municipio"] = malhas["codarea"].astype(str).map(nomes)
    if malhas["municipio"].isna().any():
        raise ValueError("Não foi possível associar nomes a todos os municípios do IBGE.")
    return malhas


def renderizar(erro=None, estado="MT", mes=None, meses_disponiveis=(),
               resultado=None, ranking=(), token=None, ano=None):
    ano = ano or pd.Timestamp.now().year
    meses_disponiveis = dict(meses_disponiveis)
    if mes not in meses_disponiveis:
        mes = max(meses_disponiveis, default=None)
    nome_meses = dict(MESES)
    nomes_ufs = dict(UFS)
    return render_template_string(
        PAGE,
        erro=erro,
        ufs=UFS,
        estado=estado,
        ano=ano,
        mes=mes,
        meses=MESES,
        meses_disponiveis=meses_disponiveis,
        nome_ultimo_mes=nome_meses.get(max(meses_disponiveis, default=None), ""),
        resultado=resultado,
        tem_resultado=resultado is not None,
        ranking=ranking,
        token=token,
        nome_estado=nomes_ufs.get(estado, estado),
        nome_mes=nome_meses.get(mes, ""),
    )


@app.route("/", methods=["GET", "POST"])
def inicio():
    ano = pd.Timestamp.now().year
    uf_valida = {uf for uf, _ in UFS}
    estado = request.form.get("estado", "MT").upper()
    erro = None
    try:
        meses_disponiveis = obter_arquivos_disponiveis(ano)
    except requests.RequestException as error:
        app.logger.exception("Falha ao consultar os arquivos AQ1km do INPE")
        meses_disponiveis = []
        erro = f"Não foi possível consultar os dados do INPE agora: {error}"

    resultado = None
    ranking = ()
    token = None
    mes = None
    if request.method == "POST" and meses_disponiveis:
        try:
            if estado not in uf_valida:
                raise ValueError("Selecione uma unidade federativa válida.")
            mes = int(request.form["mes"])
            arquivos_por_mes = dict(meses_disponiveis)
            if mes not in arquivos_por_mes:
                raise ValueError("Esse mês ainda não tem arquivo AQ1km publicado pelo INPE.")
            queimadas = carregar_queimadas(arquivos_por_mes[mes])
            municipios = carregar_municipios(estado).copy()
            tabela, mapa, lider = analisar_camadas(queimadas, municipios)
            token = uuid.uuid4().hex
            resultados[token] = (
                tabela.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                mapa.get_root().render(),
            )
            while len(resultados) > 8:
                resultados.pop(next(iter(resultados)))
            resultado = lider
            ranking = tabela.head(10).to_dict("records")
        except (KeyError, ValueError, requests.RequestException, zipfile.BadZipFile) as error:
            app.logger.exception("Não foi possível processar a análise AQ1km")
            erro = f"Não foi possível concluir a análise: {error}"
        except Exception as error:
            app.logger.exception("Falha inesperada na análise geoespacial")
            erro = f"Erro inesperado ao processar os dados: {error}"

    return renderizar(
        erro=erro,
        estado=estado,
        mes=mes,
        meses_disponiveis=meses_disponiveis,
        resultado=resultado,
        ranking=ranking,
        token=token,
        ano=ano,
    )


@app.get("/mapa/<token>")
def mapa(token):
    item = resultados.get(token)
    if item is None:
        abort(404)
    return Response(item[1], mimetype="text/html")


@app.get("/baixar/<token>")
def baixar_csv(token):
    item = resultados.get(token)
    if item is None:
        abort(404)
    return send_file(
        io.BytesIO(item[0]),
        mimetype="text/csv",
        as_attachment=True,
        download_name="ranking_areas_queimadas.csv",
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5001")), debug=False)
