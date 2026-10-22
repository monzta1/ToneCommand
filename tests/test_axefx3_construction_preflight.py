"""Future mixer/Drive checks during empty construction do not permit SETs."""
import pytest
from devices.axefx3 import serial_build as serial,album_planning,fw33,protocol
from test_axefx3_serial_build import fake
from test_axefx3_album_build import design


def expanded(reg):
    raw=design()
    for album in raw['albums']:
        album['cab']=album_planning.cab_voice(album['cab']).model_dump()
    return album_planning.compile_design(reg,raw,[],8)


def test_empty_album_with_expanded_mixer_builds_before_active_album_session():
    d=fake();d.get_channel=lambda eid:d._test_blocks[eid].channel
    plan=expanded(d.reg)
    with serial.execution(d,serial.ROUTE):
        result=serial.build(d,plan['required_route'],plan['actions'])
    assert result.ok and d._write.call_count==41
    assert all(call.args[0][6] in (0x30,0x32,0x35) for call in d._write.call_args_list)
    assert d._serial_session is None


@pytest.mark.parametrize('fault',[None,'session','phase','grid','channel','layout','cab_mode'])
def test_readonly_construction_scope_and_live_frame_guard_remain_independent(fault):
    d=fake();d.get_channel=lambda eid:1 if fault=='channel' else 0
    spec=d.reg.find_param('CABINET','CABINET_MUTE1')
    with serial.execution(d,serial.ROUTE):
        session=d._serial_session;session.index=28
        d._test_cells.update(serial.row_fixture.steps()[27][2]);d._channels[62]=4
        d._test_bulk[62]=[0]*424
        if fault=='session':session.failed=True
        if fault=='phase':session.index=27
        if fault=='grid':d._test_cells.clear()
        if fault=='layout':d._test_bulk[62]=[0]*106
        if fault=='cab_mode':d._test_bulk[62][31]=1
        error=serial.construction_domain_error(d,spec)
        assert bool(error)==bool(fault)
        with pytest.raises(PermissionError):fw33.check_frame(d,protocol.set_parameter(d.reg,spec,0))
    d._write.assert_not_called()
