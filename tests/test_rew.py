import base64
import copy

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from conftest import owner_client
from helixtune.api import create_app
from helixtune.engine import Engine
from helixtune.rew import RewClient, RewError

UID = 'ba2da346-0f31-4d9d-bbeb-2bfcd07e1cb9'


def encoded(values):
    return base64.b64encode(np.asarray(values, dtype='>f4').tobytes()).decode()


@pytest.fixture
def rew():
    state = {'rows': [{'uuid': UID, 'title': 'Imported response', 'notes':'source notes', 'date':'2014-May-05 14:12:40'}],
             'data': {'unit':'SPL', 'smoothing':'1/6', 'startFreq':20, 'ppo':1, 'magnitude':encoded([70,71,72]),
                      'phase':encoded([1,2,3])}, 'requests': []}
    def reply(req):
        state['requests'].append(req)
        assert req.method == 'GET' and req.url.host == '127.0.0.1'
        if req.url.path == '/doc.json':
            return httpx.Response(200,json={'info':{'version':'fixture'},'paths':{'/measurements':{},'/measurements/{id}/frequency-response':{}}})
        if req.url.path == '/measurements': return httpx.Response(200,json=state['rows'])
        if req.url.path == f'/measurements/{UID}/frequency-response': return httpx.Response(200,json=state['data'])
        return httpx.Response(404)
    state['transport'] = httpx.MockTransport(reply)
    state['client'] = RewClient(transport=state['transport'])
    return state


def test_decodes_documented_big_endian_array_and_log_frequency_axis(rew):
    preview, arrays = rew['client'].capture(UID)
    assert arrays == {'freqs':[20,40,80], 'spl':[70,71,72], 'phase':[1,2,3]}
    assert preview['has_phase'] and preview['points'] == 3
    assert preview['summary']['date'] == '2014-May-05 14:12:40'
    assert all(req.method == 'GET' for req in rew['requests'])


def test_linear_frequency_axis_drops_dc_and_preserves_matching_phase(rew):
    rew['data'].update(startFreq=0, ppo=0, freqStep=10)
    _, arrays = rew['client'].capture(UID)
    assert arrays == {'freqs':[10,20], 'spl':[71,72], 'phase':[2,3]}


def test_handles_index_keyed_list_but_never_uses_numeric_index_for_capture(rew):
    rew['rows'] = {'1':rew['rows'][0]}
    rew['client'].capture(UID)
    assert all('/measurements/1/' not in str(req.url) for req in rew['requests'])


def test_duplicate_uuid_is_visible_and_refused(rew):
    rew['rows'].append(copy.deepcopy(rew['rows'][0]))
    assert all(row['ambiguous'] for row in rew['client'].discover()['measurements'])
    with pytest.raises(RewError, match='duplicated'): rew['client'].capture(UID)


@pytest.mark.parametrize('changes', [
    {'magnitude':'not base64'}, {'magnitude': encoded([70,float('nan'),72])},
    {'phase':encoded([1])}, {'startFreq':-1}, {'ppo':0},
    {'ppo':1, 'freqStep':10}, {'unit':'dBFS'}, {'magnitude':encoded([400,400,400])},
])
def test_refuses_bad_or_unsupported_frequency_data(rew, changes):
    rew['data'].update(changes)
    with pytest.raises(RewError): rew['client'].capture(UID)


def test_malformed_uuid_and_port_refused_before_network(rew):
    for uid in ['1', '../../application/command', 'http://example.com']:
        with pytest.raises(RewError): rew['client'].capture(uid)
    for port in [1,65536]:
        with pytest.raises(RewError): RewClient(port)
    assert not rew['requests']


def test_does_not_follow_redirects_or_treat_other_service_as_rew():
    for response in [httpx.Response(302,headers={'Location':'http://external.example/'}),
                     httpx.Response(200,json={'not':'REW'})]:
        requests=[]
        def reply(req): requests.append(req); return response
        with pytest.raises(RewError): RewClient(transport=httpx.MockTransport(reply)).discover()
        assert len(requests)==1


def test_connection_failure_has_actionable_message():
    def reply(req): raise httpx.ConnectError('no server',request=req)
    with pytest.raises(RewError,match='Start its local API'):
        RewClient(transport=httpx.MockTransport(reply)).discover()


@pytest.fixture
def api(tmp_path, synthetic_mapping, rew):
    engine=Engine(mapping=synthetic_mapping,data_dir=tmp_path)
    app=create_app(engine)
    app.state.rew_factory=lambda port: RewClient(port,transport=rew['transport'])
    return engine,app,owner_client(app)


def test_import_is_reviewed_local_copy_with_unknown_hardware_and_no_inferred_tune(api,rew):
    engine,_,owner=api
    preview=owner.get(f'/api/rew/measurements/{UID}').json()
    body={'uuid':UID,'expected_fingerprint':preview['fingerprint'],'channels':['A'],'seat':'driver'}
    result=owner.post('/api/rew/import',json=body)
    assert result.status_code==200 and result.json()['created']
    m=engine.measurements.get(result.json()['id'])
    assert m.tune is None and m.drivers is None and m.taken_at==0
    assert m.import_provenance['summary']['date']=='2014-May-05 14:12:40'
    assert m.phase==[1,2,3] and m.channels==['A']
    assert engine.measurement_status(m)[0]=='unknown'
    assert owner.post('/api/rew/import',json=body).json()=={'id':m.id,'created':False}
    assert len(engine.measurements.list())==1
    assert all(req.method=='GET' for req in rew['requests'])


def test_source_changed_after_preview_refuses_import_without_creating_data(api,rew):
    engine,_,owner=api
    preview=owner.get(f'/api/rew/measurements/{UID}').json()
    rew['data']['magnitude']=encoded([75,76,77])
    result=owner.post('/api/rew/import',json={'uuid':UID,'expected_fingerprint':preview['fingerprint']})
    assert result.status_code==409 and not engine.measurements.list()


def test_import_only_binds_explicitly_selected_baseline_scene(api):
    engine,_,owner=api
    engine.save_snapshot('Known capture tune')
    preview=owner.get(f'/api/rew/measurements/{UID}').json()
    result=owner.post('/api/rew/import',json={'uuid':UID,'expected_fingerprint':preview['fingerprint'],
        'tune_snapshot':'Known capture tune','channels':['B']})
    m=engine.measurements.get(result.json()['id'])
    assert m.tune==engine.snapshot_tune('Known capture tune') and m.drivers is None


def test_anonymous_and_agent_cannot_probe_rew_even_on_get(api,rew):
    _,app,_=api
    agent=TestClient(app,headers={'Authorization':'Bearer '+app.state.access.token('agent')})
    for path in ['/api/rew',f'/api/rew/measurements/{UID}']:
        assert TestClient(app).get(path).status_code==401
        assert agent.get(path).status_code==403
    assert agent.post('/api/rew/import',json={'uuid':UID,'expected_fingerprint':'none'}).status_code==403
    assert not rew['requests']


def test_source_summary_changes_during_read_are_refused(rew):
    original = rew['transport']
    def changing(request):
        response = original.handle_request(request)
        if request.url.path.endswith('/frequency-response'):
            rew['rows'][0]['title'] = 'Changed during read'
        return response
    client = RewClient(transport=httpx.MockTransport(changing))
    with pytest.raises(RewError, match='changed while reading'):
        client.capture(UID)
