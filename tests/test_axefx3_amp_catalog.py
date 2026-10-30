"""Facts-only catalog checks; no physical MIDI or selector-write acceptance."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fm9.device import ReadOnly

from devices.axefx3 import amp_catalog as catalog


def resource():
    return json.loads(catalog.files('devices.axefx3').joinpath('data', 'fw33_amp_models.json').read_text(encoding='utf-8'))


def inject(monkeypatch, value):
    f = Mock()
    f.return_value.joinpath.return_value.read_text.return_value = value
    monkeypatch.setattr(catalog, 'files', f)
    return f


def test_complete_ordered_catalog_and_exact_anchors():
    names = catalog.roster(catalog.FIRMWARE)
    assert list(names) == list(range(336)) and len(set(names.values())) == 336
    assert {i:names[i] for i in (0,14,267,335)} == {
        0:'59 Bassguy Bright',14:'Brit 800 2204 High',
        267:'USA JP IIC+ Yellow',335:'Brit JVM Crunch Red'}
    for number, name in names.items():
        assert catalog.ordinal(catalog.FIRMWARE, name) == number
    names[14] = 'Changed by caller'
    assert catalog.roster(catalog.FIRMWARE)[14] == 'Brit 800 2204 High'


@pytest.mark.parametrize('firmware',['33.00','33.00 Beta 2','97.00','32.06','future',None,True,33])
def test_unknown_profile_never_loads_or_guesses_a_catalog(monkeypatch,firmware):
    f = inject(monkeypatch, 'must not read')
    assert catalog.roster(firmware) == {}
    assert catalog.report(firmware)['count'] == 0
    f.assert_not_called()


@pytest.mark.parametrize('name',['unknown','brit 800 2204 high',' Brit 800 2204 High',14,None,True])
def test_only_an_exact_label_resolves(name):
    with pytest.raises(ValueError):catalog.ordinal(catalog.FIRMWARE,name)
    with pytest.raises(ValueError):catalog.ordinal('33.00','Brit 800 2204 High')


@pytest.mark.parametrize('fault',[
    'missing','duplicate_name','renumber','rename','nonstring','empty','long','control',
    'nonascii','whitespace','firmware','model','model_float','selector','selector_bool',
    'cache','source','extra','not_object','models_list'])
def test_malformed_or_changed_data_is_never_a_partial_catalog(monkeypatch,fault):
    data = deepcopy(resource())
    if fault=='missing':del data['models']['4']
    elif fault=='duplicate_name':data['models']['4']=data['models']['5']
    elif fault=='renumber':data['models']['4'],data['models']['5']=data['models']['5'],data['models']['4']
    elif fault=='rename':data['models']['4']='A plausible but unverified name'
    elif fault=='nonstring':data['models']['4']=[]
    elif fault=='empty':data['models']['4']=''
    elif fault=='long':data['models']['4']='x'*121
    elif fault=='control':data['models']['4']='wrong\nname'
    elif fault=='nonascii':data['models']['4']='\u2603'
    elif fault=='whitespace':data['models']['4']=' Double Verb Vibrato'
    elif fault=='firmware':data['firmware']='33.00'
    elif fault=='model':data['model_byte']=18
    elif fault=='model_float':data['model_byte']=16.0
    elif fault=='selector':data['selector_pid']=1
    elif fault=='selector_bool':data['selector_pid']=False
    elif fault=='cache':data['cache_sha256']='0'*64
    elif fault=='source':data['source']='bad\nsource'
    elif fault=='extra':data['selector_frame']=[1,2,3]
    elif fault=='not_object':data=[]
    elif fault=='models_list':data['models']=list(data['models'].values())
    inject(monkeypatch,json.dumps(data))
    with pytest.raises(ValueError):catalog.roster(catalog.FIRMWARE)


@pytest.mark.parametrize('raw',['{','{"models":{},"models":{}}','NaN','Infinity','x'*32769],
                         ids=['malformed','duplicate','nan','infinity','oversized'])
def test_invalid_ambiguous_or_oversized_json_declines(monkeypatch,raw):
    inject(monkeypatch,raw)
    with pytest.raises(ValueError):catalog.roster(catalog.FIRMWARE)


def test_missing_package_resource_is_not_silently_an_empty_roster(monkeypatch):
    f = inject(monkeypatch,'')
    f.return_value.joinpath.return_value.read_text.side_effect=FileNotFoundError('missing data')
    with pytest.raises(FileNotFoundError):catalog.roster(catalog.FIRMWARE)


def test_import_lookup_and_report_open_no_ports_or_enable_writes(monkeypatch):
    from fm9 import midi_transport
    from devices.axefx3.readonly_adapter import ReadOnlyRegistry
    def forbidden(*args,**kwargs):pytest.fail('Catalog opened MIDI')
    monkeypatch.setattr(midi_transport,'open_ports',forbidden)
    importlib.reload(catalog)
    assert catalog.ordinal(catalog.FIRMWARE,'Brit 800 2204 High') == 14
    result=catalog.report(catalog.FIRMWARE)
    assert result['count']==336
    for field in ('live_list_fetched','generic_setter_enabled','hardware_verified_in_this_slice'):
        assert result[field] is False
    reg=ReadOnlyRegistry()
    assert reg.amp_roster=={} and reg.amp_models=={}
    with pytest.raises(ReadOnly,match='read-only'):reg.spec('DISTORT',0)
    assert 'AmpWriter' not in catalog.__dict__


def test_json_is_declared_in_noneditable_package_data():
    import tomllib
    config=tomllib.loads((Path(__file__).resolve().parents[1]/'pyproject.toml').read_text(encoding='utf-8'))
    assert 'data/*.json' in config['tool']['setuptools']['package-data']['devices.axefx3']
