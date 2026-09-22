from tools.craft_evaluation import evaluate


def test_curated_craft_semantic_slice_is_green():
    total, wrong = evaluate()

    assert total == 13
    assert wrong == 0
