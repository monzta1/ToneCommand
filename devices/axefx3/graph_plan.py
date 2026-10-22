"""Read-only free-chain contract and difference report, no execution endpoint.

Human coordinates are one-based. Proposed topology is checked independently
of wire encoding. A valid graph, operation list or fingerprint is not a write
permit, a supported firmware capability or proof of safe physical loudness.
"""
from fm9.protocol import GridCell, BlockStatus
from . import topology
from .controller_review import digest
from .route_guard import GuardError, labels


def position(value):
    if (not isinstance(value,list) or len(value)!=2
            or any(type(v) is not int for v in value)
            or value[0] not in range(1,7) or value[1] not in range(1,15)):
        raise GuardError('Graph position must be [row1..6, column1..14].')
    return value[0]-1,value[1]-1


def desired(spec,reg):
    """Explicit nodes and adjacent forward cables, never infer a missing route."""
    if not isinstance(spec,dict) or set(spec)!={'cells','connections'}:
        raise GuardError('Graph requires explicit cells and connections only.')
    nodes,connections=spec['cells'],spec['connections']
    if (not isinstance(nodes,list) or not 2<=len(nodes)<=84
            or not isinstance(connections,list) or not 1<=len(connections)<=468):
        raise GuardError('Graph size invalid or connections missing.')
    cells={};blocks=[]
    for node in nodes:
        if not isinstance(node,dict):raise GuardError('Graph cell must be an object.')
        if 'shunt' in node:
            if set(node)!={'position','shunt'} or node['shunt'] is not True:
                raise GuardError('Shunt cannot also contain a block or arbitrary fields.')
            eid=None
        else:
            if (set(node)!={'position','block','instance'} or not isinstance(node['block'],str)
                    or type(node['instance']) is not int or node['instance'] not in range(1,5)):
                raise GuardError('Block cell requires position, block and integer instance.')
            try:
                _,eid=reg.resolve_block(node['block'],node['instance'])
            except (ValueError,KeyError) as exc:
                raise GuardError('Unknown graph block or instance.') from exc
            blocks.append(BlockStatus(eid,False,0,4))
        pos=position(node['position'])
        if pos in cells:raise GuardError('Two cells occupy the same position.')
        cells[pos]=GridCell(*pos,eid,eid is None,0)
    edges=set()
    for cable in connections:
        if not isinstance(cable,dict) or set(cable)!={'source','target'}:
            raise GuardError('Cable requires explicit source and target only.')
        src,dst=position(cable['source']),position(cable['target'])
        if src not in cells or dst not in cells or dst[1]!=src[1]+1 or (src,dst) in edges:
            raise GuardError('Cable must be unique, forward-adjacent and connect two existing cells.')
        edges.add((src,dst));cells[dst].cable_in_mask|=1<<(src[0]+1)
    return topology.inspect(list(cells.values()),blocks,reg)


def review(state,spec,reg):
    """Bind a proposed graph to complete existing state without contacting MIDI.

    Moves remain moves: never replace them with delete/recreate, which could
    reset voicing, channels, modifiers or other scenes. Cable rewiring around
    a replaced node is reported even when its coordinates remain unchanged.
    The report has no token and cannot be passed to the existing SEND executor.
    Operations describe differences, not a safe transmission order.
    """
    required={'preset','scene','firmware','grid','blocks','bulk','modifiers','scene_names'}
    if not isinstance(state,dict) or not required<=set(state):
        raise GuardError('Complete device snapshot required, not a block list.')
    if (not isinstance(state['preset'],(tuple,list)) or len(state['preset'])!=2
            or type(state['preset'][0]) is not int or state['preset'][0] not in range(512)
            or type(state['scene']) is not int or state['scene'] not in range(1,9)
            or state['firmware']!=reg.firmware):
        raise GuardError('Snapshot identity is invalid or mismatches the registry.')
    old=topology.inspect(state['grid'],state['blocks'],reg)
    new=desired(spec,reg)
    ids={eid for eid,_ in old['nodes'].values() if eid is not None}
    if (not isinstance(state['bulk'],dict) or set(state['bulk'])!=ids
            or any(not isinstance(w,list) or not w for w in state['bulk'].values())
            or not isinstance(state['modifiers'],list) or len(state['modifiers'])!=32
            or any(not isinstance(e,dict) or not isinstance(e.get('words'),list)
                   or len(e['words'])!=25 for e in state['modifiers'])
            or not isinstance(state['scene_names'],list) or len(state['scene_names'])!=8
            or any(not isinstance(n,(tuple,list)) or len(n)!=2
                   or type(n[0]) is not int or n[0]!=i or not isinstance(n[1],str)
                   for i,n in enumerate(state['scene_names'],1))):
        raise GuardError('Complete block bulks,32 modifier records and8 scene names required.')
    before={eid:pos for pos,(eid,_) in old['nodes'].items() if eid is not None}
    after={eid:pos for pos,(eid,_) in new['nodes'].items() if eid is not None}
    operations=[]
    def human(pos):return [pos[0]+1,pos[1]+1]
    def block(kind,eid,**fields):
        operations.append(dict(kind=kind,block=labels([eid],reg)[0],effect_id=eid,**fields))
    for eid in sorted(before.keys()-after.keys()):block('remove_block',eid,position=human(before[eid]))
    for eid in sorted(before.keys()&after.keys()):
        if before[eid]!=after[eid]:
            block('move_block',eid,source=human(before[eid]),target=human(after[eid]),preserve_full_state=True)
    for eid in sorted(after.keys()-before.keys()):block('add_block',eid,position=human(after[eid]))
    shunts=lambda graph:{pos for pos,(eid,_) in graph['nodes'].items() if eid is None}
    for kind,positions in [('remove_shunt',shunts(old)-shunts(new)),('add_shunt',shunts(new)-shunts(old))]:
        operations.extend(dict(kind=kind,position=human(pos)) for pos in sorted(positions))
    changed={pos for pos in old['nodes'].keys()|new['nodes'].keys()
             if pos not in old['nodes'] or pos not in new['nodes']
             or old['nodes'][pos][0]!=new['nodes'][pos][0]}
    old_edges,new_edges=set(old['edges']),set(new['edges'])
    rewire={edge for edge in old_edges&new_edges if changed.intersection(edge)}
    for kind,edges in [('disconnect',old_edges-new_edges|rewire),('connect',new_edges-old_edges|rewire)]:
        operations.extend(dict(kind=kind,source=human(src),target=human(dst)) for src,dst in sorted(edges))
    affected={eid for eid in before if eid not in after or before[eid]!=after[eid]}
    bindings=[e.get('slot') for e in state['modifiers'] if e.get('effect_id') in affected]
    return dict(preset=state['preset'][0],scene=state['scene'],firmware=state['firmware'],
        state_fingerprint=digest(state),operations=operations,parallel=new['parallel'],
        affected_modifier_slots=bindings,hardware_writes_supported=False,
        physical_volume_verified=False,stored=False,
        warning='Planning only. Wire support, modifier ownership, scene/channel preservation, '
                'quiet staging, execution ordering and a separate state-bound SEND review are still required.')
