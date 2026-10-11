import json
from src.geosiap_storage import import_summary, list_evidences, get_evidence, sanitize

def summary():
    return {
        'platform':'GeoSIAP', 'municipality':'Japeri/RJ', 'entity_id':10,
        'year_requested':2025, 'source_sha256':'a'*64,
        'processed_at_utc':'2026-10-11T15:25:24+00:00', 'criterion':'4.1',
        'assessment_status':'evidencia_parcial','record_count':1454,
        'monetary_missing_counts':{'vl_pago_per':163},
        'assessment_reason':'Evidência técnica parcial',
        'nome_razao':'DADO QUE NÃO DEVE SER PERSISTIDO'
    }

def test_import_idempotent_and_read(tmp_path):
    db = tmp_path/'test.db'
    source = tmp_path/'summary.json'
    source.write_text(json.dumps(summary()),encoding='utf-8')
    evidence_id, created = import_summary(source,db)
    assert created
    same_id, created = import_summary(source,db)
    assert not created and evidence_id == same_id
    assert len(list_evidences(db)) == 1
    item = get_evidence(evidence_id,db)
    assert item['record_count'] == 1454
    assert 'nome_razao' not in item
    assert get_evidence(999,db) is None

def test_reject_unknown_status():
    x = summary()
    x['assessment_status'] = 'atende'
    try:
        sanitize(x)
    except ValueError:
        pass
    else:
        raise AssertionError('Status não permitido foi aceito')
