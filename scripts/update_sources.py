"""Refresh public macro/finance sources into data_raw.
API keys belong in environment variables or GitHub Actions Secrets, never in files.
This script intentionally does not overwrite curated processed datasets.
"""
from pathlib import Path
import os, json, urllib.request, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data_raw'; OUT.mkdir(exist_ok=True)
def world_bank(indicator='NY.GDP.MKTP.CD', countries='all', date='1960:2025'):
 url=f'https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}?format=json&per_page=20000&date={date}'
 with urllib.request.urlopen(url,timeout=60) as resp: meta,data=json.load(resp)
 rows=[{'country_code':x.get('countryiso3code'),'country':x.get('country'),'year':x.get('date'),'value':x.get('value'),'indicator':indicator,'source':'World Bank'} for x in data]
 pd.DataFrame(rows).to_csv(OUT/f'worldbank_{indicator}.csv',index=False,encoding='utf-8-sig')
 return len(rows)
if __name__=='__main__': print('downloaded rows:',world_bank())
