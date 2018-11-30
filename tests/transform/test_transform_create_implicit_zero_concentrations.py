""" Test creation of implicit zero concentrations in a model

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Author: Jonathan Karr <jonrkarr@gmail.com>
:Date: 2018-11-29
:Copyright: 2017-2018, Karr Lab
:License: MIT
"""

from wc_lang import Model, Species
from wc_lang.transform.create_implicit_zero_concentrations import CreateImplicitZeroConcentrationsTransform
import unittest


class CreateImplicitZeroConcentrationsTransformTestCase(unittest.TestCase):
    def test(self):
        model = Model()
        c_1 = model.compartments.create(id='c_1')
        c_2 = model.compartments.create(id='c_2')
        st_1 = model.species_types.create(id='st_1')
        st_2 = model.species_types.create(id='st_2')
        st_1_c_1 = model.species.create(id=Species.gen_id('st_1', 'c_1'), species_type=st_1, compartment=c_1)
        st_1_c_2 = model.species.create(id=Species.gen_id('st_1', 'c_2'), species_type=st_1, compartment=c_2)
        st_2_c_1 = model.species.create(id=Species.gen_id('st_2', 'c_1'), species_type=st_2, compartment=c_1)
        st_2_c_2 = model.species.create(id=Species.gen_id('st_2', 'c_2'), species_type=st_2, compartment=c_2)
        model.concentrations.create(species=st_1_c_1, mean=1., std=2.)
        model.concentrations.create(species=st_2_c_2, mean=1., std=2.)

        transform = CreateImplicitZeroConcentrationsTransform()
        transform.run(model)

        self.assertEqual(len(model.concentrations), 4)
        self.assertEqual(st_1_c_1.concentration.mean, 1.)
        self.assertEqual(st_1_c_2.concentration.mean, 0.)
        self.assertEqual(st_2_c_1.concentration.mean, 0.)
        self.assertEqual(st_2_c_2.concentration.mean, 1.)
        self.assertEqual(st_1_c_1.concentration.std, 2.)
        self.assertEqual(st_1_c_2.concentration.std, 0.)
        self.assertEqual(st_2_c_1.concentration.std, 0.)
        self.assertEqual(st_2_c_2.concentration.std, 2.)