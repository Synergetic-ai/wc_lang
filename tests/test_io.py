""" Tests of input/output.

:Author: Jonathan Karr <karr@mssm.edu>
:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2016-11-10
:Copyright: 2016-2018, Karr Lab
:License: MIT
"""

from obj_tables import utils
from test.support import EnvironmentVarGuard
from wc_lang import (Model, Taxon, TaxonRank, Submodel, Reaction, SpeciesType,
                     Species, Compartment, SpeciesCoefficient,
                     DfbaObjSpecies, DfbaObjReaction,
                     Parameter, Reference, Identifier, Function, FunctionExpression,
                     StopConditionExpression,
                     Observable, ObservableExpression,
                     RateLaw, RateLawExpression, RateLawDirection,
                     DistributionInitConcentration,
                     DfbaObjective, DfbaObjectiveExpression, ChemicalStructure)
from wc_lang import io
from wc_lang.io import Writer, Reader, convert, create_template
from wc_onto import onto
from wc_utils.util.chem import EmpiricalFormula
from wc_utils.util.git import GitHubRepoForTests
from wc_utils.util.units import unit_registry
from wc_utils.workbook.io import read as read_workbook, write as write_workbook
import obj_tables.core
import obj_tables.io
import os
import re
import shutil
import tempfile
import unittest


class TestCreateTemplate(unittest.TestCase):

    def setUp(self):
        _, self.filename = tempfile.mkstemp(suffix='.xlsx')

    def tearDown(self):
        if os.path.isfile(self.filename):
            os.remove(self.filename)

    def test_create_template(self):
        create_template(self.filename, data_repo_metadata=False)
        self.assertIsInstance(Reader().run(self.filename), dict)
        self.assertIsInstance(Reader().run(self.filename)[Model][0], Model)


class TestSimpleModel(unittest.TestCase):

    def setUp(self):
        self.model = mdl = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.1b')

        mdl.taxon = Taxon(id='taxon', name='test taxon', rank=TaxonRank.species)

        self.comp_0 = comp_0 = mdl.compartments.create(id='comp_0', name='compartment 0')
        self.comp_1 = comp_1 = mdl.compartments.create(id='comp_1', name='compartment 1')
        self.compartments = compartments = [comp_0, comp_1]

        density_comp_0 = mdl.parameters.create(id='density_comp_0', value=1100, units=unit_registry.parse_units('g l^-1'))
        density_comp_1 = mdl.parameters.create(id='density_comp_1', value=1000, units=unit_registry.parse_units('g l^-1'))
        compartments[0].init_density = density_comp_0
        compartments[1].init_density = density_comp_1

        self.species_types = species_types = []
        self.species = species = []
        for i in range(8):
            spec_type = mdl.species_types.create(
                id='spec_type_{}'.format(i),
                name='species type {}'.format(i),
                type=onto['WC:metabolite'],
                structure=ChemicalStructure(
                    empirical_formula=EmpiricalFormula('C' + str(i + 1)),
                    molecular_weight=12 * (i + 1),
                    charge=i + 1))
            species_types.append(spec_type)

            if i != 3:
                spec = Species(species_type=spec_type, compartment=comp_0)
            else:
                spec = Species(species_type=spec_type, compartment=comp_1)
            spec.id = spec.gen_id()
            spec.model = mdl
            species.append(spec)

            conc = DistributionInitConcentration(model=mdl,
                                                 species=spec, mean=3 * i, units=unit_registry.parse_units('M'))
            conc.id = conc.gen_id()

        species_coefficients = {}

        def get_or_create_species_coefficient(species=None, coefficient=None):
            part_serialized = SpeciesCoefficient._serialize(species, coefficient)
            if part_serialized not in species_coefficients:
                species_coefficients[part_serialized] = SpeciesCoefficient(species=species, coefficient=coefficient)
            return species_coefficients[part_serialized]

        self.observables = observables = []
        objects = {Species: {}, Observable: {}}
        for i in range(8):
            expr_parts = []
            for j in range(i + 1):
                objects[Species][species[j].id] = species[j]
                expr_parts.append("{} * {}".format(j + 1, species[j].id))
            obs_expr, _ = ObservableExpression.deserialize(' + '.join(expr_parts), objects)
            id = 'obs_{}'.format(i)
            obs = mdl.observables.create(id=id, expression=obs_expr)
            observables.append(obs)
            objects[Observable][id] = obs
        for i in range(3):
            expr_parts = []
            for j in range(i + 1):
                expr_parts.append("{} * {}".format(j + 1, observables[j].id))
            obs_expr, _ = ObservableExpression.deserialize(' + '.join(expr_parts), objects)
            obs = mdl.observables.create(id='obs_{}'.format(i + 8), expression=obs_expr)
            observables.append(obs)

        objects = {Observable: {o.id: o for o in observables}}
        self.functions = functions = []
        for i in range(8):
            obs_expr = ' + 2 * '.join(o.id for o in observables[0:i + 1])
            func_expr, _ = FunctionExpression.deserialize(obs_expr,
                                                          objects)
            func = mdl.functions.create(id='func_{}'.format(i),
                                        expression=func_expr,
                                        units=unit_registry.parse_units('molecule'))
            functions.append(func)

        self.submdl_0 = submdl_0 = mdl.submodels.create(
            id='submodel_0', name='submodel 0', framework=onto['WC:stochastic_simulation_algorithm'])
        self.submdl_1 = submdl_1 = mdl.submodels.create(
            id='submodel_1', name='submodel 1', framework=onto['WC:stochastic_simulation_algorithm'])
        self.submdl_2 = submdl_2 = mdl.submodels.create(
            id='submodel_2', name='submodel 2', framework=onto['WC:dynamic_flux_balance_analysis'])
        self.submodels = submodels = [submdl_0, submdl_1, submdl_2]

        self.rxn_0 = rxn_0 = submdl_0.reactions.create(
            id='rxn_0', name='reaction 0', model=mdl)

        rxn_0.participants.append(get_or_create_species_coefficient(species=species[0], coefficient=-3))
        rxn_0.participants.append(get_or_create_species_coefficient(species=species[1], coefficient=-3))
        rxn_0.participants.append(get_or_create_species_coefficient(species=species[2], coefficient=3))
        k_cat_0 = mdl.parameters.create(id='k_cat_0', value=2, units=unit_registry.parse_units('s^-1'))
        k_m_0 = mdl.parameters.create(id='k_m_0', value=1, units=unit_registry.parse_units('molecule'))
        expression, _ = RateLawExpression.deserialize('k_cat_0 * {0} / (k_m_0 + {0})'.format(species[5].id), {
            Species: {
                species[5].id: species[5],
            },
            Parameter: {
                'k_cat_0': k_cat_0,
                'k_m_0': k_m_0,
            },
        })
        rate_law_0 = rxn_0.rate_laws.create(
            model=mdl,
            direction=RateLawDirection.forward,
            expression=expression,
            units=unit_registry.parse_units('s^-1'))
        rate_law_0.id = rate_law_0.gen_id()

        self.rxn_1 = rxn_1 = submdl_1.reactions.create(
            id='rxn_1', name='reaction 1', model=mdl)
        rxn_1.participants.append(get_or_create_species_coefficient(species=species[0], coefficient=-2))
        rxn_1.participants.append(get_or_create_species_coefficient(species=species[1], coefficient=-3))
        rxn_1.participants.append(get_or_create_species_coefficient(species=species[3], coefficient=2))
        k_cat_1 = mdl.parameters.create(id='k_cat_1', value=2, units=unit_registry.parse_units('s^-1'))
        k_m_1 = mdl.parameters.create(id='k_m_1', value=1, units=unit_registry.parse_units('molecule'))
        expression, _ = RateLawExpression.deserialize('k_cat_1 * {0} / (k_m_1 + {0})'.format(species[6].id), {
            Species: {
                species[6].id: species[6],
            },
            Parameter: {
                'k_cat_1': k_cat_1,
                'k_m_1': k_m_1,
            },
        })
        rate_law_1 = rxn_1.rate_laws.create(
            model=mdl,
            direction=RateLawDirection.forward,
            expression=expression,
            units=unit_registry.parse_units('s^-1'))
        rate_law_1.id = rate_law_1.gen_id()

        self.rxn_2 = rxn_2 = submdl_2.reactions.create(
            id='rxn_2', name='reaction 2', model=mdl)
        rxn_2.participants.append(get_or_create_species_coefficient(species=species[0], coefficient=-2))
        rxn_2.participants.append(get_or_create_species_coefficient(species=species[1], coefficient=-3))
        rxn_2.participants.append(get_or_create_species_coefficient(species=species[7], coefficient=1))
        k_cat_2 = mdl.parameters.create(id='k_cat_2', value=2, units=unit_registry.parse_units('s^-1'))
        k_m_2 = mdl.parameters.create(id='k_m_2', value=1, units=unit_registry.parse_units('molecule'))
        expression, _ = RateLawExpression.deserialize('k_cat_2 * {0} / (k_m_2 + {0})'.format(species[7].id), {
            Species: {
                species[7].id: species[7],
            },
            Parameter: {
                'k_cat_2': k_cat_2,
                'k_m_2': k_m_2,
            },
        })
        rate_law_2 = rxn_2.rate_laws.create(
            model=mdl,
            direction=RateLawDirection.forward,
            expression=expression,
            units=unit_registry.parse_units('s^-1'))
        rate_law_2.id = rate_law_2.gen_id()

        submdl_2.dfba_obj = DfbaObjective(model=mdl)
        submdl_2.dfba_obj.id = submdl_2.dfba_obj.gen_id()
        submdl_2.dfba_obj.expression = DfbaObjectiveExpression(expression='rxn_2', reactions=[rxn_2])

        self.reactions = [rxn_0, rxn_1, rxn_2]
        self.rate_laws = [rate_law_0, rate_law_1, rate_law_2]

        self.parameters = parameters = []
        self.references = references = []
        self.identifiers = identifiers = []
        for i in range(3):
            param = mdl.parameters.create(
                id='param_{}'.format(i), name='parameter {}'.format(i),
                value=i * 4, units=unit_registry.parse_units('dimensionless'))
            param.submodels = submodels[i:i + 1]
            parameters.append(param)

            ref = param.references.create(
                id='ref_{}'.format(i), name='reference {}'.format(i),
                type=None)
            ref.model = mdl
            references.append(ref)

            x_ref = ref.identifiers.create(namespace='x', id='y' * (i + 1))
            identifiers.append(x_ref)

        param = mdl.parameters.create(
            id='param_stop_cond', name='parameter - stop condition',
            value=1., units=unit_registry.parse_units('molecule'))
        parameters.append(param)
        objects[Parameter] = {param.id: param}
        self.stop_conditions = stop_conditions = []
        for i in range(3):
            cond = mdl.stop_conditions.create(id='stop_cond_{}'.format(i))
            expr = '({}) > {}'.format(' + '.join(o.id for o in observables[0:i+1]), param.id)
            cond.expression, error = StopConditionExpression.deserialize(expr, objects)
            self.stop_conditions.append(cond)

        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_write_read(self):
        filename = os.path.join(self.tempdir, 'model.xlsx')

        Writer().run(filename, self.model, data_repo_metadata=False)
        model = Reader().run(filename)[Model][0]
        self.assertEqual(model.validate(), None)

        self.assertTrue(model.is_equal(self.model))
        self.assertEqual(self.model.difference(model), '')

    def test_write_with_repo_metadata(self):
        # create temp git repo & write file into it
        test_repo_name = 'test_wc_lang_test_io'
        test_github_repo = GitHubRepoForTests(test_repo_name)
        repo = test_github_repo.make_test_repo(self.tempdir)

        # write data repo metadata in data_file
        data_file = os.path.join(self.tempdir, 'test.xlsx')
        Writer().run(data_file, self.model, data_repo_metadata=True)
        # deliberately read metadata
        objs_read = Reader().run(data_file, [utils.DataRepoMetadata] + list(Writer.MODELS))
        data_repo_metadata = objs_read[utils.DataRepoMetadata][0]
        self.assertTrue(data_repo_metadata.url.startswith('https://github.com/'))
        self.assertEqual(data_repo_metadata.branch, 'master')
        self.assertEqual(len(data_repo_metadata.revision), 40)

        test_github_repo.delete_test_repo()

    def test_write_read_sloppy(self):
        filename = os.path.join(self.tempdir, 'model.xlsx')

        Writer().run(filename, self.model, data_repo_metadata=False)

        wb = read_workbook(filename)
        row = wb['!!Model'].pop(3)
        wb['!!Model'].insert(4, row)
        write_workbook(filename, wb)

        with self.assertRaisesRegex(ValueError, "The rows of worksheet '!!Model' must be defined in this order"):
            Reader().run(filename)

        env = EnvironmentVarGuard()
        env.set('CONFIG__DOT__wc_lang__DOT__io__DOT__strict', '0')
        with env:
            model = Reader().run(filename)[Model][0]
        self.assertEqual(model.validate(), None)

        self.assertTrue(model.is_equal(self.model))
        self.assertEqual(self.model.difference(model), '')

    def test_convert(self):
        filename_xls1 = os.path.join(self.tempdir, 'model1.xlsx')
        filename_xls2 = os.path.join(self.tempdir, 'model2.xlsx')
        filename_csv = os.path.join(self.tempdir, 'model-*.csv')

        Writer().run(filename_xls1, self.model, data_repo_metadata=False)

        convert(filename_xls1, filename_csv)
        self.assertTrue(os.path.isfile(os.path.join(self.tempdir, 'model-Model.csv')))
        self.assertTrue(os.path.isfile(os.path.join(self.tempdir, 'model-Taxon.csv')))
        model = Reader().run(filename_csv)[Model][0]
        self.assertTrue(model.is_equal(self.model))

        convert(filename_csv, filename_xls2)
        model = Reader().run(filename_xls2)[Model][0]
        self.assertTrue(model.is_equal(self.model))

    def test_convert_sloppy(self):
        filename_xls1 = os.path.join(self.tempdir, 'model1.xlsx')
        filename_xls2 = os.path.join(self.tempdir, 'model2.xlsx')
        filename_csv = os.path.join(self.tempdir, 'model-*.csv')

        Writer().run(filename_xls1, self.model, data_repo_metadata=False)

        wb = read_workbook(filename_xls1)
        row = wb['!!Model'].pop(3)
        wb['!!Model'].insert(4, row)
        write_workbook(filename_xls1, wb)

        with self.assertRaisesRegex(ValueError, "The rows of worksheet '!!Model' must be defined in this order"):
            convert(filename_xls1, filename_csv)
        env = EnvironmentVarGuard()
        env.set('CONFIG__DOT__wc_lang__DOT__io__DOT__strict', '0')
        with env:
            convert(filename_xls1, filename_csv)

        self.assertTrue(os.path.isfile(os.path.join(self.tempdir, 'model-Model.csv')))
        self.assertTrue(os.path.isfile(os.path.join(self.tempdir, 'model-Taxon.csv')))
        model = Reader().run(filename_csv)[Model][0]
        self.assertTrue(model.is_equal(self.model))

        convert(filename_csv, filename_xls2)
        model = Reader().run(filename_xls2)[Model][0]
        self.assertTrue(model.is_equal(self.model))

    def test_read_without_validation(self):
        # write model to file
        filename = os.path.join(self.tempdir, 'model.xlsx')
        Writer().run(filename, self.model, data_repo_metadata=False)

        # read model and verify that it validates
        model = Reader().run(filename)[Model][0]
        self.assertEqual(model.validate(), None)

        # introduce error into model file
        wb = read_workbook(filename)
        wb['!!Model'][4][1] = '1000'
        write_workbook(filename, wb)

        # read model and verify that it doesn't validate
        with self.assertRaisesRegex(ValueError, 'does not match pattern'):
            Reader().run(filename)

        env = EnvironmentVarGuard()
        env.set('CONFIG__DOT__wc_lang__DOT__io__DOT__validate', '0')
        with env:
            model = Reader().run(filename)[Model][0]

        self.assertNotEqual(model.validate(), None)

    def test_write_with_optional_args(self):
        # write model to file, passing models
        filename = os.path.join(self.tempdir, 'model.xlsx')
        Writer().run(filename, self.model, models=Writer.MODELS)

        # read model and verify that it validates
        model = Reader().run(filename)[Model][0]
        self.assertEqual(model.validate(), None)

        # write model to file, passing validate
        filename = os.path.join(self.tempdir, 'model.xlsx')
        Writer().run(filename, self.model, validate=True)

        # read model and verify that it validates
        model = Reader().run(filename)[Model][0]
        self.assertEqual(model.validate(), None)


class TestJsonIO(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test(self):
        test_model = Model(id='model', version='0.0.1', wc_lang_version='0.0.1')
        submodel = test_model.submodels.create(id='submodel')

        filename_yaml = os.path.join(self.tempdir, 'model.yaml')
        Writer().run(filename_yaml, test_model)
        model = Reader().run(filename_yaml)[Model][0]
        self.assertEqual(model.validate(), None)

        self.assertTrue(model.is_equal(test_model))
        self.assertEqual(test_model.difference(model), '')


class TestExampleModel(unittest.TestCase):

    def setUp(self):
        _, self.filename = tempfile.mkstemp(suffix='.xlsx')

    def tearDown(self):
        if os.path.isfile(self.filename):
            os.remove(self.filename)

    def test_read_write(self):
        fixture_filename = os.path.join(os.path.dirname(__file__), 'fixtures', 'example-model.xlsx')

        model = Reader().run(fixture_filename)[Model][0]
        self.assertEqual(model.validate(), None)

        # compare excel files
        Writer().run(self.filename, model, data_repo_metadata=False)
        original = read_workbook(fixture_filename)
        copy = read_workbook(self.filename)
        remove_ws_metadata(original)
        remove_ws_metadata(copy)
        original.pop('!!' + obj_tables.core.TOC_SHEET_NAME)
        copy.pop('!!' + obj_tables.core.TOC_SHEET_NAME)

        # note that models must be sorted by id for this assertion to hold
        for sheet in original.keys():
            for i_row, (copy_row, original_row) in enumerate(zip(copy[sheet], original[sheet])):
                self.assertEqual(copy_row, original_row,
                                 msg='Rows {} of {} sheets are not equal'.format(i_row, sheet))
            self.assertEqual(copy[sheet], original[sheet], msg='{} sheets are not equal'.format(sheet))

        self.assertEqual(copy, original)

        # compare models
        model2 = Reader().run(self.filename)[Model][0]
        self.assertTrue(model2.is_equal(model))
        self.assertTrue(model.difference(model2) == '')

    def test_rate_law_expressions_with_multiple_model_types(self):
        fixture_filename = os.path.join(os.path.dirname(__file__), 'fixtures', 'example-model.xlsx')
        model = Reader().run(fixture_filename)[Model][0]
        rate_laws = model.get_rate_laws(id='AK_AMP-backward')
        self.assertEqual(len(rate_laws), 1)
        rate_law = rate_laws[0]
        self.assertEqual(len(rate_law.expression.species), 1)
        self.assertEqual(rate_law.expression.species[0].id, 'Adk_Protein[c]')
        self.assertEqual(len(rate_law.expression.parameters), 1)
        self.assertEqual(rate_law.expression.parameters[0].id, 'k_cat_rev_ak')
        self.assertEqual(len(rate_law.expression.observables), 1)
        self.assertEqual(rate_law.expression.observables[0].id, 'AXP_c')
        self.assertEqual(len(rate_law.expression.functions), 1)
        self.assertEqual(rate_law.expression.functions[0].id, 'func_1')


class TestReaderException(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test(self):
        model1 = Model(id='model1', name='test model', version='0.0.1a', wc_lang_version='0.0.1')
        model2 = Model(id='model2', name='test model', version='0.0.1a', wc_lang_version='0.0.1')
        filename = os.path.join(self.tempdir, 'model.xlsx')
        obj_tables.io.WorkbookWriter().run(filename, [model1, model2], models=Writer.MODELS, include_all_attributes=False)

        with self.assertRaisesRegex(ValueError, ' should define one model$'):
            Reader().run(filename)


class TestReadNoModel(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test(self):
        filename = os.path.join(self.tempdir, 'model.xlsx')
        obj_tables.io.WorkbookWriter().run(filename, [], models=io.Writer.MODELS, include_all_attributes=False)
        with self.assertRaisesRegex(ValueError, 'should define one model'):
            Reader().run(filename)


class ImplicitRelationshipsTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_write_parameter(self):
        model = Model(id='model', version='0.0.1', wc_lang_version='0.0.1')
        submodel = model.submodels.create(id='submodel')
        species_type = model.species_types.create(id='st', structure=ChemicalStructure(molecular_weight=1., charge=0))
        compartment = model.compartments.create(id='c')
        species = model.species.create(species_type=species_type, compartment=compartment)
        species.id = species.gen_id()
        reaction = submodel.reactions.create(id='reaction', model=model)
        reaction.participants.create(species=species, coefficient=1.)
        rate_law = reaction.rate_laws.create(model=model, direction=RateLawDirection.forward)
        rate_law.id = rate_law.gen_id()
        rate_law_eq = rate_law.expression = RateLawExpression(expression='parameter')
        parameter = rate_law_eq.parameters.create(id='parameter', value=1., units=unit_registry.parse_units('dimensionless'), model=model)

        filename = os.path.join(self.tempdir, 'model.xlsx')
        Writer().run(filename, model, data_repo_metadata=False)

        parameter.model = Model(id='model2', version='0.0.1', wc_lang_version='0.0.1')
        with self.assertRaisesRegex(ValueError, 'must be set to the instance of `Model`'):
            Writer().run(filename, model, data_repo_metadata=False)

    def test_write_other(self):
        model = Model(id='model', version='0.0.1', wc_lang_version='0.0.1')
        species_type = model.species_types.create(id='species_type')
        compartment = model.compartments.create(id='compartment')
        species = Species(
            model=model,
            species_type=species_type,
            compartment=compartment)
        species.id = species.gen_id()
        s_id = species.serialize()
        obs_expr, _ = ObservableExpression.deserialize(s_id, {Species: {s_id: species}})
        observable = model.observables.create(id='observable', expression=obs_expr)

        filename = os.path.join(self.tempdir, 'model.xlsx')
        Writer().run(filename, model, data_repo_metadata=False)

        model2 = Model(id='model2', version='0.0.1', wc_lang_version='0.0.1')
        observable.model = model2
        with self.assertRaisesRegex(ValueError, 'must be set to the instance of `Model`'):
            Writer().run(filename, model, data_repo_metadata=False)

    def test_read(self):
        filename = os.path.join(self.tempdir, 'model.xlsx')
        obj_tables.io.WorkbookWriter().run(filename, [Submodel(id='submodel')], models=Writer.MODELS, include_all_attributes=False)
        with self.assertRaisesRegex(ValueError, 'should define one model'):
            Reader().run(filename)

    def test_validate(self):
        class TestModel(obj_tables.Model):
            id = obj_tables.StringAttribute(primary=True, unique=True)

        Model.Meta.attributes['test'] = obj_tables.OneToOneAttribute(TestModel, related_name='a')
        with self.assertRaisesRegex(Exception, 'Relationships from `Model` not supported'):
            io.Writer.validate_implicit_relationships(Model)
        Model.Meta.attributes.pop('test')

        Model.Meta.related_attributes['test'] = obj_tables.OneToManyAttribute(TestModel, related_name='b')
        with self.assertRaisesRegex(Exception, 'Only one-to-one and many-to-one relationships are supported to `Model`'):
            io.Writer.validate_implicit_relationships(Model)
        Model.Meta.related_attributes.pop('test')


def remove_ws_metadata(wb):
    for sheet in wb.values():
        for row in list(sheet):
            if row and ((isinstance(row[0], str) and row[0].startswith('!!')) or
                        all(cell in ['', None] for cell in row)):
                sheet.remove(row)
            else:
                break
