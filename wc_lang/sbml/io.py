""" Reading/writing a WC model to/from an SBML representation

Representations include
* Files
* Strings

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2017-09-22
:Copyright: 2017, Karr Lab
:License: MIT
"""

import sys
from os.path import split, splitext, join
from six import iteritems
from libsbml import readSBMLFromString, writeSBMLToFile, SBMLNamespaces, SBMLDocument

from obj_model.core import Validator
from wc_lang.core import (Model, Taxon, Submodel, ObjectiveFunction, Compartment, SpeciesType,
    Species, Concentration, Reaction, ReactionParticipant, RateLaw, RateLawEquation,
    BiomassComponent, BiomassReaction, Parameter, Reference, CrossReference, SubmodelAlgorithm)
from wc_lang.sbml.util import (wrap_libsbml, wrap_libsbml_pass_text, init_sbml_model,
    SBML_LEVEL, SBML_VERSION, create_sbml_doc_w_fbc)

'''
wc_lang to SBML mapping to support FBA modeling
Individual wc_lang submodels that use dFBA are mapped to individual SBML documents and files.

WC			            SBML                                                Status
-----                   -----                                               ------
Model                   Model                                               Ignored
Taxon			        None, perhaps make SBML annotations                 Ignored
Submodel			    Model                                               Implemented
ObjectiveFunction       Objective                                           Mostly Implemented
Compartment			    Compartment                                         Implemented
SpeciesType			    SpeciesType aren't defined                          NA
Species			        Species                                             Implemented
Concentration			Concentrations are incorporated in Species          NA
Reaction			    Reaction, with FbcReactionPlugin for DFBA submodels Implemented
ReactionParticipant		SpeciesReference in a Reaction                      Implemented
RateLaw			        KineticLaw                                          Ignored
RateLawEquation			
BiomassComponent
BiomassReaction			                                                    TBD
Parameter			    Parameter                                           Implemented
Reference			    
CrossReference			

wc_lang attribute to SBML mapping:

WC Model			    SBML Model
--------                ----------
comments                notes
references              notes, as a Python dict
'''

class Reader(object):
    """ Read model objects from an SBML representation """

    @staticmethod
    def run(self, objects, models, path=None, get_related=True,
        title=None, description=None, keywords=None, version=None,
        language=None, creator=None):
        """ Write a list of model objects to a string or a file in an SBML format.

        Args:
            objects (:obj:`list`): list of objects
            models (:obj:`list`): list of model, in the order that they should
                appear as worksheets; all models which are not in `models` will
                follow in alphabetical order
            path (:obj:`str`, optional): path of SBML file to write
            title (:obj:`str`, optional): title
            description (:obj:`str`, optional): description
            keywords (:obj:`str`, optional): keywords
            version (:obj:`str`, optional): version
            language (:obj:`str`, optional): language
            creator (:obj:`str`, optional): creator
        """
        pass

class Writer(object):
    """ Write an SBML representation of a model  """

    @staticmethod
    def run(model, algorithms=None, path=None):
        """ Write the `model`'s submodels in SBML.

        Each `Submodel` in `Model` `model` whose algorithm is in `algorithms`
        is converted into a separate SBML document.
        If `path` is None, then the SBML is returned in string(s), otherwise it's written to file(s)
        which are named `path + submodel.id + suffix'.

        Args:
            model (:obj:`Model`): a `Model`
            algorithms (:obj:`list`, optional): list of `SubmodelAlgorithm` attributes, defaulting
                to `[SubmodelAlgorithm.dfba]`
            path (:obj:`str`, optional): prefix of path of SBML file(s) to write

        Returns:
            :obj:`dict` of `str`:
                if `path` is None, a dictionary SBML documents as strings, indexed by submodel ids,
                otherwise a list of SBML file(s) created
        """
        if algorithms is None:
            algorithms = [SubmodelAlgorithm.dfba]
        sbml_documents = {}
        for submodel in model.get_submodels():
            if submodel.algorithm in algorithms:
                objects = [submodel, submodel.objective_function] + \
                    model.get_compartments() + \
                    submodel.get_species() + submodel.parameters + submodel.reactions
                sbml_documents[submodel.id] = SBMLExchange.write(objects)
        if not sbml_documents:
            raise ValueError("No submodel.algorithm in algorithms '{}'.".format(algorithms))
        if path is None:
            return sbml_documents
        else:
            ext = '.sbml'
            (dirname, basename) = split(path)
            files = []
            import os
            try:
                print(dirname, 'contains', os.listdir(dirname))
            except:
                print('could not list', dirname)
            for id,sbml_doc in iteritems(sbml_documents):
                dest = join(dirname, basename + '-' + id + ext)
                files.append(dest)
                if not writeSBMLToFile(sbml_doc, dest):
                    raise ValueError("SBML document for submodel '{}' could not be written to '{}'.".format(
                        id, dest))
            return files

class SBMLExchange(object):
    """ Exchange `wc_lang` model to/from a libSBML SBML representation """

    @staticmethod
    def write(objects):
        """ Write the `wc_lang` model described by `objects` to a libSBML `SBMLDocument`.

        Warning: `wc_lang` and SBML semantics are not equivalent. Thus, this
        `wc_lang` information will not be written:
        * xxx

        # TODO: elaborate

        Args:
            objects (:obj:`list`): list of objects

        Returns:
            :obj:`SBMLDocument`: an SBMLDocument containing `objects`

        Raises:
            :obj:`ValueError`: if the SBMLDocument cannot be created
            # TODO: elaborate
        """
        # Create an empty SBMLDocument object.
        sbml_document = create_sbml_doc_w_fbc()

        # Create the SBML Model object inside the SBMLDocument object.
        sbml_model = init_sbml_model(sbml_document)

        '''
        Algorithm:
            * validate objects
            * (do not add related objects, as only certain model types can be written to SBML)
            * group objects by model class
            * add objects to the SBML document in dependent order
        '''
        error = Validator().run(objects)
        if error:
            warn('Some data will not be written because objects are not valid:\n  {}'.format(
                str(error).replace('\n', '\n  ').rstrip()))

        grouped_objects = {}
        for obj in objects:
            obj_class = obj.__class__
            if obj_class not in grouped_objects:
                grouped_objects[obj_class] = []
            if obj not in grouped_objects[obj_class]:
                grouped_objects[obj_class].append(obj)

        # Dependencies among models create a partial order constraint on writing them:
        #     Submodel depends on nothing
        #     Compartment depends on nothing
        #     Parameter depends on nothing
        #     Compartment must precede Species
        #     Compartment must precede Reaction
        #     Species must precede Reaction
        #     Reaction must precede ObjectiveFunction
        # This partial order is satisfied by this sequence:
        model_order = [Submodel, Compartment, Parameter, Species, Reaction, ObjectiveFunction]

        # add objects into SBMLDocument
        for model in model_order:
            if model in grouped_objects:
                for obj in grouped_objects[model]:
                    obj.add_to_sbml_doc(sbml_document)

        return sbml_document

    @staticmethod
    def read(document):
        """ Read a model in a libSBML `SBMLDocument` into a `wc_lang` model.

        Warning: `wc_lang` and SBML semantics are not equivalent. Thus, this
        SBML information will not be read:
        * xxx

        Args:
            document (:obj:`SBMLDocument`): representation of an SBML model

        Returns:
            :obj:`dict`: model objects grouped by `Model`

        Raises:
            :obj:`ValueError`: if ...
        """
        pass