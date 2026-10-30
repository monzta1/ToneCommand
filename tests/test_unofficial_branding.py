"""Fork identity/support checks. Never open MIDI, AI or a browser account."""
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import server
from fm9 import diagnostics
from tools import mk1_ai_trial, mk1_tester

ROOT=Path(__file__).resolve().parents[1]
TRACKER='https://github.com/Axelman8/ToneCommand/issues'
PAGES=('ui/index.html','ui/axefx3.html','ui/controllers.html',
       'packaging/mk1-ai/index.html','packaging/mk1/welcome.html')


class Markup(HTMLParser):
    def __init__(self):
        super().__init__();self.assets=[];self.links=[];self.title=False;self.titles=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='title':self.title=True
        if tag in ('img','script','link'):
            self.assets.append(attrs.get('src',attrs.get('href','')))
        if tag=='a':self.links.append(attrs)
    def handle_endtag(self,tag):
        if tag=='title':self.title=False
    def handle_data(self,text):
        if self.title:self.titles.append(text)


@pytest.mark.parametrize('path',PAGES)
def test_every_shipped_entry_has_visible_fork_identity_and_own_support(path):
    source=(ROOT/path).read_text(encoding='utf-8');markup=Markup();markup.feed(source)
    assert 'Unofficial FX3' in ''.join(markup.titles)
    assert 'Unofficial FX3' in source.split('<header',1)[1].split('</header>',1)[0]
    assert not any('logo' in asset.lower() for asset in markup.assets)
    assert 'TONE // COMMAND' not in source and 'TONE <span>//</span> COMMAND' not in source
    links=[link for link in markup.links if link.get('href')==TRACKER]
    assert links and all('noopener' in link.get('rel','') for link in links)


@pytest.mark.parametrize('path',['/','/axefx3','/controllers'])
def test_actual_shared_server_pages_have_fork_branding_without_reaching_device(monkeypatch,path):
    monkeypatch.setattr(server,'get_fm9',lambda:pytest.fail('Branding GET reached MIDI'))
    with TestClient(server.app) as client:
        response=client.get(path)
    assert response.status_code==200
    assert 'Unofficial FX3' in response.text and TRACKER in response.text
    markup=Markup();markup.feed(response.text)
    assert not any('logo' in asset.lower() for asset in markup.assets)


def test_mk1_ai_entry_has_own_identity_without_factory_or_ai_calls():
    app=mk1_ai_trial.create_app(factory=lambda:pytest.fail('Branding opened MK1'),
        ask_ai=lambda *a:pytest.fail('Branding contacted AI'))
    with TestClient(app,base_url='http://127.0.0.1:8909') as client:
        page=client.get('/')
        assert page.status_code==200 and 'Unofficial FX3' in page.text
        assert TRACKER in page.text
        assert client.get('/trial.css').status_code==200
        assert client.get('/logo.png').status_code==404


def test_fork_reports_never_point_to_upstream_issue_queue(monkeypatch,tmp_path):
    assert diagnostics.REPO=='Axelman8/ToneCommand'
    monkeypatch.setattr(diagnostics,'environment',lambda query_device=True:['Unofficial FX3 test'])
    package=diagnostics.package_for_sharing(path=tmp_path/'absent.jsonl')
    assert package['url'].startswith(TRACKER+'/new?')


def test_historical_readonly_entry_keeps_boundary_and_labels_preview(monkeypatch):
    monkeypatch.setattr(server,'_context',server._context)
    with TestClient(mk1_tester.create_app()) as client:
        assert 'Historical read-only evaluation' in client.get('/mk1-test').text
        preview=client.get('/axefx3')
        assert preview.status_code==200 and 'Unofficial FX3' in preview.text
        assert client.post('/api/apply',json={}).status_code==423


def test_old_guides_point_to_single_current_source_without_unlocking_hardware():
    for path in ('docs/MK1-AI-TRIAL.md','docs/MK1-TESTER-GUIDE.md'):
        text=(ROOT/path).read_text(encoding='utf-8')
        assert '**Historical' in text and 'MK1-DEVELOPMENT.md' in text
    assert 'integration/axefx3-upstream-20261009' in (ROOT/'docs/MK1-DEVELOPMENT.md').read_text(encoding='utf-8')
