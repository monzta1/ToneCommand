"""Metadata-only export checks preserve meaningful leading/trailing spaces."""
import json

import pytest
from tools import axefx3_name_list as names


def fixture(chassis='mk2'):
    slots=[dict(number=n,name=f'Tone {n}') for n in range(names.COUNTS[chassis])]
    slots[156]['name']=' Leading tone'
    slots[357]['name']='Trailing tone '
    text='\r\n'.join(f"{s['number']:04d}  \t{s['name']}" for s in slots)+'\r\n'
    return text,slots


@pytest.mark.parametrize('chassis', ['mk1','mk2','turbo'])
def test_complete_lists_compare_without_changing_names(chassis):
    text,slots=fixture(chassis)
    result=names.compare(text,{'slots':slots},chassis)
    assert result['equal'] and result['matched']==names.COUNTS[chassis]
    assert result['upper_matched']==(0 if chassis=='mk1' else 512)
    assert not result['midi_opened'] and not result['write_permissions_changed']
    assert names.editor_names('\ufeff'+text,chassis)[156]==' Leading tone'
    assert names.editor_names(text,chassis)[357]=='Trailing tone '


def test_space_only_difference_is_reported_not_normalized_or_leaked():
    text,slots=fixture()
    slots[156]['name']=slots[156]['name'].lstrip()
    result=names.compare(text,slots,'mk2')
    assert result['mismatch_slots']==[156] and result['matched']==1023
    assert result['outer_space_only_slots']==[156] and result['equal'] is False
    assert 'Leading tone' not in json.dumps(result)


@pytest.mark.parametrize('fault',['separator','missing','duplicate','out_of_range','extra_blank','long_name'])
def test_bad_editor_exports_are_not_repaired_or_partially_accepted(fault):
    text,_=fixture()
    rows=text.splitlines()
    if fault=='separator':rows[0]=rows[0].replace('  \t','   ')
    elif fault=='missing':rows.pop()
    elif fault=='duplicate':rows[-1]=rows[0]
    elif fault=='out_of_range':rows[-1]='1024  \tOther'
    elif fault=='extra_blank':rows.insert(1,'')
    elif fault=='long_name':rows[0]='0000  \t'+'x'*32
    with pytest.raises(ValueError):names.editor_names('\n'.join(rows),'mk2')


@pytest.mark.parametrize('fault',['missing','duplicate','bool_number','unknown','non_string','long_name'])
def test_invalid_tc_exports_refuse(fault):
    _,slots=fixture()
    if fault=='missing':slots.pop()
    elif fault=='duplicate':slots[-1]=slots[0]
    elif fault=='bool_number':slots[0]['number']=True
    elif fault=='unknown':slots[0]['number']=1024
    elif fault=='non_string':slots[0]['name']=None
    elif fault=='long_name':slots[0]['name']='x'*32
    with pytest.raises(ValueError):names.native_names(slots,'mk2')


def test_unknown_chassis_and_ambiguous_json_do_not_get_a_default():
    with pytest.raises(ValueError):names.editor_names('','guess')
    with pytest.raises(ValueError):json.loads('{"slots":[],"slots":[]}',object_pairs_hook=names._unique)


def test_cli_needs_only_explicit_metadata_files(tmp_path,capsys):
    text,slots=fixture('mk1')
    editor,native=tmp_path/'editor.txt',tmp_path/'tc.json'
    editor.write_text(text,encoding='utf-8',newline='');native.write_text(json.dumps({'slots':slots}),encoding='utf-8')
    assert names.main(['--editor-export',str(editor),'--tc-export',str(native),'--chassis','mk1'])==0
    assert json.loads(capsys.readouterr().out)['count']==512
