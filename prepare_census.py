"""Join official 2025 Eustat section populations to GeoEuskadi census geometries.

Explicit column selection prevents accidental spatial joins on repeated section
numbers (001, 002, ...) across different municipalities or districts.
Run `python prepare_census.py inspect PATH` to see input columns first.
"""
from __future__ import annotations
import argparse
import json
import sys
import unicodedata
from pathlib import Path


def load_pop(path,header=0):
    import pandas as pd
    last=None
    for enc in ('utf-8-sig','cp1252','latin1'):
        try:
            return pd.read_csv(path,sep=None,engine='python',header=header,encoding=enc,on_bad_lines='skip',dtype=str)
        except (ValueError,UnicodeError) as e:last=e
    raise ValueError('No se pudo interpretar la tabla CSV') from last


def load_shapes(path):
    import geopandas as gpd
    p=Path(path).resolve()
    if p.suffix.lower()=='.zip':return gpd.read_file('zip://'+str(p))
    return gpd.read_file(str(p))


def norm_text(x):
    return ''.join(ch for ch in unicodedata.normalize('NFD',str(x or '').lower()) if unicodedata.category(ch)!='Mn').strip()


def join_key(row,columns):
    return ':'.join((str(int(float(str(row[c]).strip()))) if str(row[c]).strip().replace('.','',1).isdigit() else str(row[c]).strip()) for c in columns)


def merge(geometry,population,geometry_keys,population_keys,people_column,municipality_column,output,header=0):
    from territory import valid_municipality
    gdf=load_shapes(geometry)
    df=load_pop(population,header)
    if len(geometry_keys)!=len(population_keys):raise ValueError('Las claves compuestas deben tener el mismo número de campos')
    for col in geometry_keys:
        if col not in gdf.columns:raise ValueError(f'Campo geográfico inexistente: {col}')
    for col in population_keys+[people_column,municipality_column]:
        if col not in df.columns:raise ValueError(f'Campo estadístico inexistente: {col}')
    result_map={};duplicate=[]
    for _,row in df.iterrows():
        municipality=valid_municipality(row[municipality_column])
        if not municipality:continue
        key=join_key(row,population_keys)
        if key in result_map:
            duplicate.append(key);continue
        raw=str(row[people_column]).strip()
        try:pop=float(raw.replace('.','').replace(',','.')) if ',' in raw else float(raw.replace('.','')) if raw.count('.')==1 and len(raw.split('.')[-1])==3 else float(raw)
        except ValueError:continue
        if pop<0:continue
        result_map[key]={'municipality':municipality,'population':pop}
    if duplicate:raise ValueError(f'Claves de población duplicadas; revisa municipio/distrito/sección: {duplicate[:6]}')
    out=[];used=set()
    if gdf.crs is None:raise ValueError('Falta CRS en cartografía de secciones; no se pueden asignar coordenadas con seguridad')
    gdf=gdf.to_crs('EPSG:4326')
    for _,row in gdf.iterrows():
        key=join_key(row,geometry_keys)
        datum=result_map.get(key)
        if not datum or row.geometry is None or row.geometry.is_empty:continue
        if key in used:raise ValueError(f'Geometría censal duplicada: {key}')
        used.add(key)
        out.append({'type':'Feature','properties':{'section_id':key,'municipality':datum['municipality'],
             'population':datum['population'],'reference_date':'2025-01-01','source':'Eustat + GeoEuskadi'},
             'geometry':row.geometry.__geo_interface__})
    if not out:raise ValueError('No hay secciones cruzadas. Inspecciona columnas y claves compuestas.')
    destination=Path(output);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps({'type':'FeatureCollection','features':out},ensure_ascii=False),encoding='utf-8')
    return {'features':len(out),'municipalities':sorted({f['properties']['municipality'] for f in out}),
            'unmatched_census_rows':len(result_map)-len(used),'output':str(destination)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    a=sub.add_parser('inspect');a.add_argument('path');a.add_argument('--header',type=int,default=0)
    a=sub.add_parser('merge');a.add_argument('--geometry',required=True);a.add_argument('--population',required=True)
    a.add_argument('--geometry-keys',required=True,help='Campos separados por coma: municipio,distrito,seccion')
    a.add_argument('--population-keys',required=True,help='Campos equivalentes separados por coma')
    a.add_argument('--people-column',required=True);a.add_argument('--municipality-column',required=True)
    a.add_argument('--output',default='data/geo/census.geojson');a.add_argument('--header',type=int,default=0)
    args=parser.parse_args()
    if args.command=='inspect':
        if Path(args.path).suffix.lower()=='.csv':frame=load_pop(args.path,args.header)
        else:frame=load_shapes(args.path)
        print('Columnas:',list(frame.columns));print(frame.head(7).to_string(index=False))
    else:
        result=merge(args.geometry,args.population,args.geometry_keys.split(','),args.population_keys.split(','),args.people_column,args.municipality_column,args.output,args.header)
        print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
