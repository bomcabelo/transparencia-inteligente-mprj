from src.scoring import compute


def r(cid, status):
    return {"criterion_id": cid, "status": status}


def test_weighted_score_excludes_na_and_inconclusive():
    # 4.1 essencial (3) atende; 4.5 obrigatória (2) não atende; 18.1 recomendada (1) inconclusivo
    s = compute([r("4.1", "atende"), r("4.5", "nao_atende"), r("18.1", "inconclusivo"),
                 r("19.5", "nao_aplicavel"), r("7.1", "nao_avaliado")])
    assert s["score"] == 60.0                     # 3 / (3+2)
    assert s["score_intervalo"] == [50.0, 66.7]   # inconclusivo como 0 e como 1
    assert s["cobertura_avaliacao"] == round(5 / 6, 3)
    assert s["media_simples"] == 50.0             # média aritmética ignora a relevância


def test_essential_gap_caps_classification():
    full = [r("4.1", "atende"), r("4.5", "atende"), r("3.1", "atende")]
    assert compute(full)["classificacao"] == "Elevado"
    gap = [r("4.1", "parcial")] + [r(c, "atende") for c in ("4.5", "3.5", "4.6", "4.7", "2.4", "2.5", "2.6",
                                                            "2.9", "16.1", "16.2", "16.3", "15.4", "1.1", "1.2")]
    s = compute(gap)
    assert s["score"] >= 85 and s["classificacao"] == "Intermediário"
    assert s["essenciais_pendentes"] == ["4.1"]


def test_no_conclusive_results_means_no_score():
    s = compute([r("4.1", "inconclusivo")])
    assert s["score"] is None and s["classificacao"] == "Sem avaliação conclusiva" and not s["comparavel"]


def test_low_coverage_publishes_interval_but_no_point_score():
    rows = [r("1.1", "atende")] + [r(c, "inconclusivo") for c in ("1.2", "1.3", "4.1", "3.1", "12.1", "2.4")]
    s = compute(rows)
    assert s["score"] is None and s["classificacao"] == "Cobertura insuficiente"
    assert s["score_intervalo"][0] < s["score_intervalo"][1] and not s["comparavel"]
