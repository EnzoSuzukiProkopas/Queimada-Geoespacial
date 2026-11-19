import argparse
from datetime import date

import folium
import geopandas as gpd
import pandas as pd
from branca.colormap import LinearColormap
from branca.element import Element


DATE_COLUMNS = ("data", "date", "data_queima", "data_queimada", "dt_queimada")


def find_column(frame, requested, candidates):
    columns = {column.casefold(): column for column in frame.columns}
    if requested:
        column = columns.get(requested.casefold())
        if column is None:
            raise ValueError(
                f"Campo '{requested}' não encontrado. Campos disponíveis: "
                f"{', '.join(map(str, frame.columns))}"
            )
        return column

    for candidate in candidates:
        if candidate.casefold() in columns:
            return columns[candidate.casefold()]
    raise ValueError(
        "Não foi possível identificar o campo de data. Informe-o com --campo-data. "
        f"Campos disponíveis: {', '.join(map(str, frame.columns))}"
    )


def analisar_camadas(queimadas, municipios):
    if queimadas.crs is None or municipios.crs is None:
        raise ValueError("Os dois arquivos precisam informar seu sistema de coordenadas (CRS).")
    if "municipio" not in municipios.columns:
        raise ValueError("A camada de municípios precisa ter uma coluna 'municipio'.")
    if queimadas.empty or municipios.empty:
        raise ValueError("As camadas geográficas não podem estar vazias.")

    municipios = municipios[["municipio", municipios.geometry.name]].copy()
    queimadas = queimadas[[queimadas.geometry.name]].to_crs(municipios.crs)
    queimadas = queimadas.dissolve()
    area_crs = "EPSG:6933"
    cruzamento = gpd.overlay(
        municipios.to_crs(area_crs),
        queimadas.to_crs(area_crs),
        how="intersection",
        keep_geom_type=True,
    )
    if cruzamento.empty:
        raise ValueError("Os polígonos de queimada não intersectam os municípios selecionados.")

    cruzamento["area_km2"] = cruzamento.geometry.area / 1_000_000
    por_municipio = cruzamento.groupby("municipio")["area_km2"].sum()
    resultado = (
        municipios[["municipio"]]
        .drop_duplicates()
        .set_index("municipio")
        .join(por_municipio)
        .fillna({"area_km2": 0})
        .sort_values("area_km2", ascending=False)
        .reset_index()
    )
    lider = resultado.iloc[0]

    areas_queimadas = cruzamento[["municipio", "geometry"]].merge(
        por_municipio.rename("area_municipio_km2"),
        left_on="municipio",
        right_index=True,
    ).to_crs("EPSG:4326")
    municipios_mapa = municipios.merge(
        por_municipio.rename("area_km2"),
        left_on="municipio",
        right_index=True,
        how="left",
    )
    municipios_mapa["area_km2"] = municipios_mapa["area_km2"].fillna(0)
    municipios_mapa = municipios_mapa.to_crs("EPSG:4326")
    max_area = max(float(municipios_mapa["area_km2"].max()), 1)
    escala = LinearColormap(
        colors=["#fff7bc", "#fec44f", "#fe9929", "#ec7014", "#cc4c02"],
        vmin=0,
        vmax=max_area,
        caption="Área queimada intersectada por município (km²)",
    )

    mapa = folium.Map(tiles="OpenStreetMap")
    folium.GeoJson(
        municipios_mapa,
        name="Área queimada por município",
        show=True,
        style_function=lambda feature: {
            "color": "#58645d",
            "weight": 0.7,
            "fillColor": escala(feature["properties"]["area_km2"]),
            "fillOpacity": 0.48,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["municipio", "area_km2"],
            aliases=["Município", "Área queimada (km²)"],
            localize=True,
        ),
    ).add_to(mapa)
    folium.GeoJson(
        areas_queimadas,
        name="Cicatrizes AQ1km",
        show=True,
        style_function=lambda _: {
            "color": "#a31616",
            "weight": 1.4,
            "fillColor": "#e31a1c",
            "fillOpacity": 0.9,
        },
        highlight_function=lambda _: {
            "color": "#6d0010",
            "weight": 3,
            "fillOpacity": 1,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["municipio", "area_municipio_km2"],
            aliases=["Município", "Total no município (km²)"],
            localize=True,
        ),
    ).add_to(mapa)
    mapa.get_root().html.add_child(
        Element(
            f"""
            <div style="position:fixed;bottom:32px;left:12px;z-index:9999;
                        max-width:280px;padding:10px 12px;background:white;
                        border:1px solid #aeb8b0;border-radius:6px;
                        box-shadow:0 1px 5px #777;font:12px Arial,sans-serif">
              <strong>Legenda</strong>
              <div style="margin-top:5px"><span style="color:#e31a1c">■</span>
                Cicatrizes AQ1km (áreas queimadas)</div>
              <div style="margin-top:5px">Área queimada total por município</div>
              <div style="height:10px;margin:3px 0;background:linear-gradient(
                to right,#fff7bc,#fec44f,#fe9929,#ec7014,#cc4c02)"></div>
              <div style="display:flex;justify-content:space-between">
                <span>0 km²</span><span>{max_area:.1f} km²</span>
              </div>
              <div>Contornos: limites municipais</div>
            </div>
            """
        )
    )
    folium.LayerControl().add_to(mapa)
    bounds = municipios_mapa.total_bounds
    mapa.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    return resultado, mapa, lider


def analisar(arquivo_queimadas, arquivo_municipios, estado, mes, ano,
             campo_data=None, campo_uf="SIGLA_UF", campo_municipio="NM_MUN"):
    queimadas = gpd.read_file(arquivo_queimadas)
    municipios = gpd.read_file(arquivo_municipios)
    if queimadas.crs is None or municipios.crs is None:
        raise ValueError("Os dois arquivos precisam informar seu sistema de coordenadas (CRS).")

    data_col = find_column(queimadas, campo_data, DATE_COLUMNS)
    uf_col = find_column(municipios, campo_uf, ())
    municipio_col = find_column(municipios, campo_municipio, ())

    valores_data = queimadas[data_col]
    datas_texto = valores_data.astype("string").str.strip()
    compactas = datas_texto.str.fullmatch(r"\d{8}", na=False)
    datas = pd.Series(pd.NaT, index=queimadas.index, dtype="datetime64[ns]")
    datas.loc[compactas] = pd.to_datetime(
        datas_texto.loc[compactas], format="%Y%m%d", errors="coerce"
    )
    datas.loc[~compactas] = pd.to_datetime(
        valores_data.loc[~compactas], errors="coerce", dayfirst=True
    )
    queimadas = queimadas.loc[(datas.dt.year == ano) & (datas.dt.month == mes)].copy()
    if queimadas.empty:
        raise ValueError(f"Não há registros de área queimada para {mes:02d}/{ano}.")

    estado = estado.strip().upper()
    municipios = municipios.loc[
        municipios[uf_col].astype(str).str.strip().str.upper() == estado
    ].copy()
    if municipios.empty:
        raise ValueError(f"Nenhum município encontrado para a UF '{estado}'.")

    municipios = municipios[[municipio_col, municipios.geometry.name]].rename(
        columns={municipio_col: "municipio"}
    )
    return analisar_camadas(queimadas, municipios)


def main():
    parser = argparse.ArgumentParser(
        description="Cruza polígonos de área queimada com limites municipais."
    )
    parser.add_argument("--queimadas", required=True, help="Shapefile, GeoPackage ou GeoJSON AQ1km")
    parser.add_argument("--municipios", required=True, help="Arquivo vetorial de municípios")
    parser.add_argument("--estado", required=True, help="Sigla da UF, por exemplo MT")
    parser.add_argument("--mes", required=True, type=int, choices=range(1, 13))
    parser.add_argument("--ano", type=int, default=date.today().year)
    parser.add_argument("--campo-data", help="Campo com a data das queimadas (autoidentificado quando possível)")
    parser.add_argument("--campo-uf", default="SIGLA_UF", help="Campo da UF nos municípios")
    parser.add_argument("--campo-municipio", default="NM_MUN", help="Campo do nome do município")
    parser.add_argument("--saida", help="Prefixo dos arquivos de saída")
    args = parser.parse_args()

    try:
        resultado, mapa, lider = analisar(
            args.queimadas,
            args.municipios,
            args.estado,
            args.mes,
            args.ano,
            args.campo_data,
            args.campo_uf,
            args.campo_municipio,
        )
    except ValueError as error:
        parser.error(str(error))

    print(
        f"Maior área queimada: {lider['municipio']} ({lider['area_km2']:.2f} km²) "
        f"em {args.estado.upper()}, {args.mes:02d}/{args.ano}."
    )
    prefixo = args.saida or f"queimadas_{args.estado.upper()}_{args.ano}_{args.mes:02d}"
    resultado.to_csv(f"{prefixo}.csv", index=False, encoding="utf-8-sig")
    mapa.save(f"{prefixo}.html")
    print(f"Resultados: {prefixo}.csv e {prefixo}.html")


if __name__ == "__main__":
    main()
