import numpy as np
from tools.stamina_supply_evaluation import replay,measure
from bot.ocr import RapidOcrEngine

def test_acquired_stamina_payment_and_quantity_with_negative_guards():
    image=replay();engine=RapidOcrEngine()
    assert measure(image,engine)==dict(panel=True,payment=[140471,200],quantity=[1,20])
    assert measure(image//3,engine)==dict(panel=False)
    assert measure(np.zeros_like(image),engine)==dict(panel=False)
