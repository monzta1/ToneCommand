"""A normal reviewed timing operation may set NONE only, never BPM/divisions."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from devices.axefx3 import tempo_control as tempo,album_build,album_planning,executor,fw33_profile,protocol,tone_review
from devices.axefx3.adapter import AxeFxIII
from test_axefx3_album_build import device,design


@pytest.fixture(autouse=True)
def candidate(monkeypatch):
    monkeypatch.setattr(fw33_profile,'TEMPO_NONE_RELEASED',True)
    monkeypatch.setattr(tempo.time,'sleep',lambda _:None)


def fixture(monkeypatch):
    d=device(monkeypatch);d._test_bulk[78][0]=3
    d._test_bulk[78][3]=d._test_bulk[70][9]=14
    d.read_display_text=lambda e,p:tempo.labels()[d._test_bulk[e][p]] if (e,p) in ((78,3),(70,9)) else 'NONE'
    old_write=d._write.side_effect;old_param=d.set_param_display.side_effect
    def write(frame):
        if getattr(d,'_fw33_tempo_permit',None)!=tuple(frame):return old_write(frame)
        d._approved_frame=tuple(frame)
        try:AxeFxIII._send(d,frame)
        finally:d._approved_frame=None
        eid=frame[8]|frame[9]<<7;pid=frame[10]|frame[11]<<7
        d._test_bulk[eid][pid]=0
    def param(spec,value):
        if spec.tempo_param_id is not None:
            problem=AxeFxIII._prepare_delay_milliseconds(d,spec,0)
            if problem:raise ValueError(problem)
        return old_param(spec,value)
    d._write.side_effect=write;d.set_param_display.side_effect=param
    return d


def test_complete_normal_send_transitions_both_enums_once_with_full_proof(monkeypatch):
    d=fixture(monkeypatch);plan=album_planning.compile_design(d.reg,design(),list(album_planning.serial_build.ROUTE),8)
    executor.prepare(d,plan['actions'],plan['required_route'],322)
    d._write.assert_not_called()
    result=executor.execute(d,plan['actions'],plan['required_route'],expected_preset=322,external_audio_muted=True)
    assert result['ok'],result
    assert d._test_bulk[78][3]==d._test_bulk[70][9]==0
    assert len(result['album_verification']['scene_fingerprints'])==8
    frames=[call.args[0] for call in d._write.call_args_list]
    for family in ('DELAY','CHORUS'):
        spec=d.reg.find_param(family,tempo.DOMAINS[family][4])
        assert frames.count(tempo.frame(spec))==1
    d.store_preset.assert_not_called()


@pytest.mark.parametrize('fault',['unreleased','model','label','enum','channel','bool'])
def test_unready_timing_refused_during_read_only_preflight(monkeypatch,fault):
    d=fixture(monkeypatch);spec=d.reg.find_param('CHORUS','CHORUS_RATE')
    if fault=='unreleased':monkeypatch.setattr(fw33_profile,'TEMPO_NONE_RELEASED',False)
    if fault=='model':d._test_bulk[78][0]=0
    if fault=='label':d.read_display_text=lambda *args:'not a verified enum'
    if fault=='enum':d._test_bulk[78][3]=79;d.read_display_text=lambda *args:'1/4'
    if fault=='channel':d.get_channel=lambda eid:1
    if fault=='bool':d._test_bulk[78][3]=False;d.read_display_text=lambda *args:'NONE'
    with pytest.raises(ValueError):tempo.preflight(d,spec)
    d._write.assert_not_called()


def test_none_already_set_needs_no_active_operation_or_write(monkeypatch):
    d=fixture(monkeypatch);d._test_bulk[78][3]=0
    monkeypatch.setattr(fw33_profile,'TEMPO_NONE_RELEASED',False)
    tempo.ensure(d,d.reg.find_param('CHORUS','CHORUS_RATE'))
    d._write.assert_not_called()


def test_real_setter_verifies_none_before_parsing_synced_numeric_display(monkeypatch):
    d=fixture(monkeypatch);p=album_planning.compile_design(d.reg,design(),list(album_planning.serial_build.ROUTE),8)
    resolved=[executor.resolve(d.reg,a) for a in p['actions']]
    item=next(i for i in resolved if i.spec and i.spec.name=='DELAY_TIME');spec=item.spec
    state={'time':350.};old_display=d.get_param_display;old_write=d._write.side_effect
    def display(current):
        if current!=spec:return old_display(current)
        return None if d._test_bulk[70][9]!=0 else state['time']
    def write(sent):
        if getattr(d,'_fw33_tempo_permit',None)==tuple(sent):return old_write(sent)
        assert sent==protocol.set_parameter(d.reg,spec,item.value)
        state['time']=item.value
        d._test_bulk[70][spec.param_id]=round(album_build.shared.display_to_normalized(item.value,spec.dmin,spec.dmax,spec.scale)*65534)
    d.get_param_display=display;d._write.side_effect=write
    d._set_domain_guard=lambda *args:None
    d._prepare_delay_milliseconds=lambda s,c:AxeFxIII._prepare_delay_milliseconds(d,s,c)
    with album_build.execution(d,resolved,True) as session:
        session.item=item
        result=AxeFxIII.set_param_display(d,spec,item.value)
        assert result.ok and result.display_before==350. and result.display_after==item.value
        assert [call.args[0] for call in d._write.call_args_list]==[tempo.frame(spec),protocol.set_parameter(d.reg,spec,item.value)]
    d.store_preset.assert_not_called()


def test_outside_exact_timing_operation_refuses_both_ensure_and_frame(monkeypatch):
    d=fixture(monkeypatch);spec=d.reg.find_param('CHORUS','CHORUS_RATE');frame=tempo.frame(spec)
    with pytest.raises(PermissionError):tempo.ensure(d,spec)
    d._approved_frame=d._fw33_tempo_permit=tuple(frame)
    assert not tempo.allowed(d,frame)
    with pytest.raises((ValueError,PermissionError,KeyError)):AxeFxIII._send(d,frame)
    d._approved_frame=d._fw33_tempo_permit=None
    d._write.assert_not_called()


@pytest.mark.parametrize('fault',['drop','other_field','write_exception'])
def test_unknown_result_consumes_session_without_retry_or_baseline_adoption(monkeypatch,fault):
    d=fixture(monkeypatch);p=album_planning.compile_design(d.reg,design(),list(album_planning.serial_build.ROUTE),8)
    resolved=[executor.resolve(d.reg,a) for a in p['actions']]
    item=next(i for i in resolved if i.spec and i.spec.name=='CHORUS_RATE')
    original=d._write.side_effect
    def bad(frame):
        if fault=='write_exception':raise ValueError('Ambiguous transport result')
        if fault=='other_field':original(frame);d._test_bulk[70][30]+=1
    d._write.side_effect=bad
    with album_build.execution(d,resolved,True) as session:
        session.item=item;before=deepcopy(session.expected)
        with pytest.raises(ValueError):tempo.ensure(d,item.spec)
        assert session.failed and session.expected==before and d._write.call_count==1
        with pytest.raises(PermissionError):tempo.session_for(d,item.spec)
    assert d._fw33_tempo_permit is None
    d.store_preset.assert_not_called()


def test_enum_metadata_is_complete_but_no_public_division_action_exists(monkeypatch):
    d=fixture(monkeypatch)
    assert len(tempo.labels())==79 and tempo.labels()[14]=='1/4'
    with pytest.raises(ValueError):executor.resolve(d.reg,dict(kind='set_param',block='DELAY',instance=1,param='DELAY_TEMPO',value=14))
    d._write.assert_not_called()
