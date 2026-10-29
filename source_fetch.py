"""Allowlisted, provenance-preserving source fetcher; optional network in local deployment.

This module does not claim that freshly downloaded feeds certify 2025 schedules.
"""
import io
import json
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

GTFS_URLS={
    'ekialdebus':'https://gtfs-source-feeds.transit.land/es-nap-1201.zip',
    'irunbus':'https://gtfs-source-feeds.transit.land/es-nap-1199.zip',
    # Official Moveuskadi static publications.  Euskotren is filtered by the
    # ingestion engine to the E1/E2 rail corridor lines; the Errenteria feed
    # contains the complete urban network.
    'euskotren':'https://opendata.euskadi.eus/transport/moveuskadi/euskotren/gtfs_euskotren.zip',
    'errenteria_urbanoa':'https://opendata.euskadi.eus/transport/moveuskadi/errenteria/gtfs_errenteriako_urbanoa.zip',
}
POP_URL='https://es.eustat.eus/elementos/xls0011434_c.csv'
SECTIONS_URL='https://www.geo.euskadi.eus/cartografia/DatosDescarga/Limites/Unidades_estadisticas/SECCIONES_EUSTAT_5000_ETRS89.zip'
OVERPASS_ENDPOINTS=(
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
)
# Small, overlapping pilot windows around the DEMO stops.  Keeping requests
# bounded makes the Product Review refresh reproducible and avoids asking an
# Overpass instance for the whole of eastern Gipuzkoa in one expensive query.
OSM_PILOT_BBOXES=(
    (43.280,-2.020,43.322,-1.970), # Antiguo / Miramon / Donostia
    (43.273,-1.970,43.310,-1.925), # Astigarraga / Altza
    (43.305,-1.955,43.338,-1.915), # Pasaia
    (43.294,-1.920,43.330,-1.880), # Errenteria / Lezo
    (43.286,-1.875,43.320,-1.837), # Oiartzun
    (43.310,-1.835,43.345,-1.800), # Ventas / Hospital / Olaberria
    (43.322,-1.815,43.352,-1.780), # Irun centro
    (43.345,-1.808,43.375,-1.775), # Hondarribia / aeropuerto
    (43.325,-1.790,43.355,-1.755), # Irun este / Artia
    (43.322,-1.770,43.350,-1.738), # Zaisa
)


def fetch(url,limit=90_000_000,timeout=35):
    req=urllib.request.Request(url,headers={'User-Agent':'BidasoaOarsoObservatory/0.2 (local private research; contact: data sources listed in README)', 'Accept':'application/zip,application/octet-stream,text/csv,*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        content=resp.read(limit+1)
    if len(content)>limit:raise ValueError('Archivo fuente demasiado grande')
    return content


def fetch_gtfs(operator):
    if operator not in GTFS_URLS:raise ValueError('Operador no admitido')
    content=fetch(GTFS_URLS[operator])
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            files=set(z.namelist())
            if not {'routes.txt','stops.txt','trips.txt','stop_times.txt'}.issubset(files):
                raise ValueError('El servidor no devolvió un GTFS válido')
    except zipfile.BadZipFile as e:raise ValueError('El servidor no devolvió un ZIP válido') from e
    return content


def fetch_reference(name,dest):
    if name not in ('eustat_csv','census_geometry'):raise ValueError('Fuente no autorizada')
    url=POP_URL if name=='eustat_csv' else SECTIONS_URL
    data=fetch(url,limit=65_000_000)
    if name=='census_geometry' and not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError('La cartografía no llegó como ZIP')
    if name=='eustat_csv' and len(data)<200:raise ValueError('CSV parece vacío')
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    return {'name':name,'bytes':len(data),'location':str(dest),'url':url,
            'notice':'Archivo original conservado; no está georreferenciado ni interpretado hasta cruzarlo con secciones censales'}


def fetch_osm_walkways(*,allow_pilot=False):
    """Return the bundled provincial OSM network, preserving its provenance.

    The production package contains the filtered Gipuzkoa extract generated
    from the regional Geofabrik PBF.  Returning that immutable local artifact
    prevents the refresh button from silently replacing the province-wide
    network with the old eastern pilot windows.  The Overpass fallback remains
    available only when developing a package without the bundled artifact.
    """
    bundled=Path(__file__).resolve().parent/'data'/'real'/'geography'/'walkways.geojson'
    if bundled.is_file():
        return bundled.read_bytes()
    if not allow_pilot:raise ValueError('Falta la red provincial. Importa un extracto completo; el piloto parcial requiere autorización explícita de desarrollo.')
    ways={}
    for south,west,north,east in OSM_PILOT_BBOXES:
        query=f'[out:json][timeout:60];way["highway"]({south},{west},{north},{east});out geom;'
        error=None
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                # GET avoids proxy-specific rejection of form-encoded POSTs on
                # some Windows review environments. The bounded query remains
                # short enough for a normal URL.
                request=urllib.request.Request(endpoint+'?'+urllib.parse.urlencode({'data':query}),headers={'User-Agent':'BidasoaOarsoObservatory/0.6.3-product-review'})
                with urllib.request.urlopen(request,timeout=90) as r:doc=json.load(r)
                break
            except Exception as exc: # the next public instance may still be healthy
                error=exc
        else:
            raise ValueError(f'No se pudo obtener la red OSM del área piloto: {error}')
        for item in doc.get('elements',[]):
            if item.get('type')!='way' or len(item.get('geometry',[]))<2:continue
            tags=item.get('tags',{})
            if tags.get('foot') in ('no','private') or tags.get('access') in ('private','no'):continue
            highway=tags.get('highway')
            if highway not in ('footway','pedestrian','path','living_street','residential','steps','service','unclassified','tertiary','secondary','primary','track','cycleway','bridleway'):
                continue
            coords=[[p['lon'],p['lat']] for p in item['geometry']]
            ways[item['id']]={'type':'Feature','id':str(item['id']),'properties':tags,
             'geometry':{'type':'LineString','coordinates':coords}}
    if not ways:raise ValueError('Overpass no devolvió red peatonal')
    return json.dumps({'type':'FeatureCollection','name':'OSM pedestrian network - Product Review pilot',
      'metadata':{'source':'OpenStreetMap contributors','retrieved':date.today().isoformat(),
       'scope':'bounded windows around DEMO stops; not a transport API'},
      'features':list(ways.values())},ensure_ascii=False).encode()

def fetch_osm_buildings():
    """Retrieve OSM residential buildings for the pilot areas, with explicit tags.

    They are usable only as an *allocation model* for official census population,
    and never imply population on their own.
    """
    bboxes=[(43.25,-1.98,43.40,-1.80),(43.25,-1.87,43.41,-1.68)]
    buildings={}
    for south,west,north,east in bboxes:
        query=f'[out:json][timeout:100];way["building"]({south},{west},{north},{east});out geom;'
        request=urllib.request.Request('https://overpass.kumi.systems/api/interpreter',data=urllib.parse.urlencode({'data':query}).encode(),headers={'User-Agent':'BidasoaOarsoObservatory/0.2','Content-Type':'application/x-www-form-urlencoded'},method='POST')
        with urllib.request.urlopen(request,timeout=125) as r:doc=json.load(r)
        for item in doc.get('elements',[]):
            if item.get('type')!='way':continue
            tags=item.get('tags',{});building=tags.get('building','')
            if building not in ('residential','apartments','house','detached','semidetached_house','terrace','dormitory','bungalow','farm','static_caravan','cabin'):
                continue
            coords=[[p['lon'],p['lat']] for p in item.get('geometry',[])]
            if len(coords)<4:continue
            if coords[0]!=coords[-1]:coords.append(coords[0])
            buildings[item['id']]={'type':'Feature','id':str(item['id']),'properties':tags,
             'geometry':{'type':'Polygon','coordinates':[coords]}}
    if not buildings:raise ValueError('Overpass no devolvió edificios residenciales')
    return json.dumps({'type':'FeatureCollection','features':list(buildings.values())},ensure_ascii=False).encode()

# urllib.parse is loaded here, explicitly, for the optional Overpass request.
import urllib.parse
