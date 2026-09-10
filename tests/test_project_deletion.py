from tests.test_app import client


def test_batch_delete_preserves_other_projects_and_audit(client):
    import sabc.app as module
    ids=[client.post('/api/projects',json={'name':name}).json()['id'] for name in ['one','two','keep']]
    assert client.post('/api/projects/delete',json={'ids':ids[:2]}).status_code==200
    assert client.get('/api/projects/'+ids[0]).status_code==404
    assert client.get('/api/projects/'+ids[1]).status_code==404
    assert client.get('/api/projects/'+ids[2]).status_code==200
    assert [p['id'] for p in module.store.list('projects')]==ids[2:]
    assert module.store.check_audit()
    assert client.post('/api/projects/delete',json={'ids':ids[:2]}).status_code==200
    assert client.patch('/api/projects/'+ids[0],json={'name':'revive'}).status_code==404


def test_delete_batch_validates_ids_and_cancels_running_jobs(client):
    import sabc.app as module
    ids=[client.post('/api/projects',json={'name':name}).json()['id'] for name in ['one','two']]
    assert client.post('/api/projects/delete',json={'ids':[ids[0],'missing']}).status_code==422
    module.store.save('jobs',{'project_id':ids[1],'status':'running','process_id':module.jobs.process_id})
    assert client.post('/api/projects/delete',json={'ids':ids}).status_code==200
    assert all(client.get('/api/projects/'+pid).status_code==404 for pid in ids)
    assert client.post('/api/projects/delete',json={'ids':[]}).status_code==422


def test_late_writes_cannot_restore_deleted_project(client):
    import sabc.app as module
    import pytest
    p=client.post('/api/projects',json={'name':'delete'}).json()
    assert client.post('/api/projects/delete',json={'ids':[p['id']]}).status_code==200
    with pytest.raises(ValueError,match='已删除'):
        module.store.save('projects',p)
    with pytest.raises(ValueError,match='已删除'):
        module.store.save('evidence',{'project_id':p['id'],'content':'late'})
