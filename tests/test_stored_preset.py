"""Read-only stored-memory protocol, bounded parsing and durable backups, no hardware."""
import hashlib
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import owner_client
from helixtune import stored_preset
from helixtune.api import create_app
from helixtune.cli import main
from helixtune.emulator import default_identify_payload
from helixtune.engine import Engine
from helixtune.protocol import commands, frame
from helixtune.protocol.client import Client, WritesDisabled

XML = b'<ATF Dev="15" V="synthetic"><OC ON="0" CN="13" MT="1" /></ATF>'


def blob(xml=XML): return len(xml).to_bytes(4,'big') + zlib.compress(xml)


class StoredTransport:
    """Independent fake implementing captured replies, not an EmulatedDevice subclass."""
    def __init__(self, content=None):
        self.memory = bytearray(b'\xff' * 65536)
        self.memory[:18] = b'Synthetic preset\x00\x00'
        content = blob() if content is None else content
        self.memory[18:18+len(content)] = content
        self.log = []; self.out = bytearray(); self.names = 0; self.change_on_second = False
        self.closed = False
    def reset_input_buffer(self): self.out.clear()
    def write(self, raw):
        request,_ = frame.decode_tx(raw); p = request.payload; self.log.append(p)
        if p == b'\x08': reply = default_identify_payload()
        else:
            assert commands.is_safe_read(p) and p[:2] == b'\x32\x03', 'unexpected state-changing command'
            address = int.from_bytes(p[2:4],'big'); count = p[4]
            if address == 0:
                self.names += 1
                if self.change_on_second and self.names == 2: self.memory[0] ^= 1
            reply = p[:5] + self.memory[address:address+count] + (b'' if address==0 and count==18 else b'\x00')
        self.out.extend(frame.encode_rx(reply)); return len(raw)
    def read(self, count):
        data = bytes(self.out[:min(count,17)]); del self.out[:len(data)]; return data
    def close(self): self.closed = True
    def __enter__(self): return self
    def __exit__(self,*args): self.close()


def test_backup_is_exact_blob_and_xml_with_two_matching_reads():
    transport = StoredTransport()
    result = stored_preset.read(Client(transport))
    assert result.blob == blob() and result.xml == XML
    assert result.sha256 == hashlib.sha256(blob()).hexdigest()
    assert transport.names == 2 and all(commands.is_safe_read(p) for p in transport.log)
    assert not any(p[0] in (9,10,3,4,5) for p in transport.log)


@pytest.mark.parametrize('payload', [b'\x32', b'\x32\x01\x06\x00', b'\x32\x07\x00',
    b'\x32\x03\x00\x00\x00', b'\x32\x03\x00\x00\x81', b'\x32\x03\xff\xff\x02',
    b'\x32\x03\x00\x00\x12\x00', b'\x09\x01', b'\x0a\x03',b'\x0f',b'\x13'])
def test_allowlist_does_not_enable_other_subcommands_or_malformed_reads(payload):
    transport = StoredTransport()
    with pytest.raises(WritesDisabled): Client(transport,allow_writes=True).transact(payload)
    assert transport.log == []


def test_exact_read_encoding_and_bounded_address():
    assert commands.read_stored(0x1234,128) == bytes.fromhex('32 03 12 34 80') + bytes(129)
    assert commands.read_stored(0,18) == bytes.fromhex('32 03 00 00 12') + bytes(18)
    request=commands.read_stored(18,128)
    assert commands.is_safe_read(request)
    assert not commands.is_safe_read(request[:-1]+b'\x01')
    assert not commands.is_safe_read(request+b'\x00')
    for address,count in [(65536,1),(-1,1),(65535,2),(0,0),(0,129)]:
        with pytest.raises(ValueError): commands.read_stored(address,count)


@pytest.mark.parametrize('part', ['address','length','channel','truncated','trailer'])
def test_mismatched_reply_is_refused(part):
    class BadReply(StoredTransport):
        def write(self,raw):
            size = super().write(raw); response,_ = frame.decode_rx(bytes(self.out)); p=bytearray(response.payload)
            if part=='address': p[3] ^= 1
            if part=='length': p[4] -= 1
            if part=='truncated': p.pop()
            if part=='trailer': p[-1]=1
            self.out = bytearray(frame.encode_rx(bytes(p),channel=2 if part=='channel' else 1)); return size
    with pytest.raises(frame.FrameError): Client(BadReply()).read_stored(18,128) if part=='trailer' else Client(BadReply()).read_stored(0,18)


@pytest.mark.parametrize('content', [b'\x00'*4, (stored_preset.MAX_XML+1).to_bytes(4,'big'),
    b'\x00\x00\x00\x05bad zlib', (2).to_bytes(4,'big')+zlib.compress(XML),
    (len(XML)+1).to_bytes(4,'big')+zlib.compress(XML), blob(b'<bad>'),
    blob(b'<ATF Dev="16"/>'),blob(b'<!DOCTYPE ATF><ATF Dev="15"/>'),
    blob('<!DOCTYPE ATF><ATF Dev="15"/>'.encode('utf-16'))])
def test_invalid_or_oversized_payload_never_becomes_a_backup(content):
    with pytest.raises(stored_preset.StoredPresetError): stored_preset.read(Client(StoredTransport(content)))


def test_missing_zlib_end_stops_at_memory_bound():
    # Valid zlib header, followed only by nonfinal empty DEFLATE blocks. It
    # consumes the entire memory region without producing output or reaching EOF.
    size=65536-18
    content=(1).to_bytes(4,'big')+b'\x78\x01'+(b'\x00\x00\x00\xff\xff' * 14000)
    transport=StoredTransport(content[:size])
    with pytest.raises(stored_preset.StoredPresetError,match='no complete compressed stream'):
        stored_preset.read(Client(transport))
    assert len(transport.log) < 520


def test_changed_source_and_expired_deadline_refused():
    transport = StoredTransport(); transport.change_on_second = True
    with pytest.raises(stored_preset.StoredPresetError,match='changed'): stored_preset.read(Client(transport))
    transport = StoredTransport()
    with pytest.raises(stored_preset.StoredPresetError,match='time limit'): stored_preset.read(Client(transport),timeout=0)
    assert not transport.log


def test_backup_file_is_exclusive_complete_and_private(tmp_path):
    result=stored_preset.read(Client(StoredTransport())); path=tmp_path/'stored.afpx'
    stored_preset.save(path,result)
    assert path.read_bytes()==blob() and path.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError): stored_preset.save(path,result)
    assert path.read_bytes()==blob() and not list(tmp_path.glob('*.tmp'))


def test_owner_backup_download_and_separate_scene_import_never_adopts_tune(tmp_path,synthetic_mapping):
    engine=Engine(mapping=synthetic_mapping,data_dir=tmp_path); transport=StoredTransport()
    engine.attach(Client(transport),'serial','test-only')
    app=create_app(engine); before=engine.tune.model_dump(); transport.log.clear()
    with owner_client(app) as owner:
        result=owner.post('/api/device/stored-preset/backup')
        assert result.status_code==200
        record=result.json(); assert record['stored_only'] and record['bytes']==len(blob())
        bid=record['id']
        assert owner.get(f'/api/backups/stored/{bid}').content==blob()
        assert not engine.list_snapshots()
        imported=owner.post(f'/api/backups/stored/{bid}/import',json={'name':'Stored backup review'})
        assert imported.status_code==200 and imported.json()['snapshot']=='Stored backup review'
        assert owner.post(f'/api/backups/stored/{bid}/import',json={'name':'Stored backup review'}).status_code==409
        assert engine.tune.model_dump()==before and not engine.history and not engine.device.baselined
        count=len(transport.log)
        with TestClient(app,headers={'Authorization':f'Bearer {app.state.access.token("agent")}'}) as agent:
            assert agent.post('/api/device/stored-preset/backup').status_code==403
            assert agent.get(f'/api/backups/stored/{bid}').status_code==403
            assert agent.post(f'/api/backups/stored/{bid}/import',json={'name':'Agent'}).status_code==403
        assert len(transport.log)==count


def test_cli_explicit_read_only_backup_without_any_auto_connection(tmp_path,monkeypatch):
    import serial
    transport=StoredTransport(); settings={}
    def serial_open(*args,**kwargs): settings.update(kwargs); settings['args']=args; return transport
    monkeypatch.setattr(serial,'Serial',serial_open)
    target=tmp_path/'stored.afpx'
    assert main(['backup-stored','--port','test-only','--output',str(target)])==0
    assert settings['args']==('test-only',19200)
    assert settings['rtscts'] is False and settings['xonxoff'] is False
    assert target.read_bytes()==blob() and transport.closed
    count=len(transport.log)
    assert main(['backup-stored','--port','test-only','--output',str(target)])==2
    assert len(transport.log)==count


def test_private_capture_stored_xml_replay_if_available(monkeypatch):
    import importlib.util,sys
    root=Path(__file__).resolve().parents[1]
    tool=root.parent/'win11-capture/tools/usbpcap_decode.py'
    expected=root/'captures/usb/device-2022-BasicTune-DRV.afpx'
    files=list((root/'captures/usb').glob('18-reconnect-verify*.pcap'))
    if not tool.exists() or not expected.exists() or not files: pytest.skip('private capture tooling/data absent')
    spec=importlib.util.spec_from_file_location('private_usb_replay',tool)
    decoder=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,spec.name,decoder);spec.loader.exec_module(decoder)
    memory={}
    for path in files:
        report=decoder.decode(path)
        for kind,response in decoder.split_frames(bytes(report.rx),frame.decode_rx):
            if kind!='frame' or response.payload[:2]!=b'\x32\x03': continue
            p=response.payload; start=int.from_bytes(p[2:4],'big')
            for i,value in enumerate(p[5:5+p[4]]): memory[start+i]=value
    if 18 not in memory: pytest.skip('stored memory not found in private capture')
    transport=StoredTransport()
    for address,value in memory.items(): transport.memory[address]=value
    result=stored_preset.read(Client(transport))
    assert result.xml==zlib.decompress(expected.read_bytes()[4:])
    checked=0
    for path in files:
        report=decoder.decode(path)
        captured_requests=[f.payload for kind,f in decoder.split_frames(bytes(report.tx),frame.decode_tx)
                           if kind=='frame' and f.payload[:2]==b'\x32\x03']
        for request in captured_requests:
            generated=commands.read_stored(int.from_bytes(request[2:4],'big'),request[4])
            assert generated[:5]==request[:5] and len(generated)==len(request)
        for kind,response in decoder.split_frames(bytes(report.rx),frame.decode_rx):
            if kind!='frame' or response.payload[:2]!=b'\x32\x03': continue
            captured=response
            class CapturedReply(StoredTransport):
                def write(self,raw):
                    request,_=frame.decode_tx(raw)
                    assert commands.is_safe_read(request.payload)
                    self.out=bytearray(frame.encode_rx(captured.payload,channel=captured.channel))
                    return len(raw)
            p=captured.payload
            data=Client(CapturedReply()).read_stored(int.from_bytes(p[2:4],'big'),p[4])
            assert data==p[5:5+p[4]]
            checked+=1
    assert checked>0


def test_failed_read_creates_no_backup_and_never_tries_a_session_or_baud_fallback(tmp_path,synthetic_mapping):
    class SilentStored(StoredTransport):
        def write(self,raw):
            request,_=frame.decode_tx(raw)
            if request.payload[:2]==b'\x32\x03':
                self.log.append(request.payload);return len(raw)
            return super().write(raw)
    transport=SilentStored();engine=Engine(mapping=synthetic_mapping,data_dir=tmp_path)
    engine.attach(Client(transport,timeout=.001),'serial','test-only');transport.log.clear()
    before=engine.tune.model_dump()
    with owner_client(create_app(engine)) as owner:
        response=owner.post('/api/device/stored-preset/backup')
        assert response.status_code==400 and 'No session or baud-switch fallback' in response.json()['detail']
    assert transport.log==[bytes.fromhex('32 03 00 00 12') + bytes(18)]
    assert not (tmp_path/'backups').exists() and engine.tune.model_dump()==before


def test_failed_backup_save_is_reported_without_adopting_the_stored_tune(tmp_path,synthetic_mapping,monkeypatch):
    engine=Engine(mapping=synthetic_mapping,data_dir=tmp_path)
    engine.attach(Client(StoredTransport()),'serial','test-only')
    before=engine.tune.model_dump()
    def fail_save(*args): raise OSError('storage unavailable')
    monkeypatch.setattr(stored_preset,'save',fail_save)
    with owner_client(create_app(engine)) as owner:
        response=owner.post('/api/device/stored-preset/backup')
        assert response.status_code==400 and 'Could not confirm' in response.json()['detail']
    assert engine.tune.model_dump()==before and not engine.history
