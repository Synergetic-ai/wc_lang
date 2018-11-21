""" Tests of core

:Author: Jonathan Karr <karr@mssm.edu>
:Author: Arthur Goldberg, Arthur.Goldberg@mssm.edu
:Date: 2016-11-10
:Copyright: 2016-2018, Karr Lab
:License: MIT
"""

import os
import pytest
import re
import unittest
import warnings
import math
from obj_model.core import InvalidAttribute
import wc_lang
from wc_lang.core import (Model, Taxon, TaxonRank, Submodel,
                          DfbaObjective, DfbaObjectiveExpression,
                          Reaction, SpeciesType, SpeciesTypeType, Species, Compartment,
                          SpeciesCoefficient, Parameter, Reference, ReferenceType,
                          DatabaseReference,
                          RateLaw, RateLawEquation, RateLawEquationAttribute, RateLawDirection,
                          Function, FunctionExpression,
                          Observable, ObservableExpression,
                          StopCondition, StopConditionExpression,
                          SubmodelAlgorithm, Concentration, BiomassComponent, BiomassReaction,
                          ReactionParticipantAttribute, ExpressionMethods,
                          InvalidObject, EXTRACELLULAR_COMPARTMENT_ID)
from wc_lang.prepare import PrepareModel
from wc_lang.io import Reader
from libsbml import (SBMLNamespaces, SBMLDocument, readSBMLFromString)
import libsbml
from wc_lang.sbml.util import (wrap_libsbml, LibSBMLError, init_sbml_model,
                               create_sbml_doc_w_fbc, SBML_LEVEL, SBML_VERSION, get_SBML_compatibility_method)


class TestCore(unittest.TestCase):

    def setUp(self):
        Reaction.objects.reset()
        BiomassReaction.objects.reset()

        self.model = mdl = Model(id='model', name='test model', version='0.0.1', wc_lang_version='0.0.1')

        mdl.taxon = Taxon(id='taxon', name='test taxon', rank=TaxonRank.species)

        self.comp_0 = comp_0 = mdl.compartments.create(id='comp_0', name='compartment 0',
                                                       initial_volume=1.25)
        self.comp_1 = comp_1 = mdl.compartments.create(id='comp_1', name='compartment 1',
                                                       initial_volume=2.5)
        self.compartments = compartments = [comp_0, comp_1]

        self.species_types = species_types = []
        self.species = species = []
        self.concentrations = concentrations = []
        for i in range(8):
            spec_type = mdl.species_types.create(
                id='spec_type_{}'.format(i),
                name='species type {}'.format(i),
                type=SpeciesTypeType.metabolite,
                structure='C' * i + 'H' * (i + 1),
                empirical_formula='C{}H{}'.format(i, i + 1),
                molecular_weight=12 * (i + 1),
                charge=i + 1)
            species_types.append(spec_type)

            if i != 3:
                spec = Species(species_type=spec_type, compartment=comp_0)
            else:
                spec = Species(species_type=spec_type, compartment=comp_1)
            spec.id = spec.gen_id(spec.species_type.id, spec.compartment.id)
            species.append(spec)

            conc = Concentration(id=Concentration.gen_id(spec.id), species=spec, value=3 * i)
            concentrations.append(conc)

        self.biomass_reaction = biomass_reaction = BiomassReaction(
            id='biomass_reaction_1',
            name='biomass reaction',
            comments="Nobody will ever deprive the American people of the right to vote except the "
            "American people themselves")
        BiomassReaction.get_manager().insert_all_new()

        biomass_components = []
        for i in range(2):
            biomass_components.append(
                biomass_reaction.biomass_components.create(
                    id='biomass_comp_{}'.format(i + 1),
                    coefficient=2 * (float(i) - 0.5),  # create a reactant and a product
                    species=species[i]))
        self.biomass_components = biomass_components

        self.submdl_0 = submdl_0 = mdl.submodels.create(
            id='submodel_0', name='submodel 0', algorithm=SubmodelAlgorithm.ssa)
        self.submdl_1 = submdl_1 = mdl.submodels.create(
            id='submodel_1', name='submodel 1', algorithm=SubmodelAlgorithm.ssa)
        self.submdl_2 = submdl_2 = mdl.submodels.create(
            id='submodel_2', name='submodel 2', algorithm=SubmodelAlgorithm.dfba,
            biomass_reactions=[biomass_reaction])
        self.submodels = submodels = [submdl_0, submdl_1, submdl_2]

        self.parameters = parameters = []
        for i in range(3):
            param = mdl.parameters.create(
                id='param_{}'.format(i), name='parameter {}'.format(i),
                value=i * 4, units='dimensionless')
            param.submodels = submodels[i:i + 1]
            parameters.append(param)

        self.rxn_0 = rxn_0 = submdl_0.reactions.create(id='rxn_0', name='reaction 0')
        rxn_0.participants.create(species=species[0], coefficient=-2)
        rxn_0.participants.create(species=species[1], coefficient=-3.5)
        rxn_0.participants.create(species=species[2], coefficient=1)
        equation = RateLawEquation(
            expression='k_cat_0 * {0} / (k_m_0 + {0})'.format(species[5].serialize()),
            modifiers=species[5:6])
        parameters.append(equation.parameters.create(id='k_cat_0', value=2,
                                                     model=mdl))
        parameters.append(equation.parameters.create(id='k_m_0', value=1,
                                                     model=mdl))
        rate_law_0 = rxn_0.rate_laws.create(
            id=RateLaw.gen_id(rxn_0.id, RateLawDirection.forward.name),
            direction=RateLawDirection.forward,
            equation=equation)

        self.rxn_1 = rxn_1 = submdl_1.reactions.create(id='rxn_1', name='reaction 1')
        rxn_1.participants.create(species=species[0], coefficient=-2)
        rxn_1.participants.create(species=species[1], coefficient=-3)
        rxn_1.participants.create(species=species[3], coefficient=2)
        equation = RateLawEquation(
            expression='k_cat_1 * {0} / (k_m_1 + {0})'.format(species[6].serialize()),
            modifiers=species[6:7])
        parameters.append(equation.parameters.create(id='k_cat_1', value=2,
                                                     model=mdl))
        parameters.append(equation.parameters.create(id='k_m_1', value=1,
                                                     model=mdl))
        rate_law_1 = rxn_1.rate_laws.create(
            id=RateLaw.gen_id(rxn_1.id, RateLawDirection.forward.name),
            direction=RateLawDirection.forward,
            equation=equation)

        self.rxn_2 = rxn_2 = submdl_2.reactions.create(id='rxn_2', name='reaction 2')
        rxn_2.participants.create(species=species[0], coefficient=-2)
        rxn_2.participants.create(species=species[1], coefficient=-3)
        rxn_2.participants.create(species=species[4], coefficient=1)
        equation = RateLawEquation(
            expression='{1} * {0} / ({2} + {0})'.format(species[7].serialize(), parameters[0].id, parameters[1].id),
            modifiers=species[7:8],
            parameters=parameters[0:2])
        rate_law_2 = rxn_2.rate_laws.create(
            id=RateLaw.gen_id(rxn_2.id, RateLawDirection.forward.name),
            direction=RateLawDirection.forward,
            equation=equation)

        Reaction.get_manager().insert_all_new()

        self.reactions = [rxn_0, rxn_1, rxn_2]
        self.rate_laws = [rate_law_0, rate_law_1, rate_law_2]

        self.dfba_obj = of = DfbaObjective()
        of.submodel = submdl_2
        of.expression = DfbaObjectiveExpression()
        of.expression.reactions.append(rxn_1)
        of.expression.reactions.append(rxn_2)
        biomass_reaction.dfba_obj_expression = of.expression

        self.references = references = []
        self.database_references = database_references = []
        for i in range(3):
            ref = parameters[i].references.create(
                id='ref_{}'.format(i), name='reference {}'.format(i),
                type=ReferenceType.misc)
            references.append(ref)

            x_ref = ref.database_references.create(database='x', id='y' * (i + 1),
                                                   url='http://x.com/{}'.format('y' * (i + 1)))
            database_references.append(x_ref)

    def test_default_wc_lang_version(self):
        model = Model()
        self.assertEqual(model.wc_lang_version, wc_lang.__version__)

        model = Model(wc_lang_version='xxx')
        self.assertEqual(model.wc_lang_version, 'xxx')

        model = Model(revision='xxx')
        self.assertEqual(model.revision, 'xxx')

    def test_reverse_references(self):
        mdl = self.model

        self.assertEqual(set(mdl.submodels), set(self.submodels))
        self.assertEqual(set(mdl.compartments), set(self.compartments))
        self.assertEqual(set(mdl.species_types), set(self.species_types))
        self.assertEqual(set(mdl.parameters), set(self.parameters))

        # submodel
        for reaction, submodel in zip(self.reactions, self.submodels):
            self.assertEqual(submodel.reactions, [reaction])

        for submodel in self.submodels:
            self.assertEqual(submodel.database_references, [])
            self.assertEqual(submodel.references, [])

        # compartment
        self.assertEqual(set(self.compartments[0].species), set(self.species[0:3] + self.species[4:]))
        self.assertEqual(self.compartments[1].species, self.species[3:4])

        for compartment in self.compartments:
            self.assertEqual(compartment.database_references, [])
            self.assertEqual(compartment.references, [])

        # species type
        for species_type, species in zip(self.species_types, self.species):
            self.assertEqual(species_type.species, [species])

        for species_type in self.species_types:
            self.assertEqual(species_type.database_references, [])
            self.assertEqual(species_type.references, [])

        # specie
        for species_type, species in zip(self.species_types, self.species):
            self.assertEqual(species.species_type, species_type)

        for i in range(len(self.species)):
            if i != 3:
                self.assertEqual(self.species[i].compartment, self.compartments[0])
            else:
                self.assertEqual(self.species[i].compartment, self.compartments[1])

        self.assertEqual(len(self.species[0].species_coefficients), 3)
        self.assertEqual(len(self.species[1].species_coefficients), 3)
        self.assertEqual(len(self.species[2].species_coefficients), 1)
        self.assertEqual(len(self.species[3].species_coefficients), 1)
        self.assertEqual(len(self.species[4].species_coefficients), 1)
        self.assertEqual(len(self.species[5].species_coefficients), 0)
        self.assertEqual(len(self.species[6].species_coefficients), 0)
        self.assertEqual(len(self.species[7].species_coefficients), 0)

        self.assertEqual(len(self.species[0].rate_law_equations), 0)
        self.assertEqual(len(self.species[1].rate_law_equations), 0)
        self.assertEqual(len(self.species[2].rate_law_equations), 0)
        self.assertEqual(len(self.species[3].rate_law_equations), 0)
        self.assertEqual(len(self.species[4].rate_law_equations), 0)
        self.assertEqual(len(self.species[5].rate_law_equations), 1)
        self.assertEqual(len(self.species[6].rate_law_equations), 1)
        self.assertEqual(len(self.species[7].rate_law_equations), 1)

        # reaction
        for reaction, submodel in zip(self.reactions, self.submodels):
            self.assertEqual(reaction.submodel, submodel)

        self.assertEqual(set(x.species for x in self.reactions[0].participants),
                         set([self.species[0], self.species[1], self.species[2]]))
        self.assertEqual(set(x.species for x in self.reactions[1].participants),
                         set([self.species[0], self.species[1], self.species[3]]))
        self.assertEqual(set(x.species for x in self.reactions[2].participants),
                         set([self.species[0], self.species[1], self.species[4]]))

        self.assertEqual(self.reactions[0].rate_laws[0].equation.modifiers, self.species[5:6])
        self.assertEqual(self.reactions[1].rate_laws[0].equation.modifiers, self.species[6:7])
        self.assertEqual(self.reactions[2].rate_laws[0].equation.modifiers, self.species[7:8])

        for reaction in self.reactions:
            self.assertEqual(reaction.database_references, [])
            self.assertEqual(reaction.references, [])
            self.assertEqual(len(reaction.rate_laws), 1)

        # biomass components
        for i in range(len(self.biomass_components)):
            # submodels
            self.assertEqual(self.biomass_components[i].biomass_reaction, self.biomass_reaction)
            # self.assertEqual(self.biomass_reaction.submodels[0], self.submodels[2])
            # species types
            self.assertEqual(self.biomass_components[i].species, self.species[i])
            self.assertEqual(self.biomass_components[i], self.species[i].biomass_components[0])

        # parameters
        for reference, parameter in zip(self.references, self.parameters):
            self.assertEqual(parameter.references, [reference])

        for parameter in self.parameters:
            self.assertEqual(parameter.model, mdl)

        # references
        for reference, parameter in zip(self.references, self.parameters):
            self.assertEqual(reference.parameters, [parameter])
            self.assertEqual(parameter.references, [reference])

        for reference, database_reference in zip(self.references, self.database_references):
            self.assertEqual(reference.database_references, [database_reference])
            self.assertEqual(database_reference.reference, reference)

        # reaction participant
        for species in self.species[0:5]:
            self.assertEqual(set(x.species for x in species.species_coefficients), set([species]))

        for reaction in self.reactions:
            for part in reaction.participants:
                self.assertIn(reaction, part.reactions)
            self.assertEqual(set(x.reaction for x in reaction.rate_laws), set([reaction]))

        # database references
        for reference, database_reference in zip(self.references, self.database_references):
            self.assertEqual(reference.database_references, [database_reference])
            self.assertEqual(database_reference.reference, reference)

    def test_taxon_rank_class(self):
        self.assertEqual(TaxonRank['class'], TaxonRank['classis'])
        self.assertEqual(TaxonRank.__getattr__('class'), TaxonRank['classis'])

    def test_model_get_species(self):
        self.assertEqual(set(self.model.get_species()), set(self.species))

    def test_submodel_get_species(self):
        species = self.species
        self.assertEqual(set(self.submdl_0.get_species()), set([
            species[0], species[1], species[2], species[5],
        ]))
        self.assertEqual(set(self.submdl_1.get_species()), set([
            species[0], species[1], species[3], species[6],
        ]))
        self.assertEqual(set(self.submdl_2.get_species()), set([
            species[0], species[1], species[4], species[7],
        ]))

    def test_reaction_get_species(self):
        species = self.species
        self.assertEqual(set(self.rxn_0.get_species()), set([
            species[0], species[1], species[2], species[5],
        ]))
        self.assertEqual(set(self.rxn_1.get_species()), set([
            species[0], species[1], species[3], species[6],
        ]))
        self.assertEqual(set(self.rxn_2.get_species()), set([
            species[0], species[1], species[4], species[7],
        ]))

    def test_get_components(self):
        mdl = self.model

        self.assertEqual(set(mdl.get_compartments()), set(self.compartments))
        self.assertEqual(set(mdl.get_compartments(__type=Compartment)), set(self.compartments))
        self.assertEqual(set(mdl.get_compartments(__type=Submodel)), set())

        self.assertEqual(set(mdl.get_species_types()), set(self.species_types))
        self.assertEqual(set(mdl.get_species_types(__type=SpeciesType)), set(self.species_types))
        self.assertEqual(set(mdl.get_species_types(__type=Compartment)), set())

        self.assertEqual(set(mdl.get_submodels()), set(self.submodels))
        self.assertEqual(set(mdl.get_submodels(__type=Submodel)), set(self.submodels))
        self.assertEqual(set(mdl.get_submodels(__type=SpeciesType)), set())

        self.assertEqual(set(mdl.get_species()), set(self.species))
        self.assertEqual(set(mdl.get_species(__type=Species)), set(self.species))
        self.assertEqual(set(mdl.get_species(__type=Submodel)), set())

        self.assertEqual(set(mdl.get_concentrations()), set(self.concentrations))
        self.assertEqual(set(mdl.get_concentrations(__type=Concentration)), set(self.concentrations))
        self.assertEqual(set(mdl.get_concentrations(__type=Submodel)), set())

        self.assertEqual(set(mdl.get_reactions()), set(self.reactions))
        self.assertEqual(set(mdl.get_reactions(__type=Reaction)), set(self.reactions))
        self.assertEqual(set(mdl.get_reactions(__type=Submodel)), set())

        self.assertEqual(set(mdl.get_rate_laws()), set(self.rate_laws))
        self.assertEqual(set(mdl.get_rate_laws(__type=RateLaw)), set(self.rate_laws))
        self.assertEqual(set(mdl.get_rate_laws(__type=Submodel)), set())

        self.assertEqual(set(mdl.get_parameters()), set(self.parameters))
        self.assertEqual(set(mdl.get_parameters(__type=Parameter)), set(self.parameters))
        self.assertEqual(set(mdl.get_parameters(__type=Submodel)), set())

        self.assertEqual(set(mdl.get_references()), set(self.references))
        self.assertEqual(set(mdl.get_references(__type=Reference)), set(self.references))
        self.assertEqual(set(mdl.get_references(__type=Submodel)), set())

        self.assertNotEqual(set(mdl.get_biomass_reactions(__type=BiomassReaction)), set())
        self.assertEqual(set(mdl.get_biomass_reactions(__type=Reaction)), set())

        self.assertEqual(set(self.dfba_obj.get_products()), set([
            self.species[3],
            self.species[4],
            self.species[1],
        ]))
        self.assertEqual(set(self.dfba_obj.get_products(__type=Species)), set([
            self.species[3],
            self.species[4],
            self.species[1],
        ]))
        self.assertEqual(set(self.dfba_obj.get_products(__type=Reaction)), set())

    def test_get_component(self):
        model = self.model

        self.assertEqual(model.get_component('compartment', 'comp_0'), self.comp_0)
        self.assertEqual(model.get_component('species_type', 'spec_type_1'), self.species_types[1])
        self.assertEqual(model.get_component('submodel', 'submodel_1'), self.submdl_1)
        self.assertEqual(model.get_component('reaction', 'rxn_1'), self.rxn_1)
        self.assertEqual(model.get_component('parameter', 'param_2'), self.parameters[2])
        self.assertEqual(model.get_component('reference', 'ref_1'), self.references[1])
        self.assertEqual(model.get_component('reaction', 'rxn_3'), None)

        with self.assertRaisesRegex(ValueError, ' not one of '):
            model.get_component('undefined', 'rxn_3')

    def test_species_type_is_carbon_containing(self):
        self.assertFalse(self.species_types[0].is_carbon_containing())
        self.assertTrue(self.species_types[1].is_carbon_containing())

    def test_species_gen_id(self):
        self.assertEqual(Species.gen_id(self.species[3].species_type.id, self.species[3].compartment.id),
                         'spec_type_3[comp_1]')

    def test_species_get(self):
        self.assertEqual(Species.get([], self.species), [])
        self.assertEqual(Species.get(['X'], self.species), [None])
        self.assertEqual(Species.get(['spec_type_0[comp_0]'], self.species), [self.species[0]])
        ids = ["spec_type_{}[comp_0]".format(i) for i in range(4, 8)]
        self.assertEqual(Species.get(ids, self.species), self.species[4:])
        ids.append('X')
        self.assertEqual(Species.get(ids, self.species), self.species[4:] + [None])

    def test_concentration_serialize(self):
        self.assertEqual(self.concentrations[0].serialize(), 'conc-spec_type_0[comp_0]')
        self.assertEqual(self.concentrations[1].serialize(), 'conc-spec_type_1[comp_0]')
        self.assertEqual(self.concentrations[2].serialize(), 'conc-spec_type_2[comp_0]')
        self.assertEqual(self.concentrations[3].serialize(), 'conc-spec_type_3[comp_1]')

    def test_reaction_participant_serialize(self):
        self.assertEqual(set([part.serialize() for part in self.rxn_0.participants]), set([
            '(-2) spec_type_0[comp_0]', '(-3.500000e+00) spec_type_1[comp_0]', 'spec_type_2[comp_0]'
        ]))

    def test_reaction_participant_deserialize(self):
        objs = {
            SpeciesType: {
                'spec_0': SpeciesType(id='spec_0'),
                'spec_1': SpeciesType(id='spec_1'),
                'spec_2': SpeciesType(id='spec_2')},
            Compartment: {
                'c_0': Compartment(id='c_0'),
                'c_1': Compartment(id='c_1'),
                'c_2': Compartment(id='c_2')
            },
            Species: {
            },
        }
        objs[Species]['spec_0[c_0]'] = Species(
            id='spec_0[c_0]',
            species_type=objs[SpeciesType]['spec_0'],
            compartment=objs[Compartment]['c_0'])
        objs[Species]['spec_0[c_1]'] = Species(
            id='spec_0[c_1]',
            species_type=objs[SpeciesType]['spec_0'],
            compartment=objs[Compartment]['c_1'])

        val = 'spec_0[c_0]'
        part0, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertEqual(error, None)
        self.assertEqual(part0.coefficient, 1)
        self.assertEqual(part0.species.serialize(), 'spec_0[c_0]')
        self.assertEqual(set(objs[SpeciesCoefficient].values()), set([part0]))
        self.assertEqual(len(objs[Species]), 2)

        val = '(2) spec_0[c_0]'
        part1, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertEqual(error, None)
        self.assertEqual(part1.coefficient, 2)
        self.assertEqual(part1.species.serialize(), 'spec_0[c_0]')
        self.assertEqual(set(objs[SpeciesCoefficient].values()), set([part0, part1]))
        self.assertEqual(len(objs[Species]), 2)

        val = '(2.) spec_0[c_1]'
        part2, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertEqual(error, None)
        self.assertEqual(part2.coefficient, 2)
        self.assertEqual(part2.species.serialize(), 'spec_0[c_1]')
        self.assertEqual(set(objs[SpeciesCoefficient].values()), set([part0, part1, part2]))
        self.assertEqual(len(objs[Species]), 2)

        val = '(2.5) spec_0[c_0]'
        part3, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertEqual(error, None)
        self.assertEqual(part3.coefficient, 2.5)
        self.assertEqual(part3.species.serialize(), 'spec_0[c_0]')
        self.assertEqual(set(objs[SpeciesCoefficient].values()), set([part0, part1, part2, part3]))
        self.assertEqual(len(objs[Species]), 2)

        val = '(.5) spec_0[c_0]'
        part4, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertEqual(error, None)
        self.assertEqual(part4.coefficient, 0.5)
        self.assertEqual(part4.species.serialize(), 'spec_0[c_0]')
        self.assertEqual(set(objs[SpeciesCoefficient].values()), set([part0, part1, part2, part3, part4]))
        self.assertEqual(len(objs[Species]), 2)

        val = '(.5) spec_0[c_0]'
        part4b, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertEqual(part4b, part4)
        self.assertTrue(part4b is part4)

        # negative examples
        val = '(1) spec_1'
        part5, error = SpeciesCoefficient.deserialize(val, objs, compartment=objs[Compartment]['c_0'])
        self.assertNotEqual(error, None)
        self.assertEqual(part5, None)

        val = '(-1) spec_0[c_0]'
        part6, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertNotEqual(error, None)
        self.assertEqual(part6, None)

        val = '(1) spec_0'
        part6, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertNotEqual(error, None)
        self.assertEqual(part6, None)

        val = '(1.1.) spec_0[c_0]'
        part6, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertNotEqual(error, None)
        self.assertEqual(part6, None)

        val = ' spec_0[c_0]'
        part6, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertNotEqual(error, None)
        self.assertEqual(part6, None)

        val = ' spec_3[c_0]'
        part6, error = SpeciesCoefficient.deserialize(val, objs)
        self.assertNotEqual(error, None)
        self.assertEqual(part6, None)

        self.assertEqual(set(objs[SpeciesCoefficient].values()), set([part0, part1, part2, part3, part4]))
        self.assertEqual(len(objs[Species]), 2)

        val = '(1) spec_3'
        part, error = SpeciesCoefficient.deserialize(val, objs, compartment=objs[Compartment]['c_0'])
        self.assertNotEqual(error, None)
        self.assertEqual(part, None)

        val = '(2) spec_0'
        objs[SpeciesCoefficient] = {
            '(2) spec_0[c_0]': SpeciesCoefficient(
                species=Species(id='spec_0[c_0]', species_type=objs[SpeciesType]['spec_0'], compartment=objs[Compartment]['c_0']),
                coefficient=2)
        }
        part, error = SpeciesCoefficient.deserialize(val, objs, compartment=objs[Compartment]['c_0'])
        self.assertEqual(error, None)
        self.assertEqual(part, objs[SpeciesCoefficient]['(2) spec_0[c_0]'])

    def test_rate_gen_id(self):
        self.assertEqual(self.rate_laws[0].id, 'rxn_0-forward')
        self.assertEqual(self.rate_laws[1].id, 'rxn_1-forward')
        self.assertEqual(self.rate_laws[2].id, 'rxn_2-forward')

    def test_rate_law_equation_serialize(self):
        self.assertEqual(self.rate_laws[0].equation.serialize(),
                         'k_cat_0 * {0} / (k_m_0 + {0})'.format(self.species[5].serialize()))
        self.assertEqual(self.rate_laws[1].equation.serialize(),
                         'k_cat_1 * {0} / (k_m_1 + {0})'.format(self.species[6].serialize()))
        self.assertEqual(self.rate_laws[2].equation.serialize(),
                         '{1} * {0} / ({2} + {0})'.format(
            self.species[7].serialize(),
            self.parameters[0].id,
            self.parameters[1].id,
        ))

    def test_rate_law_equation_deserialize(self):
        objs = {
            SpeciesType: {
                'spec_0': SpeciesType(id='spec_0'),
                'spec_1': SpeciesType(id='spec_1'),
                'spec_2': SpeciesType(id='spec_2')},
            Compartment: {
                'c_0': Compartment(id='c_0'),
                'c_1': Compartment(id='c_1'),
                'c_2': Compartment(id='c_2')
            },
            Parameter: {
                'p_1': Parameter(id='p_1'),
                'p_2': Parameter(id='p_2'),
            },
            Species: {
            },
            Parameter: {
                'k_cat': Parameter(id='k_cat', value=1),
                'k_m': Parameter(id='k_m', value=2),
            }
        }
        objs[Species]['spec_0[c_0]'] = Species(id='spec_0[c_0]',
                                               species_type=objs[SpeciesType]['spec_0'],
                                               compartment=objs[Compartment]['c_0'])
        objs[Species]['spec_0[c_1]'] = Species(id='spec_0[c_1]',
                                               species_type=objs[SpeciesType]['spec_0'],
                                               compartment=objs[Compartment]['c_1'])
        objs[Species]['spec_2[c_1]'] = Species(id='spec_2[c_1]',
                                               species_type=objs[SpeciesType]['spec_2'],
                                               compartment=objs[Compartment]['c_1'])
        objs[Species]['spec_1[c_1]'] = Species(id='spec_1[c_1]',
                                               species_type=objs[SpeciesType]['spec_1'],
                                               compartment=objs[Compartment]['c_1'])

        expression = 'spec_0[c_0]'
        equation1, error = RateLawEquation.deserialize(expression, objs)
        self.assertEqual(error, None)
        self.assertEqual(equation1.expression, expression)
        self.assertEqual(equation1.modifiers, [objs[Species]['spec_0[c_0]']])
        self.assertEqual(equation1.parameters, [])
        self.assertEqual(set(objs[RateLawEquation].values()), set([equation1]))

        expression = 'spec_0[c_1] / (spec_2[c_1])'
        equation2, error = RateLawEquation.deserialize(expression, objs)
        self.assertEqual(error, None)
        self.assertEqual(equation2.expression, expression)
        self.assertEqual(set(equation2.modifiers), set([objs[Species]['spec_0[c_1]'], objs[Species]['spec_2[c_1]']]))
        self.assertEqual(equation2.parameters, [])
        self.assertEqual(set(objs[RateLawEquation].values()), set([equation1, equation2]))

        expression = 'spec_0[c_3] / (spec_1[c_1])'
        equation, error = RateLawEquation.deserialize(expression, objs)
        self.assertNotEqual(error, None)
        self.assertEqual(equation, None)
        self.assertEqual(set(objs[RateLawEquation].values()), set([equation1, equation2]))

        expression = 'spec_3[c_0] / (spec_1[c_1])'
        equation, error = RateLawEquation.deserialize(expression, objs)
        self.assertNotEqual(error, None)
        self.assertEqual(equation, None)
        self.assertEqual(set(objs[RateLawEquation].values()), set([equation1, equation2]))

        # exception
        equation3, error = RateLawEquation.deserialize('2', objs)
        self.assertEqual(error, None)
        self.assertEqual(equation3.expression, '2')

        # with parameters
        expression = 'k_cat * spec_0[c_1] / (k_m + spec_2[c_1])'
        equation4, error = RateLawEquation.deserialize(expression, objs)
        self.assertEqual(error, None)
        self.assertEqual(equation4.expression, expression)
        self.assertEqual(set(equation4.modifiers), set([objs[Species]['spec_0[c_1]'], objs[Species]['spec_2[c_1]']]))
        self.assertEqual(set(equation4.parameters), set(objs[Parameter].values()))
        self.assertEqual(set(objs[RateLawEquation].values()), set([equation1, equation2, equation3, equation4]))

        expression = 'p_1 * spec_0[c_1] / (p_2 + spec_2[c_1])'
        equation, error = RateLawEquation.deserialize(expression, objs)
        self.assertNotEqual(error, None)
        self.assertEqual(equation, None)
        self.assertEqual(set(objs[RateLawEquation].values()), set([equation1, equation2, equation3, equation4]))

    def test_rate_law_validate(self):
        species_types = [
            SpeciesType(id='spec_0'),
            SpeciesType(id='spec_1'),
        ]
        compartments = [
            Compartment(id='c_0'),
            Compartment(id='c_1'),
        ]
        parameters = [
            Parameter(id='p_0'),
        ]

        # unknown specie error
        expression = 'spec_x[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ])
        rate_law = RateLaw(
            id='rxn-forward',
            reaction=Reaction(id='rxn'),
            equation=equation,
        )
        self.assertNotEqual(rate_law.equation.validate(), None)

        # unknown parameter error
        expression = 'p_x'
        equation = RateLawEquation(
            expression=expression,
            parameters=[parameters[0]])
        rate_law = RateLaw(
            id='rxn-forward',
            reaction=Reaction(id='rxn'),
            equation=equation,
        )
        self.assertNotEqual(rate_law.equation.validate(), None)

        # Name error
        expression = 'not_k_cat * spec_0[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ])
        rate_law = RateLaw(
            id='rxn-forward',
            reaction=Reaction(id='rxn'),
            equation=equation
        )
        self.assertNotEqual(rate_law.equation.validate(), None)

        # syntax error
        expression = '* spec_0[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ])
        rate_law = RateLaw(
            id='rxn-forward',
            reaction=Reaction(id='rxn'),
            equation=equation
        )
        self.assertNotEqual(rate_law.equation.validate(), None)

        # No error
        expression = 'k_cat * spec_0[c_0]'
        equation, errors = RateLawEquation.deserialize(expression, {
            Species: {
                'spec_0[c_0]': Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0]),
            },
            Parameter: {
                'k_cat': Parameter(id='k_cat', value=1),
            },
        })
        rate_law = RateLaw(
            id='rxn-forward',
            reaction=Reaction(id='rxn'),
            equation=equation,
        )
        error = rate_law.validate()
        self.assertEqual(rate_law.validate(), None, str(error))
        self.assertEqual(rate_law.equation.validate(), None, str(error))

        # No error with parameters
        expression = 'p_0 * spec_0[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ],
            parameters=[
                parameters[0],
            ],)
        rate_law = RateLaw(
            id='rxn-forward',
            reaction=Reaction(id='rxn'),
            equation=equation
        )
        self.assertEqual(rate_law.validate(), None)
        self.assertEqual(rate_law.equation.validate(), None, str(error))

    def test_rate_law_equation_validate(self):
        species_types = [
            SpeciesType(id='spec_0'),
            SpeciesType(id='spec_1'),
            SpeciesType(id='spec_2'),
        ]
        compartments = [
            Compartment(id='c_0'),
            Compartment(id='c_1'),
            Compartment(id='c_2'),
        ]
        parameters = [
            Parameter(id='p_0'),
            Parameter(id='p_1'),
            Parameter(id='k_m'),
        ]

        expression = 'spec_0[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ])
        self.assertEqual(equation.validate(), None)

        expression = 'spec_0[c_0] * spec_1[c_2]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0]),
                Species(id='spec_1[c_2]', species_type=species_types[1], compartment=compartments[2]),
            ])
        self.assertEqual(equation.validate(), None)

        expression = 'spec_0[c_0] * spec_1[c_2]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0]),
                Species(id='spec_1[c_1]', species_type=species_types[1], compartment=compartments[1]),
                Species(id='spec_1[c_2]', species_type=species_types[1], compartment=compartments[2]),
            ])
        self.assertNotEqual(equation.validate(), None)

        expression = 'spec_0[c_0] * spec_1[c_2]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0]),
            ])
        self.assertNotEqual(equation.validate(), None)

        # parameters
        expression = 'p_0 * spec_0[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ],
            parameters=[parameters[0]])
        self.assertEqual(equation.validate(), None)

        expression = 'p_0 * spec_0[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ],
            parameters=[parameters[0], parameters[1]])
        self.assertNotEqual(equation.validate(), None)

        expression = 'p_1 * spec_0[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ],
            parameters=[])
        self.assertNotEqual(equation.validate(), None)

        expression = 'k_m * spec_0[c_0]'
        equation = RateLawEquation(
            expression=expression,
            modifiers=[
                Species(id='spec_0[c_0]', species_type=species_types[0], compartment=compartments[0])
            ],
            parameters=[parameters[2]])
        invalid = equation.validate()
        self.assertEqual(invalid, None, str(invalid))

    def test_rate_law_modifiers(self):
        self.assertEqual(self.rxn_0.rate_laws[0].equation.modifiers, self.species[5:6])
        self.assertEqual(self.rxn_1.rate_laws[0].equation.modifiers, self.species[6:7])
        self.assertEqual(self.rxn_2.rate_laws[0].equation.modifiers, self.species[7:8])

    def test_rate_law_parameters(self):
        self.assertEqual([p.id for p in self.rxn_0.rate_laws[0].equation.parameters], ['k_cat_0', 'k_m_0'])
        self.assertEqual([p.id for p in self.rxn_1.rate_laws[0].equation.parameters], ['k_cat_1', 'k_m_1'])
        self.assertEqual(self.rxn_2.rate_laws[0].equation.parameters, self.parameters[0:2])

    def test_parameter_validate_unique(self):
        self.assertEqual(Parameter.validate_unique(self.parameters), None)

        model = Model()
        params = [
            Parameter(id='a', model=model),
            Parameter(id='b', model=model),
        ]
        self.assertEqual(Parameter.validate_unique(params), None)

        model = Model()
        params = [
            Parameter(id='a', model=model),
            Parameter(id='a', model=model),
        ]
        self.assertNotEqual(Parameter.validate_unique(params), None)

        submodel = Submodel()
        params = [
            Parameter(id='a'),
            Parameter(id='b'),
        ]
        self.assertEqual(Parameter.validate_unique(params), None)

        submodel = Submodel()
        params = [
            Parameter(id='a'),
            Parameter(id='a'),
        ]
        self.assertNotEqual(Parameter.validate_unique(params), None)

        model = Model()
        submodel = Submodel()
        params = [
            Parameter(id='a', model=model),
            Parameter(id='a', model=model),
        ]
        self.assertNotEqual(Parameter.validate_unique(params), None)

        params = [
            Parameter(id='a'),
            Parameter(id='b'),
        ]
        self.assertEqual(Parameter.validate_unique(params), None)

        params = [
            Parameter(id='a', model=model),
            Parameter(id='b', model=model),
        ]
        self.assertEqual(Parameter.validate_unique(params), None)

    def test_database_reference_serialize(self):
        self.assertEqual(self.database_references[0].serialize(), '{}: {}'.format('x', 'y'))
        self.assertEqual(self.database_references[1].serialize(), '{}: {}'.format('x', 'yy'))
        self.assertEqual(self.database_references[2].serialize(), '{}: {}'.format('x', 'yyy'))

    def test_ReactionParticipantAttribute_serialize(self):
        attr = ReactionParticipantAttribute()
        self.assertEqual(attr.serialize(self.rxn_0.participants),
                         '[comp_0]: (2) spec_type_0 + (3.500000e+00) spec_type_1 ==> spec_type_2')
        self.assertEqual(attr.serialize(self.rxn_1.participants),
                         '(2) spec_type_0[comp_0] + (3) spec_type_1[comp_0] ==> (2) spec_type_3[comp_1]')
        self.assertEqual(attr.serialize(None), '')

    def test_ReactionParticipantAttribute_deserialize(self):
        objs = {
            SpeciesType: {
                'spec_0': SpeciesType(id='spec_0'),
                'spec_1': SpeciesType(id='spec_1'),
                'spec_2': SpeciesType(id='spec_2')},
            Compartment: {
                'c_0': Compartment(id='c_0'),
                'c_1': Compartment(id='c_1'),
                'c_2': Compartment(id='c_2')
            },
            Species: {
            },
        }
        objs[Species]['spec_0[c_0]'] = Species(
            species_type=objs[SpeciesType]['spec_0'],
            compartment=objs[Compartment]['c_0'])
        objs[Species]['spec_1[c_0]'] = Species(
            species_type=objs[SpeciesType]['spec_1'],
            compartment=objs[Compartment]['c_0'])
        objs[Species]['spec_2[c_0]'] = Species(
            species_type=objs[SpeciesType]['spec_2'],
            compartment=objs[Compartment]['c_0'])
        objs[Species]['spec_2[c_1]'] = Species(
            species_type=objs[SpeciesType]['spec_2'],
            compartment=objs[Compartment]['c_1'])
        for species in objs[Species].values():
            species.id = species.gen_id(species.species_type.id, species.compartment.id)

        attr = ReactionParticipantAttribute()

        parts1, error = attr.deserialize('[c_0]: (2) spec_0 + (3.5) spec_1 ==> spec_2', objs)
        self.assertEqual(error, None)
        self.assertEqual(set([p.serialize() for p in parts1]), set([
            '(-2) spec_0[c_0]',
            '(-3.500000e+00) spec_1[c_0]',
            'spec_2[c_0]',
        ]))
        self.assertEqual(len(objs[SpeciesCoefficient]), 3)
        self.assertEqual(set(objs[SpeciesCoefficient].values()), set(parts1))
        self.assertEqual(len(objs[Species]), 4)

        parts2, error = attr.deserialize(
            '(2) spec_0[c_0] + (3) spec_1[c_0] ==> (2) spec_2[c_1]', objs)
        self.assertEqual(error, None)
        self.assertEqual(set([p.serialize() for p in parts2]), set(
            ['(-2) spec_0[c_0]', '(-3) spec_1[c_0]', '(2) spec_2[c_1]']))
        self.assertEqual(set([p.serialize() for p in objs[SpeciesCoefficient].values()]),
                         set([p.serialize() for p in parts1 + parts2]))
        self.assertEqual(len(objs[Species]), 4)

        # negative examples
        parts3, error = attr.deserialize(
            '(2) spec_0[c_0] + (3) spec_1[c_0] ==> (2) spec_2[c_3]', objs)
        self.assertNotEqual(error, None)
        self.assertEqual(parts3, None)

        parts3, error = attr.deserialize(
            '(2) spec_0[c_0] + (3) spec_1[c_0] => (2) spec_2[c_1]', objs)
        self.assertNotEqual(error, None)
        self.assertEqual(parts3, None)

        parts3, error = attr.deserialize(
            '(2) spec_0[c_0] + (3) spec_1[c_0] ==> (-2) spec_2[c_1]', objs)
        self.assertNotEqual(error, None)
        self.assertEqual(parts3, None)

        parts3, error = attr.deserialize(
            '[c_0]: (2) spec_0[c_0] + (3) spec_1[c_0] ==> (2) spec_2[c_1]', objs)
        self.assertNotEqual(error, None)
        self.assertEqual(parts3, None)

        parts3, error = attr.deserialize(
            '[c_0]: (2) spec_0 + (3) spec_1 ==> (2) spec_3', objs)
        self.assertNotEqual(error, None)
        self.assertEqual(parts3, None)

        parts, error = attr.deserialize('[c_3]: (2) spec_0 + (3.5) spec_1 ==> spec_2', objs)
        self.assertNotEqual(error, None)
        self.assertEqual(parts, None)

        # empty LHS
        parts, error = attr.deserialize('==> spec_2[c_1]', objs)
        self.assertEqual(error, None)
        self.assertEqual(set([p.serialize() for p in parts]), set(
            ['spec_2[c_1]']))

        parts, error = attr.deserialize('[c_1]: ==> spec_2', objs)
        self.assertEqual(error, None)
        self.assertEqual(set([p.serialize() for p in parts]), set(
            ['spec_2[c_1]']))

        parts, error = attr.deserialize('[c_1]:  ==>spec_2 ', objs)
        self.assertEqual(error, None)
        self.assertEqual(set([p.serialize() for p in parts]), set(
            ['spec_2[c_1]']))

        # empty RHS
        parts, error = attr.deserialize('spec_2[c_1] ==>', objs)
        self.assertEqual(error, None)
        self.assertEqual(set([p.serialize() for p in parts]), set(
            ['(-1) spec_2[c_1]']))

        parts, error = attr.deserialize('[c_1]: spec_2 ==>', objs)
        self.assertEqual(error, None)
        self.assertEqual(set([p.serialize() for p in parts]), set(
            ['(-1) spec_2[c_1]']))

        parts, error = attr.deserialize('[c_1]:spec_2==> ', objs)
        self.assertEqual(error, None)
        self.assertEqual(set([p.serialize() for p in parts]), set(
            ['(-1) spec_2[c_1]']))

        # both empty
        parts, error = attr.deserialize('==>', objs)
        self.assertEqual(error, None)
        self.assertEqual(parts, [])

        parts, error = attr.deserialize('[c_1]: ==>', objs)
        self.assertEqual(error, None)
        self.assertEqual(parts, [])

        parts, error = attr.deserialize('[c_1]:  ==>  ', objs)
        self.assertEqual(error, None)
        self.assertEqual(parts, [])

        parts, error = attr.deserialize('[c_1]:==>', objs)
        self.assertEqual(error, None)
        self.assertEqual(parts, [])

        # repeated species
        objs[Species] = {
            'spec_2[c_1]': Species(id='spec_2[c_1]', species_type=objs[SpeciesType]['spec_2'], compartment=objs[Compartment]['c_1']),
        }
        objs[SpeciesCoefficient] = {
            '(-1) spec_2[c_1]': SpeciesCoefficient(species=objs[Species]['spec_2[c_1]'], coefficient=-1),
            'spec_2[c_1]': SpeciesCoefficient(species=objs[Species]['spec_2[c_1]'], coefficient=1),
        }
        parts, error = attr.deserialize('[c_1]: spec_2 ==> spec_2 + spec_2', objs)
        self.assertNotEqual(error, None)
        self.assertEqual(parts, None)

        parts, error = attr.deserialize('spec_2[c_1] ==> spec_2[c_1] + spec_2[c_1]', objs)
        self.assertNotEqual(error, None)
        self.assertEqual(parts, None)

    def test_ReactionParticipantAttribute_validate(self):
        species_types = [
            SpeciesType(id='A'),
            SpeciesType(id='B'),
        ]
        compartments = [
            Compartment(id='c'),
            Compartment(id='e'),
        ]
        species = [
            Species(id='A[c]', species_type=species_types[0], compartment=compartments[0]),
            Species(id='A[e]', species_type=species_types[0], compartment=compartments[1]),
            Species(id='B[c]', species_type=species_types[1], compartment=compartments[0]),
            Species(id='B[e]', species_type=species_types[1], compartment=compartments[1]),
        ]

        attr = ReactionParticipantAttribute()
        attr.related_class = SpeciesCoefficient

        rxn = Reaction(participants=[
            SpeciesCoefficient(species=species[0], coefficient=-1),
            SpeciesCoefficient(species=species[1], coefficient=1),
        ])
        self.assertEqual(attr.validate(None, rxn.participants), None)

        self.assertNotEqual(attr.validate(None, [
            SpeciesCoefficient(species=species[0], coefficient=-1),
            SpeciesCoefficient(species=species[0], coefficient=1),
        ]), None)

        self.assertNotEqual(attr.validate(None, [
            SpeciesCoefficient(species=species[0], coefficient=-2),
            SpeciesCoefficient(species=species[0], coefficient=1),
            SpeciesCoefficient(species=species[0], coefficient=1),
        ]), None)

        self.assertNotEqual(attr.validate(None, [
            SpeciesCoefficient(species=species[0], coefficient=-2),
            SpeciesCoefficient(species=species[1], coefficient=-1),
            SpeciesCoefficient(species=species[0], coefficient=2),
            SpeciesCoefficient(species=species[1], coefficient=1),
        ]), None)

        self.assertNotEqual(attr.validate(None, []), None)

    def test_RateLawEquationAttribute_serialize(self):
        rxn = self.rxn_0
        rate_law = rxn.rate_laws[0]
        equation = rate_law.equation

        attr = RateLawEquationAttribute()
        self.assertEqual(attr.serialize(equation), equation.expression)

    def test_RateLawEquationAttribute_deserialize(self):
        objs = {
            SpeciesType: {
                'spec_0': SpeciesType(id='spec_0'),
                'spec_1': SpeciesType(id='spec_1'),
                'spec_2': SpeciesType(id='spec_2')},
            Compartment: {
                'c_0': Compartment(id='c_0'),
                'c_1': Compartment(id='c_1'),
                'c_2': Compartment(id='c_2')
            },
            Species: {
            },
            Parameter: {
                'k_cat': Parameter(id='k_cat'),
            }
        }
        objs[Species]['spec_0[c_0]'] = Species(
            id='spec_0[c_0]',
            species_type=objs[SpeciesType]['spec_0'],
            compartment=objs[Compartment]['c_0'])

        expression = 'k_cat * spec_0[c_0]'
        attr = RateLawEquationAttribute()
        equation1, error = attr.deserialize(expression, objs)
        self.assertEqual(error, None)
        self.assertEqual(equation1.expression, expression)
        self.assertEqual(equation1.modifiers, [objs[Species]['spec_0[c_0]']])
        self.assertEqual(equation1.parameters, [objs[Parameter]['k_cat']])
        self.assertEqual(list(objs[RateLawEquation].values()), [equation1])

    def test_dfba_obj_deserialize(self):

        objs = {
            Reaction: {
                'reaction_0': Reaction(id='reaction_0'),
                'reaction_1': Reaction(id='reaction_1'),
                'reaction_2': Reaction(id='reaction_2'),
            },
            BiomassReaction: {
                'biomass_reaction_0': BiomassReaction(id='biomass_reaction_0'),
                'biomass_reaction_1': BiomassReaction(id='biomass_reaction_1'),
            },
        }

        value = None
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(of_expr.expression, '')
        self.assertEqual(of_expr.reactions, [])
        self.assertEqual(of_expr.biomass_reactions, [])
        self.assertEqual(of_expr._analyzed_expr.is_linear, True)
        self.assertEqual(invalid_attribute, None)

        value = ''
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(of_expr.expression, '')
        self.assertEqual(of_expr.reactions, [])
        self.assertEqual(of_expr.biomass_reactions, [])
        self.assertEqual(of_expr._analyzed_expr.is_linear, True)
        self.assertEqual(invalid_attribute, None)

        value = "2*biomass_reaction_1 - reaction_1"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        self.assertEqual(of_expr.reactions, [objs[Reaction]['reaction_1']])
        self.assertEqual(of_expr.biomass_reactions, [objs[BiomassReaction]['biomass_reaction_1']])
        self.assertEqual(of_expr._analyzed_expr.is_linear, True)

        value = "2*biomass_reaction_1 - pow( reaction_1, 1)"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        self.assertEqual(of_expr.reactions, [objs[Reaction]['reaction_1']])
        self.assertEqual(of_expr.biomass_reactions, [objs[BiomassReaction]['biomass_reaction_1']])
        self.assertEqual(of_expr._analyzed_expr.is_linear, False)

        value = "2*biomass_reaction_1 - pow( reaction_1, 2)"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        self.assertEqual(of_expr.reactions, [objs[Reaction]['reaction_1']])
        self.assertEqual(of_expr.biomass_reactions, [objs[BiomassReaction]['biomass_reaction_1']])
        self.assertEqual(of_expr._analyzed_expr.is_linear, False)

        objs[Reaction]['biomass_reaction_1'] = Reaction(id='biomass_reaction_1')
        value = "2*biomass_reaction_1 - pow( reaction_1, 2)"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertTrue(of_expr is None)
        self.assertIn(("contains multiple model object id matches: "
                       "'biomass_reaction_1' as a BiomassReaction id, "
                       "'biomass_reaction_1' as a Reaction id"),
                      invalid_attribute.messages[0])

        del objs[Reaction]['biomass_reaction_1']
        value = "2*biomass_reaction_1 - pow( reaction_x, 2)"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertTrue(of_expr is None)
        self.assertIn("contains the identifier(s) 'reaction_x', which aren't the id(s) of an object",
                      invalid_attribute.messages[0])

        value = "2*biomass_reaction_1 - pow( biomass_reaction_1, 2)"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        self.assertEqual(of_expr.reactions, [])
        self.assertEqual(of_expr.biomass_reactions, [objs[BiomassReaction]['biomass_reaction_1']])
        self.assertEqual(of_expr._analyzed_expr.is_linear, False)

    def test_dfba_obj_deserialize_invalid_ids(self):

        objs = {
            Reaction: {
                'pow': Reaction(id='pow'),
                'reaction_x': Reaction(id='reaction_x'),
            },
            BiomassReaction: {
                'exp': BiomassReaction(id='exp'),
            },
        }

        value = "2*exp - pow( reaction_x, 2)"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(of_expr, None)
        self.assertIn("Token `pow` is ambiguous",
                      invalid_attribute.messages[0])
        self.assertIn("Token matches a Reaction and a function",
                      invalid_attribute.messages[0])

    def test_dfba_obj_validate(self):

        objs = {
            BiomassReaction: {
                'biomass_reaction_0': BiomassReaction(id='biomass_reaction_0'),
                'biomass_reaction_1': BiomassReaction(id='biomass_reaction_1'),
            },
            Reaction: {
                'reaction_0': Reaction(id='reaction_0'),
                'reaction_1': Reaction(id='reaction_1'),
                'reaction_2': Reaction(id='reaction_2'),
            },
        }

        value = "2*biomass_reaction_1"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        rv = of_expr.validate()
        self.assertEqual(rv, None, str(rv))

        value = "2*biomass_reaction_1 - reaction_1"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        rv = of_expr.validate()
        self.assertEqual(rv, None, str(rv))

        value = "2*biomass_reaction_1 - reaction_1"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        of_expr.expression = of_expr.expression[0:-1]
        rv = of_expr.validate()
        self.assertTrue(isinstance(rv, InvalidObject))
        self.assertRegex(rv.attributes[0].messages[0], re.escape("aren't the id(s) of an object"))

        value = "2*biomass_reaction_1 - reaction_1"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        of_expr.expression += ')'
        rv = of_expr.validate()
        self.assertTrue(isinstance(rv, InvalidObject))
        self.assertRegex(rv.attributes[0].messages[0], "Python syntax error")

        value = "2*biomass_reaction_1 -  3*reaction_1"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        of_expr.biomass_reactions = []
        rv = of_expr.validate()
        self.assertRegex(rv.attributes[0].messages[0], re.escape("aren't the id(s) of an object"))

        value = "2*biomass_reaction_1 * reaction_1"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        rv = of_expr.validate()
        self.assertEqual(rv, None)

        value = "2*biomass_reaction_1 ** 2"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        rv = of_expr.validate()
        self.assertEqual(rv, None)

        value = "2*biomass_reaction_1 - pow( reaction_1, 2)"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        rv = of_expr.validate()
        self.assertEqual(rv, None)

        value = "2*biomass_reaction_1 - pow( reaction_1, 2)"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        self.assertEqual(invalid_attribute, None)
        of_expr.expression = "2*biomass_reaction_1 - min( reaction_1, 2)"
        rv = of_expr.validate()
        self.assertTrue(isinstance(rv, InvalidObject))
        self.assertRegex(rv.attributes[0].messages[0], re.escape("aren't the id(s) of an object"))

        of_expr = DfbaObjectiveExpression(expression="1.")
        rv = of_expr.validate()
        self.assertEqual(rv, None)

        of_expr = DfbaObjectiveExpression(expression="1")
        rv = of_expr.validate()
        self.assertEqual(rv, None)

        of_expr = DfbaObjectiveExpression(expression="True")
        rv = of_expr.validate()
        self.assertRegex(rv.attributes[0].messages[0], re.escape("aren't the id(s) of an object"))

        of_expr = DfbaObjectiveExpression(expression="'str' + 1.")
        rv = of_expr.validate()
        self.assertRegex(rv.attributes[0].messages[0], "cannot eval expression")

        of = DfbaObjective(id='dfba-obj-submdl_1',
                           submodel=Submodel(id='submdl_1'),
                           expression=DfbaObjectiveExpression(expression='1.'))
        self.assertEqual(of.validate(), None)

        of = DfbaObjective(id='invalid_id',
                           submodel=Submodel(id='submdl_2'),
                           expression=DfbaObjectiveExpression(expression='1.'))
        self.assertNotEqual(of.validate(), None)

        of = DfbaObjective(id='dfba-obj-submdl_3',
                           expression=DfbaObjectiveExpression(expression='1.'))
        self.assertNotEqual(of.validate(), None)

        value = "3*biomass_reaction_1 - reaction_1"
        of_expr, invalid_attribute = DfbaObjectiveExpression.deserialize(value, objs)
        of = DfbaObjective(id='dfba-obj-submdl_4',
                           submodel=Submodel(id='submdl_4'),
                           expression=of_expr)
        errors = of_expr.validate()
        self.assertEqual(errors, None, str(errors))
        of_expr.reactions.append(objs[Reaction]['reaction_0'])
        self.assertNotEqual(of_expr.validate(), None)

    def test_validate(self):
        self.assertEqual(self.model.validate(), None)

    def test_sbml_data_exchange(self):
        # create an SBMLDocument that uses version 2 of the 'Flux Balance Constraints' extension
        document = create_sbml_doc_w_fbc()

        # Initialize the SBML document's model
        sbml_model = init_sbml_model(document)

        # Write a dFBA Submodel to an SBML document
        self.submdl_2.comments = 'test submodel comment'
        sbml_model = self.submdl_2.add_to_sbml_doc(document)
        self.assertEqual(sbml_model.getIdAttribute(), self.submdl_2.id)
        self.assertEqual(sbml_model.getName(), self.submdl_2.name)
        self.assertIn(self.submdl_2.comments, sbml_model.getNotesString())

        # Write Compartments to the SBML document
        self.comp_0.comments = 'test comment'
        sbml_compartment = self.comp_0.add_to_sbml_doc(document)
        self.assertTrue(sbml_compartment.hasRequiredAttributes())
        self.assertEqual(sbml_compartment.getIdAttribute(), self.comp_0.id)
        self.assertEqual(sbml_compartment.getName(), self.comp_0.name)
        self.assertEqual(sbml_compartment.getSize(), self.comp_0.initial_volume)
        self.assertIn(self.comp_0.comments, sbml_compartment.getNotesString())

        # Write species used by the submodel to the SBML document
        for species in self.submdl_2.get_species():
            sbml_species = species.add_to_sbml_doc(document)
            self.assertTrue(sbml_species.hasRequiredAttributes())
            self.assertEqual(sbml_species.getIdAttribute(), species.gen_sbml_id())
            self.assertEqual(sbml_species.getName(), species.species_type.name)
            self.assertEqual(sbml_species.getCompartment(), species.compartment.id)
            self.assertEqual(sbml_species.getInitialConcentration(), species.concentration.value)

        # Write reactions used by the submodel to an SBML document
        self.rxn_2.min_flux = 100
        self.rxn_2.max_flux = 200
        self.rxn_2.comments = 'comments'
        sbml_reaction = self.rxn_2.add_to_sbml_doc(document)
        self.assertTrue(sbml_reaction.hasRequiredAttributes())
        self.assertEqual(sbml_reaction.getIdAttribute(), self.rxn_2.id)
        self.assertEqual(sbml_reaction.getName(), self.rxn_2.name)
        fbc_plugin = sbml_reaction.getPlugin('fbc')
        sbml_model = document.getModel()
        self.assertEqual(sbml_model.getParameter(fbc_plugin.getLowerFluxBound()).getValue(),
                         self.rxn_2.min_flux)
        self.assertEqual(sbml_model.getParameter(fbc_plugin.getUpperFluxBound()).getValue(),
                         self.rxn_2.max_flux)
        self.assertEqual(len(sbml_reaction.getListOfReactants()) + len(sbml_reaction.getListOfProducts()),
                         len(self.rxn_2.participants))
        for reactant in sbml_reaction.getListOfReactants():
            for participant in self.rxn_2.participants:
                if reactant.getSpecies() == participant.species.gen_sbml_id():
                    self.assertEqual(reactant.getStoichiometry(), -participant.coefficient)
        for product in sbml_reaction.getListOfProducts():
            for participant in self.rxn_2.participants:
                if product.getSpecies() == participant.species.gen_sbml_id():
                    self.assertEqual(product.getStoichiometry(), participant.coefficient)

        # Write the biomass reaction to the SBML document
        sbml_biomass_reaction = self.biomass_reaction.add_to_sbml_doc(document)
        self.assertTrue(sbml_biomass_reaction.hasRequiredAttributes())
        self.assertEqual(sbml_biomass_reaction.getIdAttribute(), self.biomass_reaction.id)
        self.assertEqual(sbml_biomass_reaction.getName(), self.biomass_reaction.name)
        self.assertIn(self.biomass_reaction.comments, sbml_biomass_reaction.getNotesString())
        fbc_plugin = sbml_biomass_reaction.getPlugin('fbc')
        sbml_model = document.getModel()
        self.assertEqual(sbml_model.getParameter(fbc_plugin.getLowerFluxBound()).getValue(), 0)
        self.assertEqual(sbml_model.getParameter(fbc_plugin.getUpperFluxBound()).getValue(),
                         float('inf'))
        self.assertEqual(len(sbml_biomass_reaction.getListOfReactants()) +
                         len(sbml_biomass_reaction.getListOfProducts()),
                         len(self.biomass_reaction.biomass_components))

        # Write parameters to the SBML document
        param = self.model.parameters.create(
            id='param_custom_units', name='param custom units',
            value=100, units='custom')
        param.submodel = self.model.submodels[0]
        self.parameters.append(param)

        for param in self.parameters:
            sbml_param = param.add_to_sbml_doc(document)
            self.assertTrue(sbml_param.hasRequiredAttributes())
            self.assertIn(param.id, sbml_param.getIdAttribute())
            self.assertEqual(sbml_param.getName(), param.name)
            self.assertEqual(sbml_param.getValue(), param.value)

        # Write an objective function to the model
        #   create DfbaObjective
        rxn_id = 'rxn_2'
        biomass_reaction_id = 'biomass_reaction_1'
        objs = {
            Reaction: {
                rxn_id: self.rxn_2,
            },
            BiomassReaction: {
                biomass_reaction_id: self.biomass_reaction},
        }
        (of_expr, _) = DfbaObjectiveExpression.deserialize('biomass_reaction_1 + 2*rxn_2', objs)
        of = self.submdl_2.dfba_obj = DfbaObjective(expression=of_expr)

        prepare_model = PrepareModel(self.model)
        (reactions, biomass_reactions) = prepare_model.parse_dfba_submodel_obj_func(self.submdl_2)
        PrepareModel.assign_linear_objective_fn(self.submdl_2, reactions, biomass_reactions)
        self.submdl_2.dfba_obj.expression.linear = True

        #   write DfbaObjective to the model, and test
        sbml_objective = of.add_to_sbml_doc(document)
        self.assertEqual(wrap_libsbml(sbml_objective.getNumFluxObjectives, returns_int=True), 2)
        self.assertEqual(len(wrap_libsbml(sbml_objective.getListOfFluxObjectives)), 2)
        for flux_objective in wrap_libsbml(sbml_objective.getListOfFluxObjectives):
            if wrap_libsbml(flux_objective.getReaction) == rxn_id:
                self.assertEqual(wrap_libsbml(flux_objective.getCoefficient), 2.0)
            elif wrap_libsbml(flux_objective.getReaction) == biomass_reaction_id:
                self.assertEqual(wrap_libsbml(flux_objective.getCoefficient), 1.0)
            else:
                self.fail("reaction {} unexpected".format(wrap_libsbml(flux_objective.getReaction)))

        # Check the SBML document
        self.assertEqual(wrap_libsbml(get_SBML_compatibility_method(document)), 0)
        for i in range(document.checkConsistency()):
            print(document.getError(i).getShortMessage())
            print(document.getError(i).getMessage())
        self.assertEqual(wrap_libsbml(document.checkConsistency), 0)

        # exceptions -- dFBA objective isn't linear
        expression, invalid_attribute = DfbaObjectiveExpression.deserialize('pow(1, 2)', {})
        self.assertEqual(invalid_attribute, None)
        obj_func = DfbaObjective(expression=expression, submodel=Submodel(id='Metabolism'))
        with pytest.warns(UserWarning):
            obj_func.add_to_sbml_doc(document)

    def test_dfba_obj_get_products(self):
        model = Model()
        submodel = model.submodels.create()
        species_type_0 = model.species_types.create(id='spec_0')
        species_type_1 = model.species_types.create(id='spec_1')
        species_type_2 = model.species_types.create(id='spec_2')
        compartment_0 = model.compartments.create(id='c_0')
        compartment_1 = model.compartments.create(id='c_1')
        compartment_2 = model.compartments.create(id='c_2')
        species_0 = Species(id='spec_0[c_0]', species_type=species_type_0, compartment=compartment_0)
        species_1 = Species(id='spec_1[c_1]', species_type=species_type_1, compartment=compartment_1)
        species_2 = Species(id='spec_2[c_2]', species_type=species_type_2, compartment=compartment_2)

        obj_func = submodel.dfba_obj = DfbaObjective(
            expression=DfbaObjectiveExpression(
                reactions=[
                    Reaction(
                        reversible=True,
                        participants=[SpeciesCoefficient(species=species_0)],
                    ),
                ],
                biomass_reactions=[
                    BiomassReaction(
                        biomass_components=[BiomassComponent(coefficient=-1, species=species_1)],
                    ),
                ],
            ),
        )
        self.assertEqual(obj_func.get_products(), [species_0])

        obj_func = submodel.dfba_obj = DfbaObjective(
            expression=DfbaObjectiveExpression(
                reactions=[
                    Reaction(
                        reversible=True,
                        participants=[SpeciesCoefficient(species=species_0)],
                    ),
                ],
                biomass_reactions=[
                    BiomassReaction(
                        biomass_components=[BiomassComponent(coefficient=-1, species=species_1)],
                    ),
                    BiomassReaction(
                        biomass_components=[BiomassComponent(coefficient=1, species=species_2)],
                    ),
                ],
            ),
        )
        with self.assertRaisesRegex(ValueError, 'does not belong to submodel'):
            obj_func.get_products()

    def make_objects(self):
        model = Model()
        objects = {
            Observable: {},
            Parameter: {},
            Function: {},
            Species: {},
        }
        for id in ['a', 'b', 'duped_id']:
            param = model.parameters.create(id=id)
            objects[Parameter][id] = param

        for id in ['ccc', 'ddd', 'eee', 'duped_id']:
            observable = model.observables.create(id=id)
            objects[Observable][id] = observable

        for id in ['f', 'g', 'duped_id']:
            function = model.functions.create(id=id)
            objects[Function][id] = function

        # use existing species
        for s in self.species:
            objects[Species][s.id] = s

        id_map = {}
        for model_type in objects.keys():
            for id, obj in objects[model_type].items():
                typed_id = "{}.{}".format(model_type.__name__, id)
                id_map[typed_id] = obj

        return model, objects, id_map

    def test_make_obj(self):
        model, objects, id_map = self.make_objects()
        expr = 'ccc + 2 * ddd'
        fun_obj = ExpressionMethods.make_obj(model, Function, 'fun_id', expr, objects)
        self.assertTrue(isinstance(fun_obj, Function))
        self.assertEqual(fun_obj.id, 'fun_id')
        self.assertEqual(fun_obj.model, model)
        self.assertTrue(isinstance(fun_obj.expression, FunctionExpression))
        self.assertTrue(fun_obj in model.functions)
        fun_expr = fun_obj.expression
        self.assertEqual(fun_expr.expression, expr)
        self.assertEqual(set(fun_expr.observables),
                         set([id_map['Observable.ccc'], id_map['Observable.ddd']]))
        self.assertEqual(set(fun_expr.parameters), set([]))
        self.assertEqual(set(fun_expr.functions), set([]))

        expr = 'ccc + 2 * x'
        expr_model_obj, error = ExpressionMethods.make_expression_obj(Function, expr, objects)
        self.assertTrue(expr_model_obj is None)
        self.assertTrue(isinstance(error, InvalidAttribute))

        fun_obj = ExpressionMethods.make_obj(model, Function, 'fun_id', '', objects,
                                             allow_invalid_objects=True)
        self.assertTrue(isinstance(fun_obj, Function))

    def do_test_valid_expression(self, expression_class, parent_class, objects, expr, expected_val,
                                 expected_related_objs=None, expected_error=None):
        """ Test a valid expression

        Args:
            expression_class (:obj:`obj_model.Model`): expression class being tested
            parent_class (:obj:`obj_model.Model`): the expression model that uses an expression_class
            objects (:obj:`dict`): dict of objects which can be used by `expr`
            expr (:obj:`str`): the expression
            expected_val (:obj:`obj`): the value expected when the expression is evaluated
            expected_related_objs (:obj:`dict`, optional): objects that should be used by the deserialize expression
        """
        expr_obj, error = expression_class.deserialize(expr, objects)
        if expected_error:
            self.assertIn(expected_error, str(error))
        else:
            self.assertEqual(error, None, str(error))
            self.assertEqual(expr_obj.serialize(), expr)
            self.assertEqual(expr_obj.expression, expr)
            self.assertEqual(expr_obj, objects[expression_class][expr])
            # check used objects in expression_class attributes
            if expected_related_objs:
                for modifier, elements in expected_related_objs.items():
                    self.assertEqual(set(getattr(expr_obj, modifier)), set(elements))
            error = expr_obj.validate()
            self.assertEqual(error, None)
            self.assertEqual(expr_obj._analyzed_expr.test_eval(), expected_val)

    def test_valid_function_expressions(self):
        _, objects, id_map = self.make_objects()

        i = 0
        for i_expr, (expr, expected_test_val, expected_related_objs, error) in enumerate([
            ('ccc', 1, {'observables': [id_map['Observable.ccc']]}, None),
            ('ccc', 1, {'observables': [id_map['Observable.ccc']]}, None),     # reuse the FunctionExpression
            ('ddd + eee', 2, {'observables': [id_map['Observable.ddd'], id_map['Observable.eee']]}, None),
            ('ddd + 2 * eee', 3, {}, None),
            ('ddd + 2 * eee > 3', False, {}, None),
            ('1 * duped_id', None, {}, 'multiple model object id matches'),
            ('1 * Observable.duped_id', 1,
                {'observables': [id_map['Observable.duped_id']]},
                None),
            ('a + f()', 2,
                {'parameters': [id_map['Parameter.a']],
                 'functions':[id_map['Function.f']]},
                None),
            ('log(a)', math.log(1), {}, None),
            ('max(a, b)', 1,
                {'parameters': [id_map['Parameter.a'], id_map['Parameter.b']]},
                None),
            ('Observable.ddd + Observable.duped_id - Parameter.duped_id', 1,
                {'parameters': [id_map['Parameter.duped_id']],
                 'observables':[id_map['Observable.duped_id'], id_map['Observable.ddd']]},
                None),
            ('ddd * Function.duped_id()', 1,
                {'observables': [id_map['Observable.ddd']],
                 'functions':[id_map['Function.duped_id']]},
                None),
        ]):
            self.do_test_valid_expression(FunctionExpression, Function,
                                          objects, expr, expected_test_val, expected_related_objs,
                                          expected_error=error)

    def do_test_expr_deserialize_error(self, expression_class, parent_class, objects, expr, error_msg_substr):
        """ Test an expression that fails to deserialize

        Args:
            expression_class (:obj:`obj_model.Model`): expression class being tested
            parent_class (:obj:`obj_model.Model`): the expression model that uses an expression_class
            objects (:obj:`dict`): dict of objects which can be used by `expr`
            expr (:obj:`str`): the expression
            error_msg_substr (:obj:`str`): substring expected in error message
        """
        func_expr, error = expression_class.deserialize(expr, objects)
        self.assertEqual(func_expr, None)
        self.assertTrue(isinstance(error, InvalidAttribute))
        self.assertIn(error_msg_substr, error.messages[0])

    def test_function_expression_deserialize_errors(self):
        _, objects, _ = self.make_objects()

        for expr_model, model in [(FunctionExpression, Function),
                                  (StopConditionExpression, StopCondition),
                                  (ObservableExpression, Observable)]:
            self.do_test_expr_deserialize_error(expr_model, model, objects, 'id1[id2', "Python syntax error")
            bad_id = 'no_such_obj'
            self.do_test_expr_deserialize_error(expr_model, model, objects, bad_id,
                                                "contains the identifier(s) '{}', which aren't the id(s) of an object".format(bad_id))

    def test_stop_condition_expression_deserialize_errors(self):
        _, objects, _ = self.make_objects()

        expr = '(ccc > 10 and ddd < 5) or (a + f() * g())'
        self.do_test_expr_deserialize_error(StopConditionExpression, StopCondition, objects, expr,
                                            "contains the identifier(s) 'and', which aren't the id(s) of an object")

    def do_test_invalid_expression(self, expression_class, parent_class, objects, expr, error_msg_substr):
        """ Test an expression that fails to validate

        Args:
            expression_class (:obj:`obj_model.Model`): expression class being tested
            parent_class (:obj:`obj_model.Model`): the expression model that uses an expression_class
            objects (:obj:`dict`): dict of objects which can be used by `expr`
            expr (:obj:`str`): the expression
            error_msg_substr (:obj:`str`): substring expected in error message
        """
        func_expr, error = expression_class.deserialize(expr, objects)
        self.assertEqual(error, None)
        invalid_obj = func_expr.validate()
        self.assertTrue(isinstance(invalid_obj, InvalidObject))
        self.assertIn(error_msg_substr, invalid_obj.attributes[0].messages[0])

    def test_invalid_function_expressions(self):
        _, objects, _ = self.make_objects()

        bad_expr = '1 +'
        self.do_test_invalid_expression(FunctionExpression, Function, objects, bad_expr,
                                        "SyntaxError: cannot eval expression '{}' in Function".format(bad_expr))

    def test_function(self):
        model, objects, _ = self.make_objects()
        kwargs = dict(id='fun_1', name='name fun_1', model=model, comments='no comment')
        func = Function(**kwargs)
        self.assertEqual(func.id, kwargs['id'])
        self.assertEqual(func.name, kwargs['name'])
        self.assertEqual(func.model, model)
        self.assertEqual(model.functions[-1], func)
        self.assertEqual(func.comments, kwargs['comments'])
        expr = 'ccc + ddd'
        func_expr, _ = FunctionExpression.deserialize(expr, objects)
        func.expression = func_expr

    def test_valid_stop_conditions(self):
        _, objects, id_map = self.make_objects()

        some_used_objs = {'observables': [id_map['Observable.ccc'], id_map['Observable.ddd']],
                          'functions': [id_map['Function.f'], id_map['Function.g']],
                          'parameters': [id_map['Parameter.a']]}
        for expr, expected_test_val, expected_attrs in [
            ('ccc > 10', False, {'observables': [id_map['Observable.ccc']]}),
            ('ccc > 0', True, {'observables': [id_map['Observable.ccc']]}),
            ('ccc > 0', True, {'observables': [id_map['Observable.ccc']]}),    # reuse StopConditionExpression
            ('ccc + ddd - a + f() * g() + 10 > 0', True, some_used_objs)
        ]:
            self.do_test_valid_expression(StopConditionExpression, StopCondition,
                                          objects, expr, expected_test_val, expected_attrs)

    def test_invalid_stop_condition_expressions(self):
        _, objects, _ = self.make_objects()

        bad_expr = '1 + ccc'
        self.do_test_invalid_expression(StopConditionExpression, StopCondition, objects, bad_expr,
                                        "Evaluating '{}', a {} expression, should return a bool but it returns a float".format(
                                            bad_expr, StopConditionExpression.__name__))

    def test_stop_condition(self):
        model, objects, _ = self.make_objects()
        kwargs = dict(id='stop_cond_1', name='name stop_cond_1', model=model, comments='no comment')
        stop_condition = StopCondition(**kwargs)
        self.assertEqual(stop_condition.id, kwargs['id'])
        self.assertEqual(stop_condition.name, kwargs['name'])
        self.assertEqual(stop_condition.model, model)
        self.assertEqual(model.stop_conditions[-1], stop_condition)
        self.assertEqual(stop_condition.comments, kwargs['comments'])
        expr = 'ccc + ddd'
        stop_condition_expr, _ = StopConditionExpression.deserialize(expr, objects)
        stop_condition.expression = stop_condition_expr

    def test_valid_observable_expressions(self):
        _, objects, id_map = self.make_objects()

        for expr, expected_test_val, expected_related_objs in [
            ('3 * spec_type_0[comp_0]', 3, {'species': [id_map['Species.spec_type_0[comp_0]']]}),
            ('spec_type_0[comp_0] + 4e2*spec_type_1[comp_0] - 1  * spec_type_3[comp_1]', 400,
                {'species': [
                    id_map['Species.spec_type_0[comp_0]'],
                    id_map['Species.spec_type_1[comp_0]'],
                    id_map['Species.spec_type_3[comp_1]']
                ]}),
            ('1.5 * spec_type_0[comp_0] - ddd + Observable.duped_id', 1.5,
                {'species': [id_map['Species.spec_type_0[comp_0]']],
                 'observables':[id_map['Observable.duped_id'], id_map['Observable.ddd']],
                 }),
        ]:
            self.do_test_valid_expression(ObservableExpression, Observable,
                                          objects, expr, expected_test_val, expected_related_objs)

    def test_invalid_observable_expressions(self):
        _, objects, _ = self.make_objects()

        non_linear_expression = 'ccc * ccc'
        self.do_test_invalid_expression(ObservableExpression, Observable, objects, non_linear_expression,
                                        "Expression must be linear")

    def test_observable(self):
        model, objects, _ = self.make_objects()
        kwargs = dict(id='obs_1', name='name obs_1', model=model, comments='no comment')
        obs = Observable(**kwargs)
        self.assertEqual(obs.id, kwargs['id'])
        self.assertEqual(obs.name, kwargs['name'])
        self.assertEqual(obs.model, model)
        self.assertEqual(model.observables[-1], obs)
        self.assertEqual(obs.comments, kwargs['comments'])
        expr = 'ccc + ddd - 2 * spec_type_0[comp_0]'
        func_expr, _ = ObservableExpression.deserialize(expr, objects)
        obs.expression = func_expr

    def test_valid_model_types(self):
        for model_type in [RateLawEquation, FunctionExpression, StopConditionExpression,
                           DfbaObjectiveExpression, ObservableExpression]:
            self.assertTrue(hasattr(model_type.Meta, 'valid_models'))
            for valid_model_type in model_type.Meta.valid_models:
                self.assertTrue(hasattr(wc_lang.core, valid_model_type))


class TestCoreFromFile(unittest.TestCase):

    MODEL_FILENAME = os.path.join(os.path.dirname(__file__), 'fixtures', 'test_model.xlsx')

    def setUp(self):
        Submodel.objects.reset()
        # read and initialize a model
        self.model = Reader().run(self.MODEL_FILENAME)
        self.dfba_submodel = Submodel.objects.get_one(id='submodel_1')

    def test_get_ex_species(self):
        ex_compartment = self.model.compartments.get_one(id=EXTRACELLULAR_COMPARTMENT_ID)
        ex_species = self.dfba_submodel.get_species(compartment=ex_compartment)
        self.assertEqual(set(ex_species),
                         set(Species.get(['specie_1[e]', 'specie_2[e]'], self.dfba_submodel.get_species())))


class TestTaxonRank(unittest.TestCase):

    def test(self):
        self.assertEqual(TaxonRank['varietas'], TaxonRank.variety)
        self.assertEqual(TaxonRank['strain'], TaxonRank.variety)
        self.assertEqual(TaxonRank['tribus'], TaxonRank.tribe)
        self.assertEqual(TaxonRank['familia'], TaxonRank.family)
        self.assertEqual(TaxonRank['ordo'], TaxonRank.order)
        self.assertEqual(TaxonRank['class'], TaxonRank.classis)
        self.assertEqual(TaxonRank['division'], TaxonRank.phylum)
        self.assertEqual(TaxonRank['divisio'], TaxonRank.phylum)
        self.assertEqual(TaxonRank['regnum'], TaxonRank.kingdom)
