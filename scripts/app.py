#!/usr/bin/env python3
"""
Gera um mapa HTML dos casos geocodificados em public.casos.localizacao.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, text


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/ufologia",
)
SCHEMA = "public"
OUTPUT_HTML = Path("mapa_casos_brasileiros.html")
BRASIL_GEOJSON = Path("output/brasil_ufs_ibge.geojson")
IBGE_GEOJSON_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=UF"
)
VENDOR_ASSETS = {
    "leaflet.css": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
    "leaflet.js": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    "MarkerCluster.css": "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css",
    "MarkerCluster.Default.css": "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css",
    "leaflet.markercluster.js": "https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js",
}

UF_BY_CODE = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

STATE_BY_CODE = {
    "11": "Rondonia",
    "12": "Acre",
    "13": "Amazonas",
    "14": "Roraima",
    "15": "Para",
    "16": "Amapa",
    "17": "Tocantins",
    "21": "Maranhao",
    "22": "Piaui",
    "23": "Ceara",
    "24": "Rio Grande do Norte",
    "25": "Paraiba",
    "26": "Pernambuco",
    "27": "Alagoas",
    "28": "Sergipe",
    "29": "Bahia",
    "31": "Minas Gerais",
    "32": "Espirito Santo",
    "33": "Rio de Janeiro",
    "35": "Sao Paulo",
    "41": "Parana",
    "42": "Santa Catarina",
    "43": "Rio Grande do Sul",
    "50": "Mato Grosso do Sul",
    "51": "Mato Grosso",
    "52": "Goias",
    "53": "Distrito Federal",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera mapa HTML dos casos com localizacao.")
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--schema", default=SCHEMA)
    parser.add_argument("--output", default=str(OUTPUT_HTML))
    return parser.parse_args()


def validate_schema(schema: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError(f"Schema invalido: {schema}")
    return schema


def color_for(index: int) -> str:
    hue = (index * 137.508) % 360
    return f"hsl({hue:.1f}, 88%, 58%)"


def load_brazil_geojson(path: Path = BRASIL_GEOJSON) -> dict[str, Any] | None:
    if path.exists():
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    else:
        try:
            request = Request(IBGE_GEOJSON_URL, headers={"User-Agent": "portal-ufologia/1.0"})
            with urlopen(request, timeout=45) as response:
                raw_data = response.read()
                if raw_data.startswith(b"\x1f\x8b"):
                    raw_data = gzip.decompress(raw_data)
                data = json.loads(raw_data.decode("utf-8"))
        except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    for feature in data.get("features", []):
        code = str(feature.get("properties", {}).get("codarea", ""))
        feature.setdefault("properties", {})
        feature["properties"]["uf"] = UF_BY_CODE.get(code, code)
        feature["properties"]["nome"] = STATE_BY_CODE.get(code, code)
    return data


def ensure_vendor_assets(output_dir: Path) -> dict[str, str]:
    vendor_dir = output_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    refs: dict[str, str] = {}

    for filename, url in VENDOR_ASSETS.items():
        target = vendor_dir / filename
        if not target.exists():
            try:
                request = Request(url, headers={"User-Agent": "portal-ufologia/1.0"})
                with urlopen(request, timeout=45) as response:
                    target.write_bytes(response.read())
            except OSError:
                refs[filename] = url
                continue
        refs[filename] = f"vendor/{filename}" if target.exists() else url

    return refs


def fetch_points(database_url: str, schema: str) -> tuple[list[dict[str, Any]], int]:
    engine = create_engine(database_url)
    query = text(
        f"""
        SELECT
            id,
            titulo,
            data_ocorrencia,
            cidade,
            estado,
            pais,
            tipo_objeto,
            tem_seres,
            link_materia,
            sumario,
            descricao,
            localizacao
        FROM {schema}.casos
        WHERE localizacao IS NOT NULL
        ORDER BY data_ocorrencia NULLS LAST, titulo, id
        """
    )
    points: list[dict[str, Any]] = []
    unresolved = 0
    case_colors: dict[Any, str] = {}

    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()

    for row in rows:
        locations = row["localizacao"] or []
        case_color = case_colors.setdefault(row["id"], color_for(len(case_colors)))
        for location in locations:
            lat = location.get("latitude")
            lon = location.get("longitude")
            if lat is None or lon is None:
                unresolved += 1
                continue

            points.append(
                {
                    "id": row["id"],
                    "titulo": row["titulo"],
                    "ano": row["data_ocorrencia"].year if row["data_ocorrencia"] else None,
                    "decada": (row["data_ocorrencia"].year // 10) * 10
                    if row["data_ocorrencia"]
                    else None,
                    "data_ocorrencia": row["data_ocorrencia"].isoformat()
                    if row["data_ocorrencia"]
                    else None,
                    "cidade": location.get("cidade") or row["cidade"],
                    "estado": location.get("estado") or row["estado"],
                    "pais": location.get("pais") or row["pais"],
                    "tipo_objeto": row["tipo_objeto"],
                    "tem_seres": row["tem_seres"],
                    "link": row["link_materia"],
                    "resumo": row["sumario"] or row["descricao"] or "",
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "map_latitude": float(lat),
                    "map_longitude": float(lon),
                    "cor": case_color,
                    "endereco": location.get("endereco"),
                }
            )

    return points, unresolved


def render_html(
    points: list[dict[str, Any]],
    unresolved: int,
    brazil_geojson: dict[str, Any] | None,
    assets: dict[str, str],
) -> str:
    data = json.dumps(points, ensure_ascii=False)
    brazil_data = json.dumps(brazil_geojson, ensure_ascii=False) if brazil_geojson else "null"
    total_cases = len({point["id"] for point in points})
    total_with_beings = len({point["id"] for point in points if point.get("tem_seres")})
    total_without_beings = max(total_cases - total_with_beings, 0)
    total_multi = len(
        {
            point["id"]
            for point in points
            if sum(1 for other in points if other["id"] == point["id"]) > 1
        }
    )
    total_single = max(total_cases - total_multi, 0)
    extra_points = max(len(points) - total_cases, 0)
    beings_pct = (total_with_beings / total_cases * 100) if total_cases else 0
    no_beings_pct = max(100 - beings_pct, 0)
    multi_pct = (total_multi / total_cases * 100) if total_cases else 0
    single_pct = max(100 - multi_pct, 0)
    base_points_pct = (total_cases / len(points) * 100) if points else 0
    extra_points_pct = max(100 - base_points_pct, 0)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mapa de Casos Ufológicos Brasileiros</title>
  <link rel="stylesheet" href="{assets.get("leaflet.css", VENDOR_ASSETS["leaflet.css"])}">
  <link rel="stylesheet" href="{assets.get("MarkerCluster.css", VENDOR_ASSETS["MarkerCluster.css"])}">
  <link rel="stylesheet" href="{assets.get("MarkerCluster.Default.css", VENDOR_ASSETS["MarkerCluster.Default.css"])}">
  <style>
    .leaflet-pane,
    .leaflet-tile,
    .leaflet-marker-icon,
    .leaflet-marker-shadow,
    .leaflet-tile-container,
    .leaflet-pane > svg,
    .leaflet-pane > canvas,
    .leaflet-zoom-box,
    .leaflet-image-layer,
    .leaflet-layer {{
      position: absolute;
      left: 0;
      top: 0;
    }}
    .leaflet-container {{
      overflow: hidden;
      touch-action: pan-x pan-y;
      outline: none;
    }}
    .leaflet-container:focus,
    .leaflet-container *:focus,
    .leaflet-interactive:focus {{
      outline: none !important;
    }}
    .leaflet-zoom-box {{
      display: none !important;
    }}
    .leaflet-tile,
    .leaflet-marker-icon,
    .leaflet-marker-shadow {{
      user-select: none;
      -webkit-user-drag: none;
    }}
    .leaflet-tile {{
      filter: inherit;
      visibility: hidden;
      border: 0;
    }}
    .leaflet-tile-loaded {{
      visibility: inherit;
    }}
    .leaflet-zoom-animated {{
      transform-origin: 0 0;
    }}
    .leaflet-pane {{
      z-index: 400;
    }}
    .leaflet-tile-pane {{
      z-index: 200;
    }}
    .leaflet-overlay-pane {{
      z-index: 400;
    }}
    .leaflet-shadow-pane {{
      z-index: 500;
    }}
    .leaflet-marker-pane {{
      z-index: 600;
    }}
    .leaflet-tooltip-pane {{
      z-index: 650;
    }}
    .leaflet-popup-pane {{
      z-index: 700;
    }}
    .leaflet-control {{
      position: relative;
      z-index: 800;
      float: left;
      clear: both;
      pointer-events: auto;
    }}
    .leaflet-top,
    .leaflet-bottom {{
      position: absolute;
      z-index: 1000;
      pointer-events: none;
    }}
    .leaflet-top {{
      top: 0;
    }}
    .leaflet-right {{
      right: 0;
    }}
    .leaflet-bottom {{
      bottom: 0;
    }}
    .leaflet-left {{
      left: 0;
    }}
    .leaflet-right .leaflet-control {{
      float: right;
      margin-right: 10px;
    }}
    .leaflet-left .leaflet-control {{
      margin-left: 10px;
    }}
    .leaflet-top .leaflet-control {{
      margin-top: 10px;
    }}
    .leaflet-bottom .leaflet-control {{
      margin-bottom: 10px;
    }}
    .leaflet-control-zoom {{
      border: 1px solid rgba(148,163,184,.28);
      border-radius: 8px;
      box-shadow: 0 8px 22px rgba(0,0,0,.42);
      overflow: hidden;
      background: rgba(15,23,42,.92);
    }}
    .leaflet-control-zoom a {{
      display: block;
      width: 32px;
      height: 32px;
      color: #e5f3ff;
      line-height: 31px;
      text-align: center;
      text-decoration: none;
      font: bold 18px/32px Arial, sans-serif;
      background: rgba(15,23,42,.92);
    }}
    .leaflet-control-zoom a + a {{
      border-top: 1px solid rgba(148,163,184,.22);
    }}
    .leaflet-control-attribution {{
      padding: 3px 7px;
      border-radius: 6px 0 0 0;
      background: rgba(2,6,23,.72);
      color: #94a3b8;
      font-size: 10px;
    }}
    .leaflet-popup {{
      position: absolute;
      text-align: center;
      margin-bottom: 20px;
    }}
    .leaflet-popup-content-wrapper {{
      text-align: left;
      background: #fff;
    }}
    .leaflet-popup-content {{
      line-height: 1.35;
    }}
    .leaflet-popup-tip-container {{
      position: absolute;
      left: 50%;
      width: 40px;
      height: 20px;
      margin-left: -20px;
      overflow: hidden;
      pointer-events: none;
    }}
    .leaflet-popup-tip {{
      width: 17px;
      height: 17px;
      padding: 1px;
      margin: -10px auto 0;
      transform: rotate(45deg);
      background: #fff;
      box-shadow: 0 3px 14px rgba(15,23,42,.22);
    }}
    .leaflet-popup-close-button {{
      position: absolute;
      top: 4px;
      right: 6px;
      width: 24px;
      height: 24px;
      color: #64748b;
      text-align: center;
      text-decoration: none;
      font: 18px/24px Arial, sans-serif;
      z-index: 2;
    }}
    .leaflet-tooltip {{
      position: absolute;
      white-space: nowrap;
      pointer-events: none;
      user-select: none;
    }}
    :root {{
      color-scheme: dark;
      --panel: rgba(7,11,22,.86);
      --panel-strong: rgba(10,16,31,.96);
      --line: rgba(148,163,184,.24);
      --ink: #f8fafc;
      --muted: #a3b3c7;
      --accent: #22d3ee;
      --accent-strong: #facc15;
      --shadow: 0 22px 60px rgba(0,0,0,.58);
    }}
    html, body, #map {{
      width: 100%;
      height: 100%;
      margin: 0;
      box-sizing: border-box;
    }}
    *, *::before, *::after {{
      box-sizing: inherit;
    }}
    body {{
      overflow: hidden;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 78% 18%, rgba(34,211,238,.20), transparent 30%),
        radial-gradient(circle at 35% 72%, rgba(56,189,248,.13), transparent 26%),
        linear-gradient(135deg, #09213a, #0f3150 45%, #071b31);
    }}
    #map {{
      position: fixed;
      inset: 0;
      z-index: 0;
      background: #0c2942;
    }}
    #map::after {{
      content: "";
      position: absolute;
      inset: 0;
      z-index: 350;
      pointer-events: none;
      background:
        radial-gradient(circle at 70% 18%, rgba(56,189,248,.18), transparent 35%),
        linear-gradient(0deg, rgba(14,52,85,.34), rgba(18,64,98,.28));
      mix-blend-mode: screen;
    }}
    .leaflet-container {{
      width: 100vw;
      height: 100vh;
      background: #0c2942;
    }}
    .leaflet-tile-pane {{
      filter: brightness(1.42) saturate(1.28) sepia(.12) hue-rotate(172deg);
    }}
    .brazil-state {{
      transition: fill .16s ease, stroke .16s ease;
      cursor: pointer;
    }}
    .state-label {{
      color: rgba(203,213,225,.82);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .08em;
      text-align: center;
      text-shadow:
        0 1px 2px rgba(2,6,23,.96),
        0 -1px 2px rgba(2,6,23,.96),
        1px 0 2px rgba(2,6,23,.96),
        -1px 0 2px rgba(2,6,23,.96);
      pointer-events: none;
    }}
    .panel {{
      position: fixed;
      left: 18px;
      top: 18px;
      bottom: 18px;
      z-index: 500;
      width: min(390px, calc(100vw - 36px));
      display: grid;
      grid-template-rows: auto auto 1fr;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
      scrollbar-color: rgba(34,211,238,.55) rgba(15,23,42,.45);
    }}
    .panel.collapsed {{
      bottom: auto;
      width: min(390px, calc(100vw - 36px));
      grid-template-rows: auto;
    }}
    .panel.collapsed .controls,
    .panel.collapsed .results {{
      display: none;
    }}
    .head {{
      padding: 16px 16px 12px;
      border-bottom: 1px solid var(--line);
    }}
    .title-row {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 12px;
    }}
    h1 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    .collapse {{
      width: 34px;
      height: 34px;
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(15,23,42,.88);
      color: #e2e8f0;
      cursor: pointer;
      font-size: 18px;
      line-height: 1;
    }}
    .stats {{
      display: grid;
      grid-template-columns: 74px 1fr;
      gap: 8px;
      margin-top: 10px;
      align-items: stretch;
    }}
    .stat-total,
    .chart-card {{
      min-width: 0;
      border: 1px solid rgba(148,163,184,.18);
      border-radius: 7px;
      background: rgba(15,23,42,.54);
    }}
    .stat-total {{
      display: grid;
      align-content: center;
      padding: 8px;
    }}
    .stat-total b {{
      display: block;
      font-size: 24px;
      line-height: .9;
      letter-spacing: 0;
    }}
    .stat-total span {{
      display: block;
      margin-top: 4px;
      color: #dbeafe;
      font-size: 11px;
      font-weight: 750;
    }}
    .stat-total small {{
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 9px;
      line-height: 1.15;
    }}
    .charts {{
      display: grid;
      gap: 5px;
    }}
    .chart-card {{
      display: grid;
      grid-template-columns: 88px 1fr 46px;
      gap: 8px;
      align-items: center;
      padding: 6px 8px;
    }}
    .chart-head {{
      display: contents;
      margin-bottom: 0;
      font-size: 10px;
      color: #dbeafe;
      font-weight: 750;
    }}
    .chart-head span:first-child {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .chart-head span:last-child {{
      color: var(--muted);
      font-weight: 650;
      text-align: right;
    }}
    .stack-bar {{
      display: flex;
      width: 100%;
      height: 6px;
      overflow: hidden;
      border-radius: 99px;
      background: rgba(51,65,85,.72);
      box-shadow: inset 0 0 0 1px rgba(148,163,184,.15);
    }}
    .stack-part {{
      min-width: 2px;
      height: 100%;
    }}
    .stack-part.main {{
      background: linear-gradient(90deg, #22d3ee, #38bdf8);
    }}
    .stack-part.alt {{
      background: linear-gradient(90deg, #a855f7, #ec4899);
    }}
    .stack-part.soft {{
      background: linear-gradient(90deg, #64748b, #94a3b8);
    }}
    .chart-legend {{
      display: none;
    }}
    .chart-legend span {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      min-width: 0;
    }}
    .dot {{
      width: 6px;
      height: 6px;
      flex: 0 0 auto;
      border-radius: 50%;
      background: #22d3ee;
    }}
    .dot.alt {{
      background: #ec4899;
    }}
    .dot.soft {{
      background: #94a3b8;
    }}
    .controls {{
      display: grid;
      grid-template-columns: 1fr 132px;
      gap: 9px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
    }}
    .controls .wide {{
      grid-column: 1 / -1;
    }}
    input, select {{
      width: 100%;
      min-height: 38px;
      box-sizing: border-box;
      border: 1px solid rgba(148,163,184,.32);
      border-radius: 8px;
      padding: 9px 10px;
      background: rgba(15,23,42,.78);
      color: var(--ink);
      font: inherit;
      font-size: 13px;
      letter-spacing: 0;
    }}
    input::placeholder {{
      color: #94a3b8;
    }}
    option {{
      background: #0f172a;
      color: #e2e8f0;
    }}
    input[type="checkbox"] {{
      accent-color: var(--accent);
    }}
    .switches {{
      display: flex;
      align-items: center;
      gap: 12px;
      color: #cbd5e1;
      font-size: 12px;
    }}
    label {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
      user-select: none;
    }}
    label input {{
      width: auto;
      min-height: auto;
    }}
    .results {{
      overflow: auto;
      padding: 7px 0;
    }}
    .case {{
      width: 100%;
      display: grid;
      grid-template-columns: 17px 1fr;
      gap: 10px;
      padding: 10px 16px;
      border: 0;
      border-bottom: 1px solid rgba(15,23,42,.07);
      border-bottom-color: rgba(148,163,184,.12);
      background: transparent;
      color: inherit;
      text-align: left;
      cursor: pointer;
    }}
    .case:hover {{
      background: rgba(34,211,238,.11);
    }}
    .swatch {{
      width: 10px;
      height: 10px;
      margin-top: 4px;
      border: 1px solid rgba(248,250,252,.56);
      border-radius: 50%;
      background: var(--c);
      box-shadow: 0 0 0 2px color-mix(in srgb, var(--c), transparent 78%);
    }}
    .case-title {{
      display: block;
      font-size: 13px;
      font-weight: 750;
      line-height: 1.22;
    }}
    .case-place {{
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.2;
    }}
    .case-date {{
      display: inline-block;
      margin-top: 5px;
      color: #94a3b8;
      font-size: 11px;
    }}
    .marker-pin {{
      width: 14px;
      height: 14px;
      transform: translate(-7px, -7px);
      border: 1.5px solid rgba(226,245,255,.78);
      border-radius: 50%;
      background: var(--c);
      box-shadow:
        0 0 0 2px rgba(4,18,31,.54),
        0 0 8px color-mix(in srgb, var(--c), transparent 68%);
    }}
    .marker-pin::after {{
      display: none;
    }}
    .leaflet-tooltip.case-label {{
      border: 0;
      border-radius: 7px;
      padding: 5px 7px;
      background: rgba(2,6,23,.92);
      color: #e0f2fe;
      box-shadow: 0 6px 18px rgba(0,0,0,.45);
      font-size: 11px;
      font-weight: 700;
      line-height: 1.15;
    }}
    .leaflet-popup-content-wrapper {{
      border-radius: 10px;
      box-shadow: 0 14px 32px rgba(15,23,42,.24);
    }}
    .leaflet-popup-content {{
      min-width: 245px;
      margin: 14px 16px;
      font-size: 13px;
      line-height: 1.35;
    }}
    .popup-title {{
      margin-bottom: 8px;
      font-size: 15px;
      font-weight: 800;
      line-height: 1.2;
    }}
    .popup-meta {{
      margin: 4px 0;
      color: #334155;
    }}
    .popup-link {{
      display: inline-block;
      margin-top: 10px;
      color: #155e75;
      font-weight: 700;
      text-decoration: none;
    }}
    .detail-panel {{
      position: fixed;
      right: 18px;
      top: 18px;
      bottom: 18px;
      z-index: 520;
      width: min(420px, calc(100vw - 36px));
      display: grid;
      grid-template-rows: auto 1fr;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel-strong);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
      scrollbar-color: rgba(34,211,238,.55) rgba(15,23,42,.45);
    }}
    .detail-panel.hidden {{
      display: none;
    }}
    .detail-head {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 12px;
      padding: 18px 18px 13px;
      border-bottom: 1px solid var(--line);
    }}
    .detail-title {{
      margin: 0;
      font-size: 19px;
      line-height: 1.18;
      letter-spacing: 0;
    }}
    .detail-close {{
      width: 34px;
      height: 34px;
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(15,23,42,.88);
      color: #e2e8f0;
      cursor: pointer;
      font-size: 20px;
      line-height: 1;
    }}
    .detail-body {{
      overflow: auto;
      padding: 14px 18px 18px;
    }}
    .detail-grid {{
      display: grid;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .detail-row {{
      display: grid;
      grid-template-columns: 72px 1fr;
      gap: 8px;
      font-size: 13px;
      line-height: 1.35;
    }}
    .detail-row strong {{
      color: #e2e8f0;
    }}
    .detail-row span {{
      color: #a3b3c7;
    }}
    .detail-summary-title {{
      margin: 15px 0 7px;
      font-size: 12px;
      font-weight: 800;
      color: #67e8f9;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .detail-summary {{
      margin: 0;
      color: #e5e7eb;
      font-size: 14px;
      line-height: 1.5;
      white-space: pre-wrap;
    }}
    .cluster-icon {{
      display: grid;
      place-items: center;
      width: 30px;
      height: 30px;
      border: 1px solid rgba(103,232,249,.72);
      border-radius: 50%;
      background: rgba(8,32,50,.78);
      color: #a5f3fc;
      box-shadow:
        0 0 0 1px rgba(3,16,27,.62),
        0 5px 14px rgba(2,6,23,.30);
      font-weight: 800;
      font-size: 11px;
    }}
    @media (max-width: 720px) {{
      .panel {{
        left: 10px;
        right: 10px;
        top: 10px;
        bottom: auto;
        max-height: 46vh;
        width: auto;
      }}
      .stats {{
        grid-template-columns: 70px 1fr;
      }}
      .controls {{
        grid-template-columns: 1fr;
      }}
      .detail-panel {{
        left: 10px;
        right: 10px;
        top: auto;
        bottom: 10px;
        max-height: 48vh;
        width: auto;
      }}
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <section class="panel" id="panel">
    <div class="head">
      <div class="title-row">
        <h1>Mapa de Casos Ufológicos Brasileiros</h1>
        <button class="collapse" id="collapse" type="button" title="Recolher painel">−</button>
      </div>
      <div class="stats" aria-label="Resumo visual dos casos">
        <div class="stat-total">
          <b>{total_cases}</b>
          <span>casos</span>
          <small>{len(points)} pontos no mapa</small>
        </div>
        <div class="charts">
          <div class="chart-card" title="{total_with_beings} casos com seres e {total_without_beings} sem seres">
            <div class="chart-head"><span>Seres</span><span>{total_with_beings}/{total_cases}</span></div>
            <div class="stack-bar" aria-hidden="true">
              <i class="stack-part main" style="width:{beings_pct:.2f}%"></i>
              <i class="stack-part soft" style="width:{no_beings_pct:.2f}%"></i>
            </div>
            <div class="chart-legend"><span><i class="dot"></i>com</span><span><i class="dot soft"></i>sem</span></div>
          </div>
          <div class="chart-card" title="{total_multi} casos com mais de uma localização">
            <div class="chart-head"><span>Multi-local</span><span>{total_multi}/{total_cases}</span></div>
            <div class="stack-bar" aria-hidden="true">
              <i class="stack-part alt" style="width:{multi_pct:.2f}%"></i>
              <i class="stack-part soft" style="width:{single_pct:.2f}%"></i>
            </div>
            <div class="chart-legend"><span><i class="dot alt"></i>multi</span><span><i class="dot soft"></i>1 local</span></div>
          </div>
          <div class="chart-card" title="{extra_points} pontos extras por casos com múltiplas localizações">
            <div class="chart-head"><span>Pontos</span><span>+{extra_points}</span></div>
            <div class="stack-bar" aria-hidden="true">
              <i class="stack-part main" style="width:{base_points_pct:.2f}%"></i>
              <i class="stack-part alt" style="width:{extra_points_pct:.2f}%"></i>
            </div>
            <div class="chart-legend"><span><i class="dot"></i>casos</span><span><i class="dot alt"></i>extras</span></div>
          </div>
        </div>
      </div>
    </div>
    <div class="controls">
      <input class="wide" id="search" type="search" placeholder="Buscar título, cidade ou estado">
      <select id="stateFilter"><option value="">Todos os estados</option></select>
      <select id="decadeFilter"><option value="">Todas as décadas</option></select>
      <div class="switches wide">
        <label><input id="detailMap" type="checkbox" checked> Mapa detalhado</label>
        <label><input id="showLabels" type="checkbox"> Títulos fixos</label>
        <label><input id="onlyBeings" type="checkbox"> Com seres</label>
      </div>
    </div>
    <div class="results" id="results"></div>
  </section>
  <aside class="detail-panel hidden" id="detailPanel" aria-live="polite">
    <div class="detail-head">
      <h2 class="detail-title" id="detailTitle">Caso</h2>
      <button class="detail-close" id="detailClose" type="button" title="Fechar ficha">×</button>
    </div>
    <div class="detail-body">
      <div class="detail-grid">
        <div class="detail-row"><strong>Local</strong><span id="detailPlace"></span></div>
        <div class="detail-row"><strong>Data</strong><span id="detailDate"></span></div>
        <div class="detail-row"><strong>Década</strong><span id="detailDecade"></span></div>
        <div class="detail-row"><strong>Objeto</strong><span id="detailObject"></span></div>
        <div class="detail-row"><strong>Seres</strong><span id="detailBeings"></span></div>
      </div>
      <div class="detail-summary-title">Resumo</div>
      <p class="detail-summary" id="detailSummary"></p>
    </div>
  </aside>

  <script src="{assets.get("leaflet.js", VENDOR_ASSETS["leaflet.js"])}"></script>
  <script src="{assets.get("leaflet.markercluster.js", VENDOR_ASSETS["leaflet.markercluster.js"])}"></script>
  <script>
    const points = {data};
    const brazilGeojson = {brazil_data};
    const map = L.map('map', {{
      preferCanvas: false,
      zoomControl: false,
      zoomSnap: 0.25,
      boxZoom: false,
      keyboard: false,
      worldCopyJump: false,
      minZoom: 3,
      maxZoom: 11
    }}).setView([-15.8, -47.9], 4);
    L.control.zoom({{ position: 'bottomright' }}).addTo(map);

    let detailEnabled = true;
    const detailLayer = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      maxZoom: 19,
      opacity: 0.96,
      subdomains: 'abcd',
      attribution: '&copy; OpenStreetMap &copy; CARTO'
    }}).addTo(map);

    let selectedState = '';

    function normalizeText(value) {{
      return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim();
    }}

    function featureStateName(feature) {{
      return feature?.properties?.nome || feature?.properties?.uf || '';
    }}

    function stateMatchesSelection(feature) {{
      return selectedState
        && normalizeText(featureStateName(feature)) === normalizeText(selectedState);
    }}

    function stateStyle(feature) {{
      const selected = stateMatchesSelection(feature);
      return {{
        color: selected ? '#facc15' : (detailEnabled ? '#38bdf8' : '#60a5fa'),
        weight: selected ? 2.25 : (detailEnabled ? 0.8 : 1.05),
        fillColor: selected ? '#22d3ee' : (detailEnabled ? '#173d5d' : '#143957'),
        fillOpacity: selected ? 0.40 : (detailEnabled ? 0.26 : 0.80),
        interactive: true
      }};
    }}

    let brazilLayer = null;
    if (brazilGeojson) {{
      brazilLayer = L.geoJSON(brazilGeojson, {{
        className: 'brazil-state',
        style: stateStyle,
        onEachFeature(feature, layer) {{
          const uf = feature?.properties?.uf || '';
          const nome = feature?.properties?.nome || uf;
          layer.bindTooltip(`${{nome}}`, {{
            sticky: true,
            direction: 'center',
            className: 'case-label'
          }});
          layer.on('mouseover', () => {{
            layer.bringToFront?.();
            layer.setStyle({{
              fillColor: '#22d3ee',
              fillOpacity: stateMatchesSelection(feature) ? 0.46 : (detailEnabled ? 0.36 : 0.78),
              color: '#facc15',
              weight: stateMatchesSelection(feature) ? 2.45 : 1.6
            }});
          }});
          layer.on('mouseout', () => brazilLayer.resetStyle(layer));
          layer.on('click', event => {{
            L.DomEvent.stop(event);
            selectStateFromMap(feature, layer);
          }});
          const center = layer.getBounds().getCenter();
          L.marker(center, {{
            icon: L.divIcon({{ className: 'state-label', html: uf, iconSize: [34, 16], iconAnchor: [17, 8] }}),
            interactive: false
          }}).addTo(map);
        }}
      }}).addTo(map);
      map.setMaxBounds(brazilLayer.getBounds().pad(0.35));
    }}

    const routeLayer = L.layerGroup().addTo(map);

    const cluster = L.markerClusterGroup({{
      showCoverageOnHover: false,
      maxClusterRadius: 36,
      iconCreateFunction(group) {{
        return L.divIcon({{
          html: `<div class="cluster-icon">${{group.getChildCount()}}</div>`,
          className: '',
          iconSize: [30, 30],
          iconAnchor: [15, 15]
        }});
      }}
    }}).addTo(map);

    const els = {{
      panel: document.getElementById('panel'),
      collapse: document.getElementById('collapse'),
      search: document.getElementById('search'),
      state: document.getElementById('stateFilter'),
      decade: document.getElementById('decadeFilter'),
      detail: document.getElementById('detailMap'),
      labels: document.getElementById('showLabels'),
      beings: document.getElementById('onlyBeings'),
      results: document.getElementById('results'),
      detailPanel: document.getElementById('detailPanel'),
      detailClose: document.getElementById('detailClose'),
      detailTitle: document.getElementById('detailTitle'),
      detailPlace: document.getElementById('detailPlace'),
      detailDate: document.getElementById('detailDate'),
      detailDecade: document.getElementById('detailDecade'),
      detailObject: document.getElementById('detailObject'),
      detailBeings: document.getElementById('detailBeings'),
      detailSummary: document.getElementById('detailSummary')
    }};

    const markerByKey = new Map();
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({{
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    }}[ch]));

    function place(point) {{
      return [point.cidade, point.estado, point.pais].filter(Boolean).join(', ');
    }}

    function keyFor(point) {{
      return `${{point.id}}:${{point.cidade}}:${{point.latitude}}:${{point.longitude}}`;
    }}

    function decadeLabel(decade) {{
      if (!decade) return 'sem década';
      return decade < 2000 ? `Anos ${{String(decade).slice(2)}}` : `Anos ${{decade}}`;
    }}

    function openCase(point) {{
      els.detailTitle.textContent = point.titulo || 'Caso';
      els.detailPlace.textContent = place(point) || 'não informado';
      els.detailDate.textContent = point.data_ocorrencia || 'não informada';
      els.detailDecade.textContent = decadeLabel(point.decada);
      els.detailObject.textContent = point.tipo_objeto || 'não informado';
      els.detailBeings.textContent = point.tem_seres ? 'sim' : 'não';
      els.detailSummary.textContent = point.resumo || 'Resumo não informado.';
      els.detailPanel.classList.remove('hidden');
      map.panTo([point.map_latitude, point.map_longitude], {{ animate: true }});
      setTimeout(() => map.invalidateSize({{ pan: false }}), 80);
    }}

    function markerIcon(point) {{
      return L.divIcon({{
        html: `<div class="marker-pin" style="--c:${{point.cor}}"></div>`,
        className: '',
        iconSize: [14, 14],
        iconAnchor: [7, 7],
        popupAnchor: [0, -10],
        tooltipAnchor: [0, -14]
      }});
    }}

    function populateFilters() {{
      const states = [...new Set(points.flatMap(point => String(point.estado || '').split(';').map(s => s.trim()).filter(Boolean)))]
        .sort((a, b) => a.localeCompare(b));
      for (const state of states) {{
        const option = document.createElement('option');
        option.value = state;
        option.textContent = state;
        els.state.appendChild(option);
      }}

      const decades = [...new Set(points.map(point => point.decada).filter(Boolean))].sort((a, b) => a - b);
      for (const decade of decades) {{
        const option = document.createElement('option');
        option.value = decade;
        option.textContent = decadeLabel(decade);
        els.decade.appendChild(option);
      }}
    }}

    function stateOptionForFeature(feature) {{
      const featureName = featureStateName(feature);
      const normalizedFeatureName = normalizeText(featureName);
      const options = Array.from(els.state.options);
      const match = options.find(option =>
        option.value && normalizeText(option.value) === normalizedFeatureName
      );
      if (match) return match.value;

      const option = document.createElement('option');
      option.value = featureName;
      option.textContent = featureName;
      els.state.appendChild(option);
      return option.value;
    }}

    function applyStateSelection(state) {{
      els.state.value = state;
      selectedState = state;
      if (brazilLayer) {{
        brazilLayer.setStyle(stateStyle);
      }}
      render();
    }}

    function selectStateFromMap(feature, layer) {{
      const state = stateOptionForFeature(feature);
      const nextState = normalizeText(els.state.value) === normalizeText(state) ? '' : state;
      applyStateSelection(nextState);
      if (nextState && layer?.getBounds) {{
        const bounds = layer.getBounds();
        if (bounds.isValid()) {{
          setTimeout(() => map.fitBounds(bounds, mapPadding()), 40);
        }}
      }}
    }}

    function updateBaseMap() {{
      detailEnabled = els.detail.checked;
      if (detailEnabled && !map.hasLayer(detailLayer)) {{
        detailLayer.addTo(map);
      }}
      if (!detailEnabled && map.hasLayer(detailLayer)) {{
        map.removeLayer(detailLayer);
      }}
      if (brazilLayer) {{
        brazilLayer.setStyle(stateStyle);
      }}
      setTimeout(() => map.invalidateSize({{ pan: false }}), 120);
    }}

    function matches(point) {{
      const term = els.search.value.trim().toLowerCase();
      const state = els.state.value;
      const decade = els.decade.value;
      const haystack = [point.titulo, point.cidade, point.estado, point.pais, point.tipo_objeto].join(' ').toLowerCase();
      const sameState = !state
        || String(point.estado || '').split(';').some(item => normalizeText(item) === normalizeText(state));
      return (!term || haystack.includes(term))
        && sameState
        && (!decade || String(point.decada) === decade)
        && (!els.beings.checked || point.tem_seres);
    }}

    function makeMarker(point) {{
      const marker = L.marker([point.map_latitude, point.map_longitude], {{ icon: markerIcon(point), riseOnHover: true }});
      marker.bindTooltip(escapeHtml(`${{point.titulo}} — ${{point.cidade || ''}}`), {{
        permanent: els.labels.checked,
        direction: 'top',
        offset: [0, -10],
        className: 'case-label'
      }});
      marker.on('click', () => openCase(point));
      return marker;
    }}

    function drawCaseLines(visiblePoints) {{
      const groups = new Map();
      for (const point of visiblePoints) {{
        const lat = Number(point.map_latitude);
        const lon = Number(point.map_longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        if (!groups.has(point.id)) groups.set(point.id, []);
        groups.get(point.id).push(point);
      }}

      for (const group of groups.values()) {{
        if (group.length < 2) continue;
        const coords = group.map(point => [point.map_latitude, point.map_longitude]);
        const color = group[0].cor || '#22d3ee';

        L.polyline(coords, {{
          color: '#e2e8f0',
          weight: 4,
          opacity: 0.12,
          lineCap: 'round',
          lineJoin: 'round',
          interactive: false
        }}).addTo(routeLayer);

        L.polyline(coords, {{
          color,
          weight: 1.4,
          opacity: 0.62,
          dashArray: '6 7',
          lineCap: 'round',
          lineJoin: 'round',
          interactive: false
        }}).addTo(routeLayer);
      }}
    }}

    function mapPadding() {{
      const panelOpen = !els.panel.classList.contains('collapsed') && window.innerWidth > 720;
      const detailOpen = !els.detailPanel.classList.contains('hidden') && window.innerWidth > 960;
      return {{
        paddingTopLeft: [panelOpen ? 430 : 32, 32],
        paddingBottomRight: [detailOpen ? 440 : 32, 32],
        maxZoom: 7
      }};
    }}

    function settleMap(bounds) {{
      requestAnimationFrame(() => {{
        map.invalidateSize({{ pan: false }});
        if (bounds.length === 1) {{
          map.setView(bounds[0], 9, {{ animate: false }});
        }} else {{
          map.fitBounds(bounds, mapPadding());
        }}
      }});
    }}

    function render() {{
      routeLayer.clearLayers();
      cluster.clearLayers();
      markerByKey.clear();
      els.results.textContent = '';

      const visible = points.filter(matches);
      const bounds = [];

      drawCaseLines(visible);

      for (const point of visible) {{
        const marker = makeMarker(point);
        cluster.addLayer(marker);
        markerByKey.set(keyFor(point), marker);
        bounds.push([point.map_latitude, point.map_longitude]);

        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'case';
        item.innerHTML = `
          <span class="swatch" style="--c:${{point.cor}}"></span>
          <span>
            <span class="case-title">${{escapeHtml(point.titulo)}}</span>
            <span class="case-place">${{escapeHtml(place(point))}}</span>
            <span class="case-date">${{escapeHtml(point.data_ocorrencia || '')}}</span>
          </span>
        `;
        item.addEventListener('click', () => {{
          cluster.zoomToShowLayer(marker, () => {{
            map.setView([point.map_latitude, point.map_longitude], Math.max(map.getZoom(), 8), {{ animate: true }});
            openCase(point);
          }});
        }});
        els.results.appendChild(item);
      }}

      if (!visible.length) {{
        const empty = document.createElement('div');
        empty.className = 'case-place';
        empty.style.padding = '14px 16px';
        empty.textContent = 'Nenhum ponto encontrado.';
        els.results.appendChild(empty);
        return;
      }}

      settleMap(bounds);
    }}

    populateFilters();
    render();

    els.search.addEventListener('input', render);
    els.state.addEventListener('change', () => applyStateSelection(els.state.value));
    els.decade.addEventListener('change', render);
    els.detail.addEventListener('change', updateBaseMap);
    els.labels.addEventListener('change', render);
    els.beings.addEventListener('change', render);
    els.detailClose.addEventListener('click', () => {{
      els.detailPanel.classList.add('hidden');
      setTimeout(() => map.invalidateSize({{ pan: false }}), 80);
    }});
    els.collapse.addEventListener('click', () => {{
      els.panel.classList.toggle('collapsed');
      els.collapse.textContent = els.panel.classList.contains('collapsed') ? '+' : '−';
      setTimeout(render, 180);
    }});
    window.addEventListener('resize', () => setTimeout(render, 150));
  </script>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    schema = validate_schema(args.schema)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    points, unresolved = fetch_points(args.database_url, schema)
    if not points:
        raise RuntimeError("Nenhum ponto com latitude/longitude encontrado em public.casos.localizacao.")

    brazil_geojson = load_brazil_geojson()
    assets = ensure_vendor_assets(output_path.parent)
    output_path.write_text(render_html(points, unresolved, brazil_geojson, assets), encoding="utf-8")
    print(f"Mapa gerado: {output_path}")
    print(f"{len(points)} pontos de localizacao, {len({point['id'] for point in points})} casos, {unresolved} entradas sem coordenada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
