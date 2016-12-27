""" Tests of command line program

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2016-12-07
:Copyright: 2016, Karr Lab
:License: MIT
"""

from capturer import CaptureOutput
from os import path
from shutil import rmtree
from tempfile import mkdtemp
from wc_lang.__main__ import App as WcLangCli
from wc_lang.core import Model
from wc_lang.io import Writer, Reader
import unittest
import wc_lang


class TestCli(unittest.TestCase):

    def setUp(self):
        self.tempdir = mkdtemp()

    def tearDown(self):
        rmtree(self.tempdir)

    def test_get_version(self):
        with CaptureOutput() as capturer:
            with WcLangCli(argv=['get-version']) as app:
                app.run()
                self.assertEqual(capturer.get_text(), wc_lang.__version__)

    def test_validate(self):
        model = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.1')
        self.assertEqual(model.validate(), None)
        filename = path.join(self.tempdir, 'model.xlsx')
        Writer().run(filename, model)

        with CaptureOutput() as capturer:
            with WcLangCli(argv=['validate', filename]) as app:
                app.run()
            self.assertEqual(capturer.get_text(), 'Model is valid')

    def test_difference(self):
        model1 = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.0')
        filename1 = path.join(self.tempdir, 'model1.xlsx')
        Writer().run(filename1, model1)

        model2 = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.0')
        filename2 = path.join(self.tempdir, 'model2.xlsx')
        Writer().run(filename2, model2)

        model3 = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.1')
        filename3 = path.join(self.tempdir, 'model3.xlsx')
        Writer().run(filename3, model3)

        with CaptureOutput() as capturer:
            with WcLangCli(argv=['difference', filename1, filename2]) as app:
                app.run()
            self.assertEqual(capturer.get_text(), 'Models are identical')

        with CaptureOutput() as capturer:
            with WcLangCli(argv=['difference', filename1, filename2, '--compare-files']) as app:
                app.run()
            self.assertEqual(capturer.get_text(), 'Models are identical')

        with CaptureOutput() as capturer:
            with WcLangCli(argv=['difference', filename1, filename3]) as app:
                app.run()
            diff = 'Objects ("model", "model") have different attribute values:\n  `wc_lang_version` are not equal:\n    0.0.0 != 0.0.1'
            self.assertEqual(capturer.get_text(), diff)

        with CaptureOutput() as capturer:
            with WcLangCli(argv=['difference', filename1, filename3, '--compare-files']) as app:
                app.run()
            diff = 'Sheet Model:\n  Row 4:\n    Cell B: 0.0.0 != 0.0.1'
            self.assertEqual(capturer.get_text(), diff)

    def test_transform(self):
        source = path.join(self.tempdir, 'source.xlsx')
        model = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.0')
        Writer().run(source, model)

        destination = path.join(self.tempdir, 'destination.xlsx')
        with WcLangCli(argv=['transform', source, destination, '--transform', 'MergeAlgorithmicallyLikeSubmodels']) as app:
            app.run()

        self.assertTrue(path.isfile(destination))

    def test_normalize(self):
        filename_xls_1 = path.join(self.tempdir, 'model-1.xlsx')
        filename_xls_2 = path.join(self.tempdir, 'model-2.xlsx')

        model = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.0')
        Writer().run(filename_xls_1, model)

        # with same destination
        with WcLangCli(argv=['normalize', filename_xls_1]) as app:
            app.run()

        model2 = Reader().run(filename_xls_1)
        self.assertEqual(model2, model)

        # with different destination
        with WcLangCli(argv=['normalize', filename_xls_1, '--destination', filename_xls_2]) as app:
            app.run()

        model2 = Reader().run(filename_xls_2)
        self.assertEqual(model2, model)

    def test_convert(self):
        filename_xls = path.join(self.tempdir, 'model.xlsx')
        filename_csv = path.join(self.tempdir, 'model-*.csv')

        model = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.0')
        Writer().run(filename_xls, model)

        with WcLangCli(argv=['convert', filename_xls, filename_csv]) as app:
            app.run()

        self.assertTrue(path.isfile(path.join(self.tempdir, 'model-Model.csv')))

    def test_create_template(self):
        filename = path.join(self.tempdir, 'template.xlsx')

        with WcLangCli(argv=['create-template', filename]) as app:
            app.run()

        self.assertTrue(path.isfile(filename))

    def test_update_wc_lang_version(self):
        filename = path.join(self.tempdir, 'model.xlsx')

        model = Model(id='model', name='test model', version='0.0.1a', wc_lang_version='0.0.0')
        self.assertNotEqual(model.wc_lang_version, wc_lang.__version__)
        Writer().run(filename, model)

        with WcLangCli(argv=['update-wc-lang-version', filename]) as app:
            app.run()

        model = Reader().run(filename)
        self.assertEqual(model.wc_lang_version, wc_lang.__version__)