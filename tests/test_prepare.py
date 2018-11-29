""" Test WC model preparation for simulation

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Author: Jonathan Karr <jonrkarr@gmail.com>
:Date: 2018-11-29
:Copyright: 2017-2018, Karr Lab
:License: MIT
"""
from wc_lang import prepare
import os
import unittest
import wc_lang.io


class PrepareModelTransformTestCase(unittest.TestCase):
    def test_run(self):
        filename = os.path.join(os.path.dirname(__file__), 'fixtures', 'example-model.xlsx')
        model = wc_lang.io.Reader().run(filename)
        transform = prepare.PrepareModelTransform()
        transform.run(model)
