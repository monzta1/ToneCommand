"""Read-only Gen-3 editor metadata, never a model SET permission.

Record grammar adapted from mcp-midi-control (Apache-2.0), commit
59047175cfc4f23e092931b54a7c54f2bffde3ea, parse-effectdefinitions-cache.ts,
via the owner's strict inventory tool. See THIRD_PARTY_NOTICES.md.
Only amplifier names escape the parser; private IR tables are discarded.
"""
import math
import struct

MAX_BYTES=16*1024*1024


class CacheError(ValueError):
    pass


class Reader:
    def __init__(self,data):
        self.data,self.pos=data,46

    def take(self,fmt):
        size=struct.calcsize('<'+fmt)
        if self.pos+size>len(self.data):raise CacheError('Truncated editor metadata')
        values=struct.unpack_from('<'+fmt,self.data,self.pos);self.pos+=size
        return values[0] if len(values)==1 else values

    def labels(self):
        count=self.take('I')
        if not 1<=count<=4096:raise CacheError('Invalid enum count')
        result=[]
        for _ in range(count):
            size=self.take('I')
            if not 1<=size<=64 or self.pos+size>len(self.data):raise CacheError('Invalid label size')
            raw=self.data[self.pos:self.pos+size];self.pos+=size
            if any(c<32 or c>126 for c in raw):raise CacheError('Invalid enum label')
            result.append(raw.decode('ascii'))
        return result


def amp_names(data):
    """Consume declared records to EOF, with no scan/resync or executable input."""
    if not 46<len(data)<=MAX_BYTES:raise CacheError('Invalid editor metadata size')
    if (not 1<=struct.unpack_from('<I',data)[0]<=65535
            or data[4:42]!=bytes(4)+struct.pack('<I',4)+bytes(30)):
        raise CacheError('Unknown Gen-3 metadata header')
    reader=Reader(data);sections=set();models=None
    while reader.pos<len(data):
        tag,count=reader.take('II')
        if not 1<=tag<=64 or tag in sections or not 1<=count<=8192:
            raise CacheError('Invalid or duplicate metadata section')
        sections.add(tag);seen=set()
        for _ in range(count):
            pid,code,pad,lo,hi,extra,step=reader.take('HHHffff')
            if pad or pid in seen or not all(math.isfinite(v) for v in (lo,hi,extra,step)):
                raise CacheError('Invalid metadata record')
            seen.add(pid);tail=reader.pos
            try:labels=reader.labels()
            except CacheError:
                reader.pos=tail
                first,flags,padding=reader.take('IIH')
                if first or padding or pid>=0xfff0:raise CacheError('Invalid numeric metadata')
                if tag==10 and pid==0:raise CacheError('Missing amplifier enum')
            else:
                if 0xfff0<=pid<0xffff:
                    if reader.take('H'):raise CacheError('Invalid table padding')
                    size=reader.take('I')
                    if size>8192:raise CacheError('Oversize metadata table')
                    for _ in range(size):reader.take('I')
                else:
                    flags,padding=reader.take('IH')
                    if padding:raise CacheError('Invalid enum padding')
                    if tag==10 and pid==0:
                        if lo!=0 or hi!=len(labels)-1 or len(set(labels))!=len(labels):
                            raise CacheError('Invalid amplifier ordinal inventory')
                        models=dict(enumerate(labels))
    if len(sections)!=struct.unpack_from('<I',data,42)[0] or not models:
        raise CacheError('Incomplete Gen-3 amplifier metadata')
    return models
