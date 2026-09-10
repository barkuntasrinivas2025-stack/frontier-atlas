from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from src.config.settings import get_settings
TABS={'Startups':['name','description','website','founded_year','funding','source_url','source_name','collected_at'],'Products':['name','description','website','category','company_name','source_url','source_name','collected_at'],'Research Papers':['title','abstract','authors','paper_url','published_at','github_url','github_stars','source_url','source_name','collected_at'],'Jobs':['title','company','location','url','description','published_at','source_url','source_name','collected_at'],'News':['title','url','summary','content','published_at','source_url','source_name','collected_at'],'Entity Mapping Log':['raw_name','normalized_name','canonical_name','entity_type','match_method','confidence','created_at']}
class GoogleSheetsExporter:
 def __init__(self,spreadsheet_id=None,credentials_file=None):
  s=get_settings(); spreadsheet_id=spreadsheet_id or s.google_sheet_id; credentials_file=credentials_file or s.google_service_account_file
  if not spreadsheet_id: raise ValueError('FA_GOOGLE_SHEET_ID is required')
  p=Path(credentials_file); self.client=gspread.authorize(Credentials.from_service_account_file(str(p),scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive.file'])); self.sheet=self.client.open_by_key(spreadsheet_id)
 def ensure_tabs(self):
  existing={w.title:w for w in self.sheet.worksheets()}
  for name,headers in TABS.items():
   w=existing.get(name) or self.sheet.add_worksheet(title=name,rows=1000,cols=max(10,len(headers)))
   if w.row_values(1)!=headers: w.update('A1', [headers]); w.freeze(rows=1)
  return self.sheet
 def replace_rows(self,name,rows):
  w=self.sheet.worksheet(name); headers=TABS[name]; w.clear(); w.update('A1',[headers]); values=[]
  for row in rows: values.append([self._v(row.get(h)) for h in headers])
  if values: w.update(f'A2',[headers] if False else values)
  w.freeze(rows=1)
 def _v(self,v):
  if isinstance(v,list): return ', '.join(map(str,v))
  if isinstance(v,dict): return str(v)
  return '' if v is None else str(v)
