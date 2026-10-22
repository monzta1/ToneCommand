"""Source interpretation and FX3 review only. No live AI/network or hardware."""
from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from devices.axefx3 import rig_source
from fm9 import describe, planner


def source(roles=('instrument','amp','cab','delay','modulation','reverb')):
    nodes=[dict(id=str(i),role=role,label='Chorus' if role=='modulation' else role,
                provenance='observed') for i,role in enumerate(roles)]
    edges=[dict(id='e'+str(i),**{'from':str(i),'to':str(i+1)},kind='audio',
                provenance='observed') for i in range(len(nodes)-1)]
    return dict(kind='text',title='<img src=x onerror=alert(1)>',url=None,notes=[],
        spec=dict(found=True,summary='A described guitar rig',scenes=[],stated=[],
                  vague=[],quotes=[],rig=dict(schema_version=1,nodes=nodes,edges=edges,unknowns=[])))


def test_shared_extractor_accepts_injected_reader_and_preserves_default(monkeypatch):
    raw=source()['spec']
    reader=Mock(return_value=json.dumps(raw))
    default=Mock(return_value=json.dumps(raw));monkeypatch.setattr(describe,'_ask',default)
    assert describe.extract('Explained rig',ask=reader)['rig']['nodes']
    default.assert_not_called();reader.assert_called_once()
    describe.extract('Explained rig');default.assert_called_once()


@pytest.mark.parametrize('backend',['codex','openai','api','grok','cli'])
def test_source_reader_respects_single_selected_provider(monkeypatch,backend):
    monkeypatch.setenv('PLANNER_BACKEND',backend)
    runner=Mock(return_value=(source()['spec'],'test-model'))
    monkeypatch.setitem(planner._RUNNERS,backend,runner)
    # The shared extraction default must never silently force Claude here.
    monkeypatch.setattr(planner,'find_claude_cli',Mock(side_effect=AssertionError('Claude fallback')))
    result=json.loads(rig_source._reader('Extraction task and untrusted source'))
    assert result['reader']==dict(backend=backend,model='test-model')
    runner.assert_called_once()
    assert 'untrusted' in runner.call_args.args[3]
    assert runner.call_args.args[5] is rig_source.SOURCE_SCHEMA


@pytest.mark.parametrize('raw',[{}, {'found':1}, {'found':True,'summary':[]},
    dict(found=True,summary='test',rig={'schema_version':1,'nodes':[{'id':'a','role':'invalid'}]})])
def test_invalid_reader_reply_refused(monkeypatch,raw):
    monkeypatch.setenv('PLANNER_BACKEND','codex')
    monkeypatch.setitem(planner._RUNNERS,'codex',lambda *args:(raw,'test'))
    with pytest.raises(RuntimeError):rig_source._reader('source')


def test_unpinned_provider_rejected_before_any_call(monkeypatch):
    monkeypatch.delenv('PLANNER_BACKEND',raising=False)
    with pytest.raises(ValueError,match='explicit'):rig_source._reader('source')


def test_youtube_only_source_normalized_and_shared_reader_reused(monkeypatch):
    read=Mock(return_value=dict(text='transcript',kind='youtube',title='Rig',url='public',notes=[]))
    monkeypatch.setattr(describe,'read_source',read)
    extract=Mock(return_value=source()['spec']);monkeypatch.setattr(describe,'extract',extract)
    result=rig_source.read('Bouw deze rig https://youtu.be/Plwb_gfmSc4?t=20')
    read.assert_called_once_with('https://www.youtube.com/watch?v=Plwb_gfmSc4')
    assert extract.call_args.kwargs['ask'] is rig_source._reader
    assert result['kind']=='youtube'


@pytest.mark.parametrize('link',['http://youtu.be/Plwb_gfmSc4',
    'https://localhost/watch?v=Plwb_gfmSc4','https://127.0.0.1/test',
    'https://youtu.be.evil.test/Plwb_gfmSc4','https://u:p@youtu.be/Plwb_gfmSc4',
    'https://youtu.be:444/Plwb_gfmSc4','https://youtu.be/invalid',
    'https://youtu.be/Plwb_gfmSc4 https://youtu.be/abcdefghijk'])
def test_unsafe_or_ambiguous_links_rejected_before_fetch(monkeypatch,link):
    fetch=Mock();monkeypatch.setattr(describe,'read_source',fetch)
    with pytest.raises(ValueError):rig_source.read(link)
    fetch.assert_not_called()


@pytest.mark.parametrize('spec',[dict(found=False),dict(found=True,rig=None),dict(found=True,rig={'nodes':[]})])
def test_music_or_no_graph_never_fabricates_original_gear(monkeypatch,spec):
    monkeypatch.setattr(describe,'read_source',lambda x:dict(text=x))
    monkeypatch.setattr(describe,'extract',lambda *a,**k:spec)
    with pytest.raises(ValueError):rig_source.read('Music reference with no explained equipment')


def test_nam_translation_preserves_all_source_ids_and_provenance():
    s=source(('instrument','wah','drive','amp','cab','delay','rack_fx','modulation','reverb'))
    compiled=rig_source.compile_source(s,nam_mode=True)
    assert len(compiled['status']['nodes'])==9
    assert len(compiled['status']['edges'])==8
    assert compiled['status']['nodes']['3']['family']=='NAM'
    for i in ('1','2','6'):
        assert compiled['status']['nodes'][i]['state']=='not_reproduced'
    assert compiled['status']['nodes']['6']['family'] is None
    assert compiled['status']['nodes']['7']['family']=='CHORUS'
    assert all(n['provenance']=='observed' for n in compiled['status']['nodes'].values())
    assert 'not a claim' in rig_source.brief(s,compiled).lower()


@pytest.mark.parametrize('label',['Phase 90','Flanger','Tremolo','Unknown rack modulation'])
def test_modulation_is_not_silently_called_chorus(label):
    s=source(('instrument','amp','modulation'))
    s['spec']['rig']['nodes'][2]['label']=label
    compiled=rig_source.compile_source(s,nam_mode=True)
    assert compiled['status']['nodes']['2']['state']=='not_reproduced'


def test_simplified_omits_pedals_explicitly():
    c=rig_source.compile_source(source(('instrument','drive','amp','cab')),nam_mode=False,mode='simplified')
    assert c['status']['nodes']['1']['state']=='not_reproduced'
    assert c['warnings']


@pytest.mark.parametrize('kind',['audio_stereo','send_return','expression','control'])
def test_faithful_refuses_unreproduced_connections(kind):
    s=source();s['spec']['rig']['edges'][1]['kind']=kind
    with pytest.raises(ValueError):rig_source.compile_source(s,nam_mode=True,mode='faithful')


def test_faithful_rejects_missing_effect_and_source_order_difference():
    c=rig_source.compile_source(source(),nam_mode=True,mode='faithful')
    p=dict(required_route=['Input 1','NAM 1','Cab 1','Delay 1','Chorus 1','Reverb 1','Output 1'],
        actions=[dict(kind='set_bypass',block=f,bypassed=False) for f in ('NAM','CABINET','DELAY','CHORUS','REVERB')])
    assert not rig_source.report(c,p)['design_omissions']
    p['required_route'][3:5]=['Chorus 1','Delay 1']
    with pytest.raises(ValueError,match='order'):rig_source.report(c,p)
    p['required_route'][3:5]=['Delay 1','Chorus 1'];p['actions'].pop()
    with pytest.raises(ValueError,match='not realize'):rig_source.report(c,p)


def test_cycle_and_excessive_branching_fail_bounded():
    s=source();s['spec']['rig']['edges'].append(dict(id='loop',**{'from':'5','to':'0'},kind='audio'))
    with pytest.raises(ValueError,match='Cyclic'):rig_source.compile_source(s,nam_mode=True)
    s=source(tuple('amp' for _ in range(20)))
    for i in range(18):
        s['spec']['rig']['edges'].append(dict(id='b'+str(i),**{'from':str(i),'to':str(i+2)},kind='audio'))
    with pytest.raises(ValueError,match='alternatives'):rig_source.compile_source(s,nam_mode=True)


def test_closest_exposes_reordered_delay_and_all_omissions():
    c=rig_source.compile_source(source(('instrument','delay','amp','cab','wah')),nam_mode=True)
    assert any('reorders' in w for w in c['warnings'])
    report=rig_source.report(c,dict(required_route=['Input 1','NAM 1','Cab 1','Delay 1','Output 1'],actions=[]))
    assert 'DELAY: not engaged by this design.' in report['design_omissions']
    assert report['verification'].startswith('Interpretation')
