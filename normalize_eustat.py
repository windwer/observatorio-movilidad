"""Normalize the official Eustat 2025 Gipuzkoa section table, *without* guessing geometry keys.

This parser recognises the published hierarchical layout:
 Cod | Municipio | Dist | Secc | Total | ... . Section 000 is a subtotal and
must not be counted as a residential section. Output can be merged later with
GeoEuskadi using the composite (municipality, district, section) key.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
from pathlib import Path
from territory import valid_municipality, MUNICIPALITIES

def read_rows(raw):
    content=None
    for enc in ('utf-8-sig','cp1252','latin1'):
        try:content=raw.decode(enc);break
        except UnicodeError:continue
    if content is None:raise ValueError('Codificación CSV no reconocida')
    sample=content[:12000]
    try:dialect=csv.Sniffer().sniff(sample,delimiters=';,\t')
    except csv.Error:dialect=csv.excel;dialect.delimiter=';'
    return list(csv.reader(io.StringIO(content), dialect))

def parse(raw,require_six=True):
    rows=read_rows(raw)
    current_code='';current_town=None;current_dist='';out=[];seen=set()
    for row in rows:
        if len(row)<5:continue
        cells=[str(x).strip() for x in row]
        code,name,dist,sect,total=cells[:5]
        if code.isdigit() and len(code)<=4 and name and not name.isdigit():
            current_code=code.zfill(3)
            current_town=valid_municipality(name)
            current_dist=''
        elif name and valid_municipality(name):
            current_town=valid_municipality(name)
        if dist.isdigit():current_dist=dist.zfill(2)
        if not current_town or not current_code or not current_dist:continue
        if not sect.isdigit() or int(sect)==0:continue
        value=total.replace(' ','').replace('\u00a0','')
        if value in ('','-','..'):continue
        # Eustat reports population as an integer with thousands separator.
        if ',' in value:raise ValueError('Población con decimal inesperado: '+value)
        value=value.replace('.','')
        if not value.isdigit():continue
        key=(current_code,current_dist,sect.zfill(3))
        if key in seen:raise ValueError('Sección censal duplicada: '+str(key))
        seen.add(key)
        out.append({'municipality_code':current_code,'municipality':current_town,
                    'district':current_dist,'section':sect.zfill(3),
                    'population':int(value),'reference_date':'2025-01-01'})
    found={r['municipality'] for r in out}
    missing=set(MUNICIPALITIES)-found
    if not out:raise ValueError('No se encontró la tabla Eustat Cod/Municipio/Dist/Secc/Total. Revisa el formato original.')
    if missing and require_six:raise ValueError('El CSV no cubre los seis municipios: '+', '.join(sorted(missing)))
    return {'rows':out,'municipalities':sorted(found),'missing_municipalities':sorted(missing),
            'populations_by_municipality':{m:sum(r['population'] for r in out if r['municipality']==m) for m in sorted(found)},
            'note':'Valores de población censal por sección, no habitantes dentro de isócronas.'}

def save_csv(data,path):
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['municipality_code','municipality','district','section','population','reference_date'])
        writer.writeheader();writer.writerows(data['rows'])
    return str(target)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True);p.add_argument('--output',default='data/references/eustat_sections_normalized.csv')
    p.add_argument('--allow-partial',action='store_true')
    a=p.parse_args();data=parse(Path(a.input).read_bytes(),not a.allow_partial)
    target=save_csv(data,a.output)
    print(json.dumps({k:v for k,v in data.items() if k!='rows'}|{'sections':len(data['rows']),'output':target},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
