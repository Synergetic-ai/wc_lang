""" Data model to represent biochemical models.

This module defines classes that represent the schema of a biochemical model:

* :obj:`Taxon`
* :obj:`Model`
* :obj:`Submodel`
* :obj:`ObjectiveFunction`
* :obj:`Compartment`
* :obj:`SpeciesType`
* :obj:`Species`
* :obj:`Concentration`
* :obj:`Reaction`
* :obj:`SpeciesCoefficient`
* :obj:`RateLaw`
* :obj:`RateLawEquation`
* :obj:`BiomassComponent`
* :obj:`BiomassReaction`
* :obj:`Parameter`
* :obj:`Reference`
* :obj:`DatabaseReference`

These are all instances of `obj_model.Model`, an alias for `obj_model.Model`.
A biochemical model may contain a list of instances of each of these classes, interlinked
by object references. For example, a :obj:`Reaction` will reference its constituent
:obj:`SpeciesCoefficient` instances, and the :obj:`RateLaw` that describes the reaction's rate.

This module also defines numerous classes that serve as attributes of these classes.

:Author: Jonathan Karr <karr@mssm.edu>
:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2016-11-10
:Copyright: 2016-2017, Karr Lab
:License: MIT
"""
# TODO: for determinism, replace remaining list(set(list1)) expressions with det_dedupe(list1) in other packages

from enum import Enum, EnumMeta
from itertools import chain
from math import ceil, floor, exp, log, log10, isnan
from natsort import natsorted, ns
from six import with_metaclass, string_types
import collections
import pkg_resources
import re
import six
import sys
import token

from obj_model import (BooleanAttribute, EnumAttribute, FloatAttribute, IntegerAttribute, PositiveIntegerAttribute,
                       RegexAttribute, SlugAttribute, StringAttribute, LongStringAttribute, UrlAttribute,
                       OneToOneAttribute, ManyToOneAttribute, ManyToManyAttribute, OneToManyAttribute,
                       InvalidModel, InvalidObject, InvalidAttribute, TabularOrientation)
import obj_model
from wc_utils.util.enumerate import CaseInsensitiveEnum, CaseInsensitiveEnumMeta
from wc_utils.util.list import det_dedupe
from wc_lang.sbml.util import (wrap_libsbml, str_to_xmlstr, LibSBMLError,
                               init_sbml_model, create_sbml_parameter, add_sbml_unit)
from wc_lang.expression_utils import (RateLawUtils, WcLangExpression, WcLangExpressionError,
                                      LinearExpressionVerifier)

with open(pkg_resources.resource_filename('wc_lang', 'VERSION'), 'r') as file:
    wc_lang_version = file.read().strip()

# wc_lang generates obj_model SchemaWarning warnings because some Models lack primary attributes.
# These models include :obj:`RateLaw`, :obj:`SpeciesCoefficient`, :obj:`RateLawEquation`, and :obj:`Species`.
# However, these are not needed by the workbook and delimiter-separated representations of
# models on disk. Therefore, suppress the warnings.
import warnings
warnings.filterwarnings('ignore', '', obj_model.SchemaWarning, 'obj_model')

# configuration
import wc_lang.config.core
config_wc_lang = wc_lang.config.core.get_config()['wc_lang']

EXTRACELLULAR_COMPARTMENT_ID = config_wc_lang['EXTRACELLULAR_COMPARTMENT_ID']


class TaxonRankMeta(CaseInsensitiveEnumMeta):

    def __getattr__(cls, name):
        """ Get value by name

        Args:
            name (:obj:`str`): attribute name

        Returns:
            :obj:`TaxonRank`: taxonomic rank
        """
        if name.lower() == 'class':
            name = 'classis'
        return super(TaxonRankMeta, cls).__getattr__(name)

    def __getitem__(cls, name):
        """ Get value by name

        Args:
            name (:obj:`str`): attribute name

        Returns:
            :obj:`TaxonRank`: taxonomic rank
        """
        lower_name = name.lower()

        if lower_name in ['varietas', 'strain']:
            name = 'variety'
        elif lower_name == 'tribus':
            name = 'tribe'
        elif lower_name == 'familia':
            name = 'family'
        elif lower_name == 'ordo':
            name = 'order'
        elif lower_name == 'class':
            name = 'classis'
        elif lower_name in ['division', 'divisio']:
            name = 'phylum'
        elif lower_name == 'regnum':
            name = 'kingdom'
        return super(TaxonRankMeta, cls).__getitem__(name)


class TaxonRank(with_metaclass(TaxonRankMeta, int, Enum)):
    """ Taxonomic ranks """
    domain = 1
    kingdom = 2
    phylum = 3
    classis = 4
    order = 5
    family = 6
    tribe = 7
    genus = 8
    species = 9
    variety = 10


class SubmodelAlgorithm(int, CaseInsensitiveEnum):
    """ Submodel algorithms """
    dfba = 1
    ode = 2
    ssa = 3


class SpeciesTypeType(int, CaseInsensitiveEnum):
    """ Types of species types """
    metabolite = 1
    protein = 2
    dna = 3
    rna = 4
    pseudo_species = 5


ConcentrationUnit = Enum('ConcentrationUnit', type=int, names=[
    ('molecules', 1),
    ('M', 2),
    ('mM', 3),
    ('uM', 4),
    ('nM', 5),
    ('pM', 6),
    ('fM', 7),
    ('aM', 8),
    ('mol dm^-2', 9),
])
ConcentrationUnit.Meta = {
    ConcentrationUnit['molecules']: {
        'xml_id': 'molecules',
        'substance_units': {'kind': 'item', 'exponent': 1, 'scale': 0},
        'volume_units': None,
    },
    ConcentrationUnit['M']: {
        'xml_id': 'M',
        'substance_units': {'kind': 'mole', 'exponent': 1, 'scale': 0},
        'volume_units': {'kind': 'litre', 'exponent': -1, 'scale': 0},
    },
    ConcentrationUnit['mM']: {
        'xml_id': 'mM',
        'substance_units': {'kind': 'mole', 'exponent': 1, 'scale': -3},
        'volume_units': {'kind': 'litre', 'exponent': -1, 'scale': 0},
    },
    ConcentrationUnit['uM']: {
        'xml_id': 'uM',
        'substance_units': {'kind': 'mole', 'exponent': 1, 'scale': -6},
        'volume_units': {'kind': 'litre', 'exponent': -1, 'scale': 0},
    },
    ConcentrationUnit['nM']: {
        'xml_id': 'nM',
        'substance_units': {'kind': 'mole', 'exponent': 1, 'scale': -9},
        'volume_units': {'kind': 'litre', 'exponent': -1, 'scale': 0},
    },
    ConcentrationUnit['pM']: {
        'xml_id': 'pM',
        'substance_units': {'kind': 'mole', 'exponent': 1, 'scale': -12},
        'volume_units': {'kind': 'litre', 'exponent': -1, 'scale': 0},
    },
    ConcentrationUnit['fM']: {
        'xml_id': 'fM',
        'substance_units': {'kind': 'mole', 'exponent': 1, 'scale': -15},
        'volume_units': {'kind': 'litre', 'exponent': -1, 'scale': 0},
    },
    ConcentrationUnit['aM']: {
        'xml_id': 'aM',
        'substance_units': {'kind': 'mole', 'exponent': 1, 'scale': -18},
        'volume_units': {'kind': 'litre', 'exponent': -1, 'scale': 0},
    },
    ConcentrationUnit['mol dm^-2']: {
        'xml_id': 'mol_per_dm_2',
        'substance_units': {'kind': 'mole', 'exponent': 1, 'scale': 0},
        'volume_units': {'kind': 'metre', 'exponent': -2, 'scale': -1},
    },
}


class RateLawDirection(int, CaseInsensitiveEnum):
    """ Rate law directions """
    backward = -1
    forward = 1


class ReferenceType(int, CaseInsensitiveEnum):
    """ Reference types """
    article = 1
    book = 2
    online = 3
    proceedings = 4
    thesis = 5

    inbook = 6
    incollection = 7
    inproceedings = 8

    misc = 9


class ObjectiveFunctionAttribute(ManyToOneAttribute):
    """ Objective function attribute """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(ObjectiveFunctionAttribute, self).__init__('ObjectiveFunction',
                                                         related_name=related_name,
                                                         verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, value, encoded=None):
        """ Serialize related object

        Args:
            value (:obj:`ObjectiveFunction`): the referenced ObjectiveFunction
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation
        """
        if value is None:
            return None
        else:
            return value.serialize()

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        return ObjectiveFunction.deserialize(self, value, objects)


class ReactionParticipantAttribute(ManyToManyAttribute):
    """ Reaction participants """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(ReactionParticipantAttribute, self).__init__('SpeciesCoefficient', related_name=related_name,
                                                           min_related=1,
                                                           verbose_name=verbose_name,
                                                           verbose_related_name=verbose_related_name,
                                                           help=help)

    def serialize(self, participants, encoded=None):
        """ Serialize related object

        Args:
            participants (:obj:`list` of :obj:`SpeciesCoefficient`): Python representation of reaction participants
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation
        """
        if not participants:
            return ''

        comps = set([part.species.compartment for part in participants])
        if len(comps) == 1:
            global_comp = comps.pop()
        else:
            global_comp = None

        if global_comp:
            participants = natsorted(participants, lambda part: part.species.species_type.id, alg=ns.IGNORECASE)
        else:
            participants = natsorted(participants, lambda part: (
                part.species.species_type.id, part.species.compartment.id), alg=ns.IGNORECASE)

        lhs = []
        rhs = []
        for part in participants:
            if part.coefficient < 0:
                lhs.append(part.serialize(show_compartment=global_comp is None, show_coefficient_sign=False))
            elif part.coefficient > 0:
                rhs.append(part.serialize(show_compartment=global_comp is None, show_coefficient_sign=False))

        if global_comp:
            return '[{}]: {} ==> {}'.format(global_comp.get_primary_attribute(), ' + '.join(lhs), ' + '.join(rhs))
        else:
            return '{} ==> {}'.format(' + '.join(lhs), ' + '.join(rhs))

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of `list` of `SpeciesCoefficient`, `InvalidAttribute` or `None`: tuple of cleaned value
                and cleaning error
        """
        errors = []

        id = r'[a-z][a-z0-9_]*'
        stoch = r'\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\)'
        gbl_part = r'({} *)*({})'.format(stoch, id)
        lcl_part = r'({} *)*({}\[{}\])'.format(stoch, id, id)
        gbl_side = r'{}( *\+ *{})*'.format(gbl_part, gbl_part)
        lcl_side = r'{}( *\+ *{})*'.format(lcl_part, lcl_part)
        gbl_pattern = r'^\[({})\]: *({}|) *==> *({}|)$'.format(id, gbl_side, gbl_side)
        lcl_pattern = r'^({}|) *==> *({}|)$'.format(lcl_side, lcl_side)

        value = value.strip(' ')
        global_match = re.match(gbl_pattern, value, flags=re.I)
        local_match = re.match(lcl_pattern, value, flags=re.I)

        if global_match:
            if global_match.group(1) in objects[Compartment]:
                global_comp = objects[Compartment][global_match.group(1)]
            else:
                global_comp = None
                errors.append('Undefined compartment "{}"'.format(global_match.group(1)))
            lhs = global_match.group(2)
            rhs = global_match.group(14)

        elif local_match:
            global_comp = None
            lhs = local_match.group(1)
            rhs = local_match.group(13)

        else:
            return (None, InvalidAttribute(self, ['Incorrectly formatted participants: {}'.format(value)]))

        lhs_parts, lhs_errors = self.deserialize_side(-1., lhs, objects, global_comp)
        rhs_parts, rhs_errors = self.deserialize_side(1., rhs, objects, global_comp)

        parts = lhs_parts + rhs_parts
        errors.extend(lhs_errors)
        errors.extend(rhs_errors)

        if errors:
            return (None, InvalidAttribute(self, errors))
        return (parts, None)

    def deserialize_side(self, direction, value, objects, global_comp):
        """ Deserialize the LHS or RHS of a reaction equation

        Args:
            direction (:obj:`float`): -1. indicates LHS, +1. indicates RHS
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            global_comp (:obj:`Compartment`): global compartment of the reaction
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple`:

                * :obj:`list` of :obj:`SpeciesCoefficient`: list of species coefficients
                * :obj:`list` of :obj:`Exception`: list of errors
        """
        parts_str = re.findall(r'(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*)(\[([a-z][a-z0-9_]*)\])*', value, flags=re.I)

        if global_comp:
            temp = [part[4] for part in parts_str]
        else:
            temp = [part[4] + '[' + part[6] + ']' for part in parts_str]
        repeated_parts = [item for item, count in collections.Counter(temp).items() if count > 1]
        if repeated_parts:
            return ([], ['Participants are repeated\n  {}'.format('\n  '.join(repeated_parts))])

        parts = []
        errors = []
        for part in parts_str:
            part_errors = []

            if part[4] in objects[SpeciesType]:
                species_type = objects[SpeciesType][part[4]]
            else:
                part_errors.append('Undefined species type "{}"'.format(part[4]))

            if global_comp:
                compartment = global_comp
            elif part[6] in objects[Compartment]:
                compartment = objects[Compartment][part[6]]
            else:
                part_errors.append('Undefined compartment "{}"'.format(part[6]))

            coefficient = direction * float(part[1] or 1.)

            if part_errors:
                errors += part_errors
            else:
                species_id = Species.gen_id(species_type.id, compartment.id)
                species, error = Species.deserialize(species_id, objects)
                if error:
                    raise ValueError('Invalid species "{}"'.format(species_id)
                                     )  # pragma: no cover; unreachable due to above error checking of species types and compartments

                if coefficient != 0:
                    if SpeciesCoefficient not in objects:
                        objects[SpeciesCoefficient] = {}
                    serialized_value = SpeciesCoefficient._serialize(species, coefficient)
                    if serialized_value in objects[SpeciesCoefficient]:
                        rxn_part = objects[SpeciesCoefficient][serialized_value]
                    else:
                        rxn_part = SpeciesCoefficient(species=species, coefficient=coefficient)
                        objects[SpeciesCoefficient][serialized_value] = rxn_part
                    parts.append(rxn_part)

        return (parts, errors)

    def validate(self, obj, value):
        """ Determine if `value` is a valid value of the attribute

        Args:
            obj (:obj:`Reaction`): object being validated
            value (:obj:`list` of :obj:`SpeciesCoefficient`): value of attribute to validate

        Returns:
            :obj:`InvalidAttribute` or None: None if attribute is valid, other return list of errors as an instance of `InvalidAttribute`
        """
        error = super(ReactionParticipantAttribute, self).validate(obj, value)
        if error:
            return error

        # check that LHS and RHS are different
        net_coeffs = {}
        for spec_coeff in value:
            net_coeffs[spec_coeff.species] = \
                net_coeffs.get(spec_coeff.species, 0) + \
                spec_coeff.coefficient
            if net_coeffs[spec_coeff.species] == 0:
                net_coeffs.pop(spec_coeff.species)
        if not net_coeffs:
            return InvalidAttribute(self, ['LHS and RHS must be different'])
        return None


class RateLawEquationAttribute(ManyToOneAttribute):
    """ Rate law equation """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(RateLawEquationAttribute, self).__init__('RateLawEquation',
                                                       related_name=related_name, min_related=1, min_related_rev=1,
                                                       verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, rate_law_equation, encoded=None):
        """ Serialize related object

        Args:
            rate_law_equation (:obj:`RateLawEquation`): the related `RateLawEquation`
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation of the rate law equation
        """
        return rate_law_equation.serialize()

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        return RateLawEquation.deserialize(self, value, objects)


class FunctionExpressionAttribute(ManyToOneAttribute):
    """ Function expression attribute """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super().__init__('FunctionExpression',
                         related_name=related_name, min_related=1, min_related_rev=1,
                         verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, function_expression, encoded=None):
        """ Serialize related object

        Args:
            function_expression (:obj:`FunctionExpression`): the referenced `FunctionExpression`
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation
        """
        return function_expression.serialize()

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        return FunctionExpression.deserialize(self, value, objects)


class StopConditionExpressionAttribute(ManyToOneAttribute):
    """ StopCondition expression attribute """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super().__init__('StopConditionExpression',
                         related_name=related_name, min_related=1, min_related_rev=1,
                         verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, stop_condition_expression, encoded=None):
        """ Serialize related object

        Args:
            stop_condition_expression (:obj:`StopConditionExpression`): the referenced `StopConditionExpression`
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation
        """
        return stop_condition_expression.serialize()

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        return StopConditionExpression.deserialize(self, value, objects)


class ObservableExpressionAttribute(ManyToOneAttribute):
    """ Observable expression attribute """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super().__init__('ObservableExpression',
                         related_name=related_name, min_related=1, min_related_rev=1,
                         verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, observable_expression, encoded=None):
        """ Serialize related object

        Args:
            observable_expression (:obj:`ObservableExpression`): the referenced `ObservableExpression`
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation
        """
        return observable_expression.serialize()

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        return ObservableExpression.deserialize(self, value, objects)


class Model(obj_model.Model):
    """ Model

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        version (:obj:`str`): version of the model
        url (:obj:`str`): url of the model Git repository
        branch (:obj:`str`): branch of the model Git repository
        revision (:obj:`str`): revision of the model Git repository
        wc_lang_version (:obj:`str`): version of ``wc_lang``
        comments (:obj:`str`): comments

    Related attributes:
        taxon (:obj:`Taxon`): taxon
        submodels (:obj:`list` of :obj:`Submodel`): submodels
        compartments (:obj:`list` of :obj:`Compartment`): compartments
        species_types (:obj:`list` of :obj:`SpeciesType`): species types
        functions (:obj:`list` of :obj:`Function`): functions
        observables (:obj:`list` of :obj:`Observable`): observables
        parameters (:obj:`list` of :obj:`Parameter`): parameters
        stop_conditions (:obj:`list` of :obj:`StopCondition`): stop conditions
        references (:obj:`list` of :obj:`Reference`): references
        database_references (:obj:`list` of :obj:`DatabaseReference`): database references
    """
    id = SlugAttribute()
    name = StringAttribute()
    version = RegexAttribute(min_length=1, pattern=r'^[0-9]+\.[0-9+]\.[0-9]+', flags=re.I)
    url = obj_model.core.StringAttribute(verbose_name='URL')
    branch = obj_model.core.StringAttribute()
    revision = obj_model.core.StringAttribute()
    wc_lang_version = RegexAttribute(min_length=1, pattern=r'^[0-9]+\.[0-9+]\.[0-9]+', flags=re.I,
                                     default=wc_lang_version, verbose_name='wc_lang version')
    comments = LongStringAttribute()

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name', 'version', 'url', 'branch', 'revision', 'wc_lang_version', 'comments')
        tabular_orientation = TabularOrientation.column

    def get_compartments(self, __type=None, **kwargs):
        """ Get all compartments

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Compartment`: compartments
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        return self.compartments.get(__type=__type, **kwargs)

    def get_species_types(self, __type=None, **kwargs):
        """ Get all species types

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`SpeciesType`: species types
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        return self.species_types.get(__type=__type, **kwargs)

    def get_submodels(self, __type=None, **kwargs):
        """ Get all submodels

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Submodel`: submodels
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        return self.submodels.get(__type=__type, **kwargs)

    def get_species(self, __type=None, **kwargs):
        """ Get all species from submodels

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Species`: species
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        species = []

        for submodel in self.submodels:
            species.extend(submodel.get_species(__type=__type, **kwargs))

        for concentation in self.get_concentrations():
            if concentation.species.has_attr_vals(__type=__type, **kwargs):
                species.append(concentation.species)

        return det_dedupe(species)

    def get_concentrations(self, __type=None, **kwargs):
        """ Get all concentrations from species types

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Concentration`: concentations
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        concentrations = []
        for species_type in self.species_types:
            for species in species_type.species:
                if species.concentration and species.concentration.has_attr_vals(__type=__type, **kwargs):
                    concentrations.append(species.concentration)
        return concentrations

    def get_reactions(self, __type=None, **kwargs):
        """ Get all reactions from submodels

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Reaction`: reactions
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        reactions = []
        for submodel in self.submodels:
            reactions.extend(submodel.reactions.get(__type=__type, **kwargs))
        return reactions

    def get_biomass_reactions(self, __type=None, **kwargs):
        """ Get all biomass reactions used by submodels

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`BiomassReaction`: biomass reactions
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        biomass_reactions = []
        for submodel in self.submodels:
            for biomass_reaction in submodel.biomass_reactions:
                if biomass_reaction.has_attr_vals(__type=__type, **kwargs):
                    biomass_reactions.append(biomass_reaction)
        return det_dedupe(biomass_reactions)

    def get_rate_laws(self, __type=None, **kwargs):
        """ Get all rate laws from reactions

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`RateLaw`: rate laws
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        rate_laws = []
        for reaction in self.get_reactions():
            rate_laws.extend(reaction.rate_laws.get(__type=__type, **kwargs))
        return det_dedupe(rate_laws)

    def get_parameters(self, __type=None, **kwargs):
        """ Get all parameters from model and submodels

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Parameter`: parameters
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        parameters = self.parameters.get(__type=__type, **kwargs)
        for submodel in self.submodels:
            parameters.extend(submodel.parameters.get(__type=__type, **kwargs))
        return det_dedupe(parameters)

    def get_references(self, __type=None, **kwargs):
        """ Get all references from model and children

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Reference`: references
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        refs = []

        refs.extend(self.references.get(__type=__type, **kwargs))

        if self.taxon:
            refs.extend(self.taxon.references.get(__type=__type, **kwargs))

        for compartment in self.compartments:
            refs.extend(compartment.references.get(__type=__type, **kwargs))

        for species_type in self.species_types:
            refs.extend(species_type.references.get(__type=__type, **kwargs))

        for concentration in self.get_concentrations():
            refs.extend(concentration.references.get(__type=__type, **kwargs))

        for submodel in self.submodels:
            refs.extend(submodel.references.get(__type=__type, **kwargs))

        for reaction in self.get_reactions():
            refs.extend(reaction.references.get(__type=__type, **kwargs))

        for rate_law in self.get_rate_laws():
            refs.extend(rate_law.references.get(__type=__type, **kwargs))

        for parameter in self.get_parameters():
            refs.extend(parameter.references.get(__type=__type, **kwargs))

        return det_dedupe(refs)

    def get_component(self, type, id):
        """ Find model component of `type` with `id`

        Args:
            type (:obj:`str`) type of component to find
            id (:obj:`str`): id of component to find

        Returns:
            :obj:`obj_model.Model`: component with `id`, or `None` if there is no component with `id`=`id`
        """
        types = ['compartment', 'species_type', 'submodel', 'reaction', 'biomass_reaction',
                 'parameter', 'reference']
        if type not in types:
            raise ValueError("Type '{}' not one of '{}'".format(type, ', '.join(types)))

        components = getattr(self, 'get_{}s'.format(type))()
        return next((c for c in components if c.id == id), None)


class Taxon(obj_model.Model):
    """ Biological taxon (e.g. family, genus, species, strain, etc.)

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        rank (:obj:`TaxonRank`): rank
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references

    Related attributes:
        database_references (:obj:`list` of :obj:`DatabaseReference`): database references
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = OneToOneAttribute(Model, related_name='taxon')
    rank = EnumAttribute(TaxonRank, default=TaxonRank.species)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='taxa')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name',
                           'rank',
                           'comments', 'references')
        tabular_orientation = TabularOrientation.column


class Submodel(obj_model.Model):
    """ Submodel

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        algorithm (:obj:`SubmodelAlgorithm`): algorithm        
        objective_function (:obj:`ObjectiveFunction`, optional): objective function for a dFBA submodel;
            if not initialized, then `biomass_reaction` is used as the objective function
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references

    Related attributes:
        database_references (:obj:`list` of :obj:`DatabaseReference`): database references
        reactions (:obj:`list` of :obj:`Reaction`): reactions
        biomass_reactions (:obj:`list` of :obj:`BiomassReaction`): the growth reaction for a dFBA submodel
        parameters (:obj:`list` of :obj:`Parameter`): parameters
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='submodels')
    algorithm = EnumAttribute(SubmodelAlgorithm, default=SubmodelAlgorithm.ssa)    
    objective_function = ObjectiveFunctionAttribute(related_name='submodels')
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='submodels')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name',
                           'algorithm', 'objective_function', 
                           'comments', 'references')
        indexed_attrs_tuples = (('id',), )

    def get_species(self, __type=None, **kwargs):
        """ Get species in reactions

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Species`: species in reactions
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        species = []

        for rxn in self.reactions:
            species.extend(rxn.get_species(__type=__type, **kwargs))

        return det_dedupe(species)

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Submodel to a libsbml SBML document as a `libsbml.model`.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.model`: the libsbml model

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml(sbml_document.getModel)
        wrap_libsbml(sbml_model.setIdAttribute, self.id)
        if self.name:
            wrap_libsbml(sbml_model.setName, self.name)
        # compartment, objective_function, and parameters are created separately
        if self.comments:
            wrap_libsbml(sbml_model.appendNotes, str_to_xmlstr(self.comments))
        return sbml_model


class ObjectiveFunction(obj_model.Model):
    """ Objective function

    Attributes:
        expression (:obj:`str`): input mathematical expression of the objective function
        analyzed_expr (:obj:`WcLangExpression`): an analyzed expression
        linear (:obj:`bool`): indicates whether objective function is linear function of reaction fluxes
        reactions (:obj:`list` of :obj:`Reaction`): if linear, reactions whose fluxes are used in the
            objective function
        reaction_coefficients (:obj:`list` of :obj:`float`): parallel list of coefficients for reactions
        biomass_reactions (:obj:`list` of :obj:`BiomassReaction`): if linear, biomass reactions whose
            fluxes are used in the objective function
        biomass_reaction_coefficients (:obj:`list` of :obj:`float`): parallel list of coefficients for
            reactions in biomass_reactions

    Related attributes:
        submodel (:obj:`Submodel`): the `Submodel` which uses this `ObjectiveFunction`
    """
    linear = BooleanAttribute()
    expression = LongStringAttribute()
    reactions = ManyToManyAttribute('Reaction', related_name='objective_functions')
    biomass_reactions = ManyToManyAttribute('BiomassReaction', related_name='objective_functions')

    class Meta(obj_model.Model.Meta):
        """
        Attributes:
            valid_functions (:obj:`tuple` of `builtin_function_or_method`): tuple of functions that
                can be used in this `ObjectiveFunction`s `expression`
            valid_used_models (:obj:`tuple` of `str`): names of `obj_model.Model`s in this module that an
                `ObjectiveFunction` is allowed to reference in its `expression`
        """
        attribute_order = ('linear', 'expression', 'reactions', 'biomass_reactions')
        tabular_orientation = TabularOrientation.inline
        # because objective functions must be continuous, the functions they use must be as well
        valid_functions = (exp, pow, log, log10)
        valid_used_models = ('Parameter', 'Observable', 'Reaction', 'BiomassReaction')

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return self.expression

    @classmethod
    def deserialize(cls, attribute, value, objects):
        """ Deserialize value

        Args:
            attribute (:obj:`Attribute`): attribute
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of all `Model` objects, grouped by model

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        # if value is None don't create an ObjectiveFunction
        if value is None:
            # wc_lang.prepare.Prepare() will instantiate an ObjectiveFunction with the biomass reaction
            return (None, None)

        # parse identifiers
        pattern = '(^|[^a-z0-9_])({})([^a-z0-9_]|$)'.format(SlugAttribute().pattern[1:-1])
        identifiers = []
        for match in re.findall(pattern, value, flags=re.I):
            identifiers.append(match[1])

        # allocate identifiers between reactions and biomass_reactions
        reactions_dict = objects[Reaction]
        reaction_ids = reactions_dict.keys()
        reactions = []
        biomass_reactions_dict = objects[BiomassReaction]
        biomass_reaction_ids = biomass_reactions_dict.keys()
        biomass_reactions = []
        valid_functions_names = set(map(lambda f: f.__name__, cls.Meta.valid_functions))
        errors = []

        # do not allow Reaction or BiomassReaction instances with ids equal to a valid_function
        invalid_reaction_ids = valid_functions_names & set(reaction_ids) & set(identifiers)
        if invalid_reaction_ids:
            errors.append("reaction id(s) {{{}}} ambiguous between a Reaction and a "
                          "valid function in '{}'".format(', '.join(list(invalid_reaction_ids)), value))
        invalid_biomass_reaction_ids = valid_functions_names & set(biomass_reaction_ids) & set(identifiers)
        if invalid_biomass_reaction_ids:
            errors.append("reaction id(s) {{{}}} ambiguous between a BiomassReaction "
                          "and a valid function in '{}'".format(', '.join(list(invalid_biomass_reaction_ids)), value))

        for id in identifiers:

            if id in valid_functions_names:
                continue

            is_reaction = id in reaction_ids
            is_biomass_reaction = id in biomass_reaction_ids

            # redundant names
            # TODO: prevent this in a check method
            if is_reaction and is_biomass_reaction:
                errors.append("id '{}' ambiguous between a Reaction and a "
                              "BiomassReaction in '{}'".format(id, value))

            # missing reaction
            if not (is_reaction or is_biomass_reaction):
                errors.append("id '{}' not a Reaction or a "
                              "BiomassReaction identifier in '{}'".format(id, value))

            if is_reaction:
                # a reaction may be used multiple times in an objective function
                if reactions_dict[id] not in reactions:
                    reactions.append(reactions_dict[id])

            if is_biomass_reaction:
                if biomass_reactions_dict[id] not in biomass_reactions:
                    biomass_reactions.append(biomass_reactions_dict[id])

        if errors:
            return (None, InvalidAttribute(attribute, errors, value=value))

        # create new ObjectiveFunction
        if cls not in objects:
            objects[cls] = {}
        serialized_val = value
        if serialized_val in objects[cls]:
            obj = objects[cls][serialized_val]
        else:
            obj = cls(expression=value, reactions=reactions, biomass_reactions=biomass_reactions)
            objects[cls][serialized_val] = obj
        return (obj, None)

    def validate(self):
        """ Determine whether an `ObjectiveFunction` is valid

        Ensure that self.expression evaluates as valid Python.

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors in an `InvalidObject` instance
        """

        # to evaluate the expression, set variables for the reaction identifiers to their fluxes
        # test validation with fluxes of 1.0
        local_ns = {func.__name__: func for func in self.Meta.valid_functions}
        local_ns.update({rxn.id: 1.0 for rxn in self.reactions})
        local_ns.update({biomass_rxn.id: 1.0 for biomass_rxn in self.biomass_reactions})
        errors = []

        try:
            eval(self.expression, {}, local_ns)
        except SyntaxError as error:
            errors.append("syntax error in expression '{}'".format(self.expression))
        except NameError as error:
            errors.append("NameError in expression '{}'".format(self.expression))
        except Exception as error:
            errors.append("cannot eval expression '{}'".format(self.expression))

        if errors:
            attr = self.__class__.Meta.attributes['expression']
            attr_err = InvalidAttribute(attr, errors)
            return InvalidObject(self, [attr_err])

        """ return `None` to indicate valid object """
        return None

    ACTIVE_OBJECTIVE = 'active_objective'

    def add_to_sbml_doc(self, sbml_document):
        """ Add this ObjectiveFunction to a libsbml SBML document in a `libsbml.model.ListOfObjectives`.

        This uses version 2 of the 'Flux Balance Constraints' extension. SBML assumes that an
        ObjectiveFunction is a linear combination of reaction fluxes.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.Objective`: the libsbml Objective that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        # issue warning if objective function not linear
        if not self.linear:
            warnings.warn("submodels '{}' can't add non-linear objective function to SBML FBC model".format(
                ', '.join(s.id for s in self.submodels)), UserWarning)
            return
        sbml_model = wrap_libsbml(sbml_document.getModel)
        fbc_model_plugin = wrap_libsbml(sbml_model.getPlugin, 'fbc')
        sbml_objective = wrap_libsbml(fbc_model_plugin.createObjective)
        wrap_libsbml(sbml_objective.setType, 'maximize')
        # In SBML 3 FBC 2, the 'activeObjective' attribute must be set on ListOfObjectives.
        # Since a submodel has only one Objective, it must be the active one.
        wrap_libsbml(sbml_objective.setIdAttribute, ObjectiveFunction.ACTIVE_OBJECTIVE)
        list_of_objectives = wrap_libsbml(fbc_model_plugin.getListOfObjectives)
        wrap_libsbml(list_of_objectives.setActiveObjective, ObjectiveFunction.ACTIVE_OBJECTIVE)
        for idx, reaction in enumerate(self.reactions):
            sbml_flux_objective = wrap_libsbml(sbml_objective.createFluxObjective)
            wrap_libsbml(sbml_flux_objective.setReaction, reaction.id)
            wrap_libsbml(sbml_flux_objective.setCoefficient, self.reaction_coefficients[idx])
        for idx, biomass_reaction in enumerate(self.biomass_reactions):
            sbml_flux_objective = wrap_libsbml(sbml_objective.createFluxObjective)
            wrap_libsbml(sbml_flux_objective.setReaction, biomass_reaction.id)
            wrap_libsbml(sbml_flux_objective.setCoefficient, self.biomass_reaction_coefficients[idx])

        return sbml_objective

    def get_products(self, __type=None, **kwargs):
        """ Get the species produced by this objective function

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of :obj:`Species`: species produced by this objective function
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        products = []
        for reaction in self.reactions:
            if reaction.reversible:
                for part in reaction.participants:
                    if part.species.has_attr_vals(__type=__type, **kwargs):
                        products.append(part.species)
            else:
                for part in reaction.participants:
                    if 0 < part.coefficient:
                        if part.species.has_attr_vals(__type=__type, **kwargs):
                            products.append(part.species)

        tmp_species_ids = []
        for biomass_reaction in self.biomass_reactions:
            for biomass_component in biomass_reaction.biomass_components:
                if 0 < biomass_component.coefficient:
                    tmp_species_ids.append(biomass_component.species.id)
        for submodel in self.submodels:
            tmp_species = Species.get(tmp_species_ids, submodel.get_species())
            for tmp_specie_id, tmp_specie in zip(tmp_species_ids, tmp_species):
                if not tmp_specie:
                    raise ValueError('Species {} does not belong to submodel {}'.format(tmp_specie_id, submodel.id))
                if tmp_specie.has_attr_vals(__type=__type, **kwargs):
                    products.append(tmp_specie)
        return det_dedupe(products)


class Compartment(obj_model.Model):
    """ Compartment

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        initial_volume (:obj:`float`): initial volume (L)
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references

    Related attributes:
        species (:obj:`list` of :obj:`Species`): species in this compartment
        database_references (:obj:`list` of :obj:`DatabaseReference`): database references
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='compartments')
    initial_volume = FloatAttribute(min=0)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='compartments')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name',
                           'initial_volume',
                           'comments', 'references')

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Compartment to a libsbml SBML document.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.compartment`: the libsbml compartment that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml(sbml_document.getModel)
        sbml_compartment = wrap_libsbml(sbml_model.createCompartment)
        wrap_libsbml(sbml_compartment.setIdAttribute, self.id)
        wrap_libsbml(sbml_compartment.setName, self.name)
        wrap_libsbml(sbml_compartment.setSpatialDimensions, 3)
        wrap_libsbml(sbml_compartment.setSize, self.initial_volume)
        wrap_libsbml(sbml_compartment.setConstant, False)
        if self.comments:
            wrap_libsbml(sbml_compartment.setNotes, self.comments, True)
        return sbml_compartment


class SpeciesType(obj_model.Model):
    """ Species type

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        structure (:obj:`str`): structure (InChI for metabolites; sequence for DNA, RNA, proteins)
        empirical_formula (:obj:`str`): empirical formula
        molecular_weight (:obj:`float`): molecular weight
        charge (:obj:`int`): charge
        type (:obj:`SpeciesTypeType`): type
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references

    Related attributes:
        species (:obj:`list` of :obj:`Species`): species
        database_references (:obj:`list` of :obj:`DatabaseReference`): database references
        concentrations (:obj:`list` of :obj:`Concentration`): concentrations
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='species_types')
    structure = LongStringAttribute()
    empirical_formula = RegexAttribute(pattern=r'^([A-Z][a-z]?\d*)*$')
    molecular_weight = FloatAttribute(min=0)
    charge = IntegerAttribute()
    type = EnumAttribute(SpeciesTypeType, default=SpeciesTypeType.metabolite)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='species_types')

    class Meta(obj_model.Model.Meta):
        verbose_name = 'Species type'
        attribute_order = ('id', 'name', 'structure', 'empirical_formula',
                           'molecular_weight', 'charge', 'type', 'comments', 'references')

        indexed_attrs_tuples = (('id',), )

    # todo: move to compiled model
    def is_carbon_containing(self):
        """ Returns `True` is species contains at least one carbon atom.

        Returns:
            :obj:`bool`: `True` is species contains at least one carbon atom.
        """
        return re.match('C[1-9]', self.empirical_formula) is not None


class Species(obj_model.Model):
    """ Species (tuple of species type, compartment)

    Attributes:
        id (:obj:`str`): identifier equal to `{species_type.id}[{compartment.id}]`
        name (:obj:`str`): name
        species_type (:obj:`SpeciesType`): species type
        compartment (:obj:`Compartment`): compartment
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references

    Related attributes:
        concentration (:obj:`Concentration`): concentration
        species_coefficients (:obj:`list` of :obj:`SpeciesCoefficient`): participations in reactions and observables
        rate_law_equations (:obj:`list` of :obj:`RateLawEquation`): rate law equations
        observable_expressions (:obj:`list` of :obj:`ObservableExpression`): observable expressions
        biomass_components (:obj:`list` of :obj:`BiomassComponent`): biomass components
    """
    id = StringAttribute(primary=True, unique=True)
    name = StringAttribute()
    species_type = ManyToOneAttribute(SpeciesType, related_name='species', min_related=1)
    compartment = ManyToOneAttribute(Compartment, related_name='species', min_related=1)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='species')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name', 'species_type', 'compartment', 'comments', 'references')
        frozen_columns = 1
        # unique_together = (('species_type', 'compartment', ), )
        ordering = ('id',)
        indexed_attrs_tuples = (('species_type', 'compartment'), )
        token_pattern = (token.NAME, token.LSQB, token.NAME, token.RSQB)

    @staticmethod
    def gen_id(species_type_id, compartment_id):
        """ Generate identifier

        Args:
            species_type_id (:obj:`str`): species type id
            compartment_id (:obj:`str`): species type id

        Returns:
            :obj:`str`: identifier
        """
        return '{}[{}]'.format(species_type_id, compartment_id)

    def validate(self):
        """ Validate that identifier is equal to `{species_type.id}[{compartment.id}]`

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors as an instance of `InvalidObject`
        """
        invalid_obj = super(Species, self).validate()
        if invalid_obj:
            errors = invalid_obj.attributes
        else:
            errors = []

        if self.id != self.gen_id(self.species_type.id, self.compartment.id):
            errors.append(InvalidAttribute(self.Meta.attributes['id'],
                                           ['Id must be {}'.format(self.gen_id(self.species_type.id, self.compartment.id))]))

        if errors:
            return InvalidObject(self, errors)
        return None

    @staticmethod
    def get(ids, species_iterator):
        """ Find some Species instances

        Args:
            ids (:obj:`Iterator` of `str`): an iterator over some species identifiers
            species_iterator (:obj:`Iterator`): an iterator over some species

        Returns:
            :obj:`list` of :obj:`Species` or `None`: each element of the `list` corresponds to an element
                of `ids` and contains either a `Species` with `id()` equal to the element in `ids`,
                or `None` indicating that `species_iterator` does not contain a matching `Species`
        """
        # TODO: this costs O(|ids||species_iterator|); replace with O(|ids|) operation using obj_model.Manager.get()
        rv = []
        for id in ids:
            s = None
            for specie in species_iterator:
                if specie.id == id:
                    s = specie
                    break
            rv.append(s)
        return rv

    def gen_sbml_id(self):
        """ Make a Species id that satisfies the SBML string id syntax.

        Replaces the '[' and ']' in Species.id with double-underscores '__'.
        See Finney and Hucka, "Systems Biology Markup Language (SBML) Level 2: Structures and
        Facilities for Model Definitions", 2003, section 3.4.

        Returns:
            :obj:`str`: SBML id
        """
        return '{}__{}__'.format(self.species_type.id, self.compartment.id)

    @staticmethod
    def sbml_id_to_id(sbml_id):
        """ Convert an `sbml_id` to its species id.

        Returns:
            :obj:`str`: species id
        """
        return sbml_id.replace('__', '[', 1).replace('__', ']', 1)

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Species to a libsbml SBML document.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.species`: the libsbml species that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml(sbml_document.getModel)
        sbml_species = wrap_libsbml(sbml_model.createSpecies)
        # initDefaults() isn't wrapped in wrap_libsbml because it returns None
        sbml_species.initDefaults()
        wrap_libsbml(sbml_species.setIdAttribute, self.gen_sbml_id())

        # add some SpeciesType data
        wrap_libsbml(sbml_species.setName, self.species_type.name)
        if self.species_type.comments:
            wrap_libsbml(sbml_species.setNotes, self.species_type.comments, True)

        # set Compartment, which must already be in the SBML document
        wrap_libsbml(sbml_species.setCompartment, self.compartment.id)

        # set the Initial Concentration
        wrap_libsbml(sbml_species.setInitialConcentration, self.concentration.value)

        # set units
        unit_xml_id = ConcentrationUnit.Meta[self.concentration.units]['xml_id']
        wrap_libsbml(sbml_species.setSubstanceUnits, unit_xml_id)

        return sbml_species


class Concentration(obj_model.Model):
    """ Species concentration

    Attributes:
        species (:obj:`Species`): species
        value (:obj:`float`): value
        units (:obj:`ConcentrationUnit`): units; default units is `M`
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references
    """
    species = OneToOneAttribute(Species, related_name='concentration')
    value = FloatAttribute(min=0)
    units = EnumAttribute(ConcentrationUnit, default=ConcentrationUnit.M)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='concentrations')

    class Meta(obj_model.Model.Meta):
        unique_together = (('species', ), )
        attribute_order = ('species', 'value', 'units', 'comments', 'references')

        frozen_columns = 1
        ordering = ('species',)

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: string representation
        """
        return 'conc-{}'.format(self.species.id)


class ExpressionMethods(object):
    """ Generic methods for mathematical expressions
    """

    @staticmethod
    def serialize(model_obj):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return model_obj.expression

    @staticmethod
    def deserialize(model_class, attribute, value, objects, decoded=None):
        """ Deserialize expression

        Args:
            attribute (:obj:`Attribute`): expression attribute
            value (:obj:`str`): string representation of the mathematical expression, in a
                Python expression
            objects (:obj:`dict`): dictionary of objects which can be used in `expression`, grouped by model

        Returns:
            :obj:`tuple`: on error return (`None`, `InvalidAttribute`),
                otherwise return (object in this class with instantiated `analyzed_expr`, `None`)
        """
        # objects must contain all objects types in valid_used_models
        used_model_types = []
        for used_model in model_class.Meta.valid_used_models:
            used_model_type = globals()[used_model]
            used_model_types.append(used_model_type)
        expr_field = 'expression'
        try:
            given_model_types = [BiomassReaction, Function, Observable, Parameter, Reaction, Species]
            analyzed_expr = WcLangExpression(model_class, expr_field, value, objects,
                given_model_types=given_model_types)
        except WcLangExpressionError as e:
            return (None, InvalidAttribute(attribute, [str(e)]))
        rv = analyzed_expr.tokenize()
        if rv[0] is None:
            errors = rv[1]
            return (None, InvalidAttribute(attribute, errors))
        _, used_objects = rv
        if model_class not in objects:
            objects[model_class] = {}
        if value in objects[model_class]:
            obj = objects[model_class][value]
        else:
            obj = model_class(expression=value)
            objects[model_class][value] = obj
            for used_model_type in used_model_types:
                used_model_type_attr = used_model_type.__name__.lower()
                if not used_model_type_attr.endswith('s'):
                    used_model_type_attr = used_model_type_attr+'s'
                attr_value = []
                if used_model_type in used_objects:
                    attr_value = list(used_objects[used_model_type].values())
                setattr(obj, used_model_type_attr, attr_value)
        obj.analyzed_expr = analyzed_expr
        return (obj, None)

    @staticmethod
    def validate(model_obj, return_type=None):
        """ Determine whether an expression model is valid by eval'ing its deserialized expression

        Args:
            return_type (:obj:`type`, optional): if provided, an expression's required return type

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors in an `InvalidObject` instance
        """
        attr = model_obj.__class__.Meta.attributes['expression']
        try:
            rv = model_obj.analyzed_expr.test_eval_expr()
            if return_type is not None:
                if not isinstance(rv, return_type):
                    attr_err = InvalidAttribute(attr,
                                                ["Evaluating '{}', a {} expression, should return a {} but it returns a {}".format(
                                                    model_obj.expression, model_obj.__class__.__name__,
                                                    return_type.__name__, type(rv).__name__)])
                    return InvalidObject(model_obj, [attr_err])

            # return `None` to indicate valid object
            return None
        except WcLangExpressionError as e:
            attr_err = InvalidAttribute(attr, [str(e)])
            return InvalidObject(model_obj, [attr_err])

    @staticmethod
    def make_expression_obj(model_type, expression, objects):
        """ Make an expression object

        Args:
            model_type (:obj:`type`): an `obj_model.Model` that uses a mathemetical expression, like
                `Function` and `Observable`
            expression (:obj:`str`): the expression used by the `model_type` being created
            objects (:obj:`dict` of `dict`): all objects that are referenced in `expression`

        Returns:
            :obj:`tuple`: if successful, (`obj_model.Model`, `None`) containing a new instance of
                `model_type`'s expression helper class; otherwise, (`None`, `InvalidAttribute`)
                reporting the error
        """
        attr = model_type.Meta.attributes['expression']
        expr_model_type = model_type.Meta.expression_model
        return expr_model_type.deserialize(attr, expression, objects)

    @staticmethod
    def make_obj(model, model_type, id, expression, objects, allow_invalid_objects=False):
        """ Make a model that contains an expression by using its expression helper class

        For example, this uses `FunctionExpression` to make a `Function`.

        Args:
            model (:obj:`obj_model.Model`): a `wc_lang.core.Model` which is the root model
            model_type (:obj:`type`): an `obj_model.Model` that uses a mathemetical expression, like
                `Function` and `Observable`
            id (:obj:`str`): the id of the `model_type` being created
            expression (:obj:`str`): the expression used by the `model_type` being created
            objects (:obj:`dict` of `dict`): all objects that are referenced in `expression`
            allow_invalid_objects (:obj:`bool`, optional): if set, return object - not error - if
                the expression object does not validate

        Returns:
            :obj:`obj_model.Model` or `InvalidAttribute`: a new instance of `model_type`, or,
                if an error occurs, an `InvalidAttribute` reporting the error
        """
        expr_model_obj, error = ExpressionMethods.make_expression_obj(model_type, expression, objects)
        if error:
            return error
        error_or_none = expr_model_obj.validate()
        if error_or_none is not None and not allow_invalid_objects:
            return error_or_none
        related_name = model_type.Meta.attributes['model'].related_name
        related_in_model = getattr(model, related_name)
        new_obj = related_in_model.create(id=id, expression=expr_model_obj)
        return new_obj


class ObservableExpression(obj_model.Model):
    """ A mathematical expression of Observables and Species

    The expression used by a `Observable`.

    Attributes:
        expression (:obj:`str`): mathematical expression for an Observable
        analyzed_expr (:obj:`WcLangExpression`): an analyzed `expression`; not an `obj_model.Model`
        observables (:obj:`list` of :obj:`Observable`): other Observables used by this Observable expression
        species (:obj:`list` of :obj:`Species`): Species used by this Observable expression

    Related attributes:
        observable_expressions (:obj:`ObservableExpression`): observable expressions
    """

    expression = LongStringAttribute(primary=True, unique=True)
    observables = ManyToManyAttribute('Observable', related_name='observable_expressions')
    species = ManyToManyAttribute(Species, related_name='observable_expressions')

    class Meta(obj_model.Model.Meta):
        """
        Attributes:
            valid_Observables (:obj:`tuple` of `builtin_Observable_or_method`): tuple of Observables that
                can be used in this `Observable`s `expression`
            valid_used_models (:obj:`tuple` of `str`): names of `obj_model.Model`s in this module that a
                `Observable` is allowed to reference in its `expression`
        """
        tabular_orientation = TabularOrientation.inline
        valid_used_models = ('Species', 'Observable')

    def serialize(self):
        return ExpressionMethods.serialize(self)

    @classmethod
    def deserialize(cls, attribute, value, objects, decoded=None):
        return ExpressionMethods.deserialize(cls, attribute, value, objects)

    def validate(self):
        # ensure that the observable is a linear function
        valid, error = LinearExpressionVerifier().validate(self.analyzed_expr.wc_tokens)
        if not valid:
            attr = self.__class__.Meta.attributes['expression']
            attr_err = InvalidAttribute(attr, [error])
            return InvalidObject(self, [attr_err])
        return ExpressionMethods.validate(self)


class Observable(obj_model.Model):
    """ Observable: a linear function of other Observbles and Species

    Attributes:
        id (:obj:`str`): unique id
        name (:obj:`str`): name
        model (:obj:`Model`): model
        expression (:obj:`ObservableExpression`): mathematical expression for an Observable
        comments (:obj:`str`): comments

    Related attributes:
        expressions (:obj:`Expressions`): expressions
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='observables')
    expression = ObservableExpressionAttribute(related_name='observable')
    comments = LongStringAttribute()

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name', 'expression', 'comments')
        expression_model = ObservableExpression

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of related `ObservableExpression`
        """
        return self.expression.serialize()


class FunctionExpression(obj_model.Model):
    """ A mathematical expression of Functions, Observbles, Parameters and Python functions

    The expression used by a `Function`.

    Attributes:
        expression (:obj:`str`): mathematical expression for a Function
        analyzed_expr (:obj:`WcLangExpression`): an analyzed `expression`; not an `obj_model.Model`
        observables (:obj:`list` of :obj:`Observable`): Observables used by this function expression
        parameters (:obj:`list` of :obj:`Parameter`): Parameters used by this function expression
        functions (:obj:`list` of :obj:`Function`): other Functions used by this function expression

    Related attributes:
        function (:obj:`Function`): function
    """

    expression = LongStringAttribute(primary=True, unique=True)
    observables = ManyToManyAttribute(Observable, related_name='functions')
    parameters = ManyToManyAttribute('Parameter', related_name='functions')
    functions = ManyToManyAttribute('Function', related_name='functions')

    class Meta(obj_model.Model.Meta):
        """
        Attributes:
            valid_functions (:obj:`tuple` of `builtin_function_or_method`): tuple of functions that
                can be used in this `Function`s `expression`
            valid_used_models (:obj:`tuple` of `str`): names of `obj_model.Model`s in this module that a
                `Function` is allowed to reference in its `expression`
        """
        tabular_orientation = TabularOrientation.inline
        valid_functions = (ceil, floor, exp, pow, log, log10, min, max)
        valid_used_models = ('Parameter', 'Observable', 'Function')

    def serialize(self):
        return ExpressionMethods.serialize(self)

    @classmethod
    def deserialize(cls, attribute, value, objects, decoded=None):
        return ExpressionMethods.deserialize(cls, attribute, value, objects)

    def validate(self):
        return ExpressionMethods.validate(self)


class Function(obj_model.Model):
    """ Function: a mathematical expression of Functions, Observbles, Parameters and Python functions

    Attributes:
        id (:obj:`str`): unique id
        name (:obj:`str`): name
        model (:obj:`Model`): model
        expression (:obj:`FunctionExpression`): mathematical expression for a Function
        comments (:obj:`str`): comments

    Related attributes:
        expressions (:obj:`Expressions`): expressions
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='functions')
    expression = FunctionExpressionAttribute(related_name='function')
    comments = LongStringAttribute()

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name', 'expression', 'comments')
        expression_model = FunctionExpression

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of related `FunctionExpression`
        """
        return self.expression.serialize()


class StopConditionExpression(obj_model.Model):
    """ A mathematical expression of Functions, Observbles, Parameters and Python functions

    The expression used by a `StopCondition`.

    Attributes:
        expression (:obj:`str`): mathematical expression for a StopCondition
        analyzed_expr (:obj:`WcLangExpression`): an analyzed `expression`; not an `obj_model.Model`
        observables (:obj:`list` of :obj:`Observable`): Observables used by this stop condition expression
        parameters (:obj:`list` of :obj:`Parameter`): Parameters used by this stop condition expression
        functions (:obj:`list` of :obj:`Function`): Functions used by this stop condition expression

    Related attributes:
        stop_condition (:obj:`StopCondition`): stop condition
    """

    expression = LongStringAttribute(primary=True, unique=True)
    observables = OneToManyAttribute(Observable, related_name='stop_conditions')
    parameters = OneToManyAttribute('Parameter', related_name='stop_conditions')
    functions = OneToManyAttribute('Function', related_name='stop_conditions')

    class Meta(obj_model.Model.Meta):
        """
        Attributes:
            valid_functions (:obj:`tuple` of `builtin_function_or_method`): tuple of functions that
                can be used in this `StopCondition`s `expression`
            valid_used_models (:obj:`tuple` of `str`): names of `obj_model.Model`s in this module that a
                `StopCondition` is allowed to reference in its `expression`
        """
        tabular_orientation = TabularOrientation.inline
        valid_functions = (ceil, floor, exp, pow, log, log10, min, max)
        valid_used_models = ('Parameter', 'Observable', 'Function')

    def serialize(self):
        return ExpressionMethods.serialize(self)

    @classmethod
    def deserialize(cls, attribute, value, objects, decoded=None):
        return ExpressionMethods.deserialize(cls, attribute, value, objects)

    def validate(self):
        """ A StopConditionExpression must return a Boolean """
        return ExpressionMethods.validate(self, return_type=bool)


class StopCondition(obj_model.Model):
    """ StopCondition: Simulation of a model terminates when its StopCondition is true.

    A mathematical expression of Functions, Observbles, Parameters and Python functions `StopCondition`s
    are optional. It must return a Boolean.

    Attributes:
        id (:obj:`str`): unique id
        name (:obj:`str`): name
        model (:obj:`Model`): model
        expression (:obj:`StopConditionExpression`): mathematical expression for a StopCondition
        comments (:obj:`str`): comments

    Related attributes:
        expressions (:obj:`Expressions`): expressions
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='stop_conditions')
    expression = StopConditionExpressionAttribute(related_name='stop_condition')
    comments = LongStringAttribute()

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name', 'expression', 'comments')
        expression_model = StopConditionExpression

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of related `StopConditionExpression`
        """
        return self.expression.serialize()


class Reaction(obj_model.Model):
    """ Reaction

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        submodel (:obj:`Submodel`): submodel that reaction belongs to
        participants (:obj:`list` of :obj:`SpeciesCoefficient`): participants
        reversible (:obj:`bool`): indicates if reaction is thermodynamically reversible
        min_flux (:obj:`float`): minimum flux bound for solving an FBA model; negative for reversible reactions
        max_flux (:obj:`float`): maximum flux bound for solving an FBA model
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references

    Related attributes:
        database_references (:obj:`list` of :obj:`DatabaseReference`): database references
        rate_laws (:obj:`list` of :obj:`RateLaw`): rate laws; if present, rate_laws[0] is the forward
            rate law, and rate_laws[0] is the backward rate law
    """
    id = SlugAttribute()
    name = StringAttribute()
    submodel = ManyToOneAttribute(Submodel, related_name='reactions')
    participants = ReactionParticipantAttribute(related_name='reactions')
    reversible = BooleanAttribute()
    min_flux = FloatAttribute(nan=True)
    max_flux = FloatAttribute(min=0, nan=True)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='reactions')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name', 'submodel', 'participants', 'reversible', 'min_flux', 'max_flux', 'comments', 'references')
        indexed_attrs_tuples = (('id',), )

    def get_species(self, __type=None, **kwargs):
        """ Get species

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list`: list of `Species`
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        species = []

        for part in self.participants:
            if part.species.has_attr_vals(__type=__type, **kwargs):
                species.append(part.species)

        for rate_law in self.rate_laws:
            if rate_law.equation:
                species.extend(rate_law.equation.modifiers.get(__type=__type, **kwargs))

        return det_dedupe(species)

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Reaction to a libsbml SBML document.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.reaction`: the libsbml reaction that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml(sbml_document.getModel)

        # create SBML reaction in SBML document
        sbml_reaction = wrap_libsbml(sbml_model.createReaction)
        wrap_libsbml(sbml_reaction.setIdAttribute, self.id)
        wrap_libsbml(sbml_reaction.setName, self.name)
        wrap_libsbml(sbml_reaction.setReversible, self.reversible)
        wrap_libsbml(sbml_reaction.setFast, False)
        if self.comments:
            wrap_libsbml(sbml_reaction.setNotes, self.comments, True)

        # write reaction participants to SBML document
        for participant in self.participants:
            if participant.coefficient < 0:
                species_reference = wrap_libsbml(sbml_reaction.createReactant)
                wrap_libsbml(species_reference.setStoichiometry, -participant.coefficient)
            elif 0 < participant.coefficient:
                species_reference = wrap_libsbml(sbml_reaction.createProduct)
                wrap_libsbml(species_reference.setStoichiometry, participant.coefficient)
            wrap_libsbml(species_reference.setSpecies, participant.species.gen_sbml_id())
            wrap_libsbml(species_reference.setConstant, True)

        # for dFBA submodels, write flux bounds to SBML document
        # uses version 2 of the 'Flux Balance Constraints' extension
        if self.submodel.algorithm == SubmodelAlgorithm.dfba:
            fbc_reaction_plugin = wrap_libsbml(sbml_reaction.getPlugin, 'fbc')
            for bound in ['lower', 'upper']:
                # make a unique ID for each flux bound parameter
                # ids for wc_lang Parameters all start with 'parameter'
                param_id = "_reaction_{}_{}_bound".format(self.id, bound)
                param = create_sbml_parameter(sbml_model, id=param_id, value=self.min_flux,
                                              units='mmol_per_gDW_per_hr')
                if bound == 'lower':
                    wrap_libsbml(param.setValue, self.min_flux)
                    wrap_libsbml(fbc_reaction_plugin.setLowerFluxBound, param_id)
                if bound == 'upper':
                    wrap_libsbml(param.setValue, self.max_flux)
                    wrap_libsbml(fbc_reaction_plugin.setUpperFluxBound, param_id)
        return sbml_reaction


class SpeciesCoefficient(obj_model.Model):
    """ A tuple of a species and a coefficient

    Attributes:
        species (:obj:`Species`): species
        coefficient (:obj:`float`): coefficient

    Related attributes:
        reaction (:obj:`Reaction`): reaction
        observables (:obj:`Observable`): observables
    """
    species = ManyToOneAttribute(Species, related_name='species_coefficients')
    coefficient = FloatAttribute(nan=False)

    class Meta(obj_model.Model.Meta):
        unique_together = (('species', 'coefficient'),)
        attribute_order = ('species', 'coefficient')
        frozen_columns = 1
        tabular_orientation = TabularOrientation.inline
        ordering = ('species',)

    def serialize(self, show_compartment=True, show_coefficient_sign=True):
        """ Serialize related object

        Args:
            show_compartment (:obj:`bool`, optional): if true, show compartment
            show_coefficient_sign (:obj:`bool`, optional): if true, show coefficient sign

        Returns:
            :obj:`str`: simple Python representation
        """
        return self._serialize(self.species, self.coefficient,
                               show_compartment=show_compartment, show_coefficient_sign=show_coefficient_sign)

    @staticmethod
    def _serialize(species, coefficient, show_compartment=True, show_coefficient_sign=True):
        """ Serialize values

        Args:
            species (:obj:`Species`): species
            coefficient (:obj:`float`): coefficient
            show_compartment (:obj:`bool`, optional): if true, show compartment
            show_coefficient_sign (:obj:`bool`, optional): if true, show coefficient sign

        Returns:
            :obj:`str`: simple Python representation
        """
        coefficient = float(coefficient)

        if not show_coefficient_sign:
            coefficient = abs(coefficient)

        if coefficient == 1:
            coefficient_str = ''
        elif coefficient % 1 == 0 and abs(coefficient) < 1000:
            coefficient_str = '({:.0f}) '.format(coefficient)
        else:
            coefficient_str = '({:e}) '.format(coefficient)

        if show_compartment:
            return '{}{}'.format(coefficient_str, species.serialize())
        else:
            return '{}{}'.format(coefficient_str, species.species_type.get_primary_attribute())

    @classmethod
    def deserialize(cls, attribute, value, objects, compartment=None):
        """ Deserialize value

        Args:
            attribute (:obj:`Attribute`): attribute
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            compartment (:obj:`Compartment`, optional): compartment

        Returns:
            :obj:`tuple` of `list` of `SpeciesCoefficient`, `InvalidAttribute` or `None`: tuple of cleaned value
                and cleaning error
        """
        errors = []

        if compartment:
            pattern = r'^(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*)$'
        else:
            pattern = r'^(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*\[[a-z][a-z0-9_]*\])$'

        match = re.match(pattern, value, flags=re.I)
        if match:
            errors = []

            coefficient = float(match.group(2) or 1.)

            if compartment:
                species_id = Species.gen_id(match.group(5), compartment.get_primary_attribute())
            else:
                species_id = match.group(5)

            species, error = Species.deserialize(species_id, objects)
            if error:
                return (None, error)

            serialized_val = cls._serialize(species, coefficient)
            if cls not in objects:
                objects[cls] = {}
            if serialized_val in objects[cls]:
                obj = objects[cls][serialized_val]
            else:
                obj = cls(species=species, coefficient=coefficient)
                objects[cls][serialized_val] = obj
            return (obj, None)

        else:
            attr = cls.Meta.attributes['species']
            return (None, InvalidAttribute(attr, ['Invalid species coefficient']))


class RateLaw(obj_model.Model):
    """ Rate law

    Attributes:
        reaction (:obj:`Reaction`): reaction
        direction (:obj:`RateLawDirection`): direction
        equation (:obj:`RateLawEquation`): equation
        k_cat (:obj:`float`): v_max (reactions enz^-1 s^-1)
        k_m (:obj:`float`): k_m (M)
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references
    """

    reaction = ManyToOneAttribute(Reaction, related_name='rate_laws')
    direction = EnumAttribute(RateLawDirection, default=RateLawDirection.forward)
    equation = RateLawEquationAttribute(related_name='rate_laws')
    k_cat = FloatAttribute(min=0, nan=True)
    k_m = FloatAttribute(min=0, nan=True)
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='rate_laws')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('reaction', 'direction',
                           'equation', 'k_cat', 'k_m',
                           'comments', 'references')
        unique_together = (('reaction', 'direction'), )
        ordering = ('reaction', 'direction',)

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return '{}.{}'.format(self.reaction.serialize(), self.direction.name)

    def validate(self):
        """ Determine whether this `RateLaw` is valid

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors in an `InvalidObject` instance
        """

        """ Check that rate law evaluates """
        if self.equation:
            try:
                species_ids = set([s.id for s in self.equation.modifiers])
                parameter_ids = set([p.id for p in self.equation.parameters])
                transcoded = RateLawUtils.transcode(self.equation, species_ids, parameter_ids)
                concentrations = {}
                parameters = {}
                for s in self.equation.modifiers:
                    concentrations[s.id] = 1.0
                for p in self.equation.parameters:
                    parameters[p.id] = 1.0
                RateLawUtils.eval_rate_law(self, concentrations, parameters, transcoded_equation=transcoded)
            except Exception as error:
                msg = str(error)
                attr = self.__class__.Meta.attributes['equation']
                attr_err = InvalidAttribute(attr, [msg])
                return InvalidObject(self, [attr_err])

        """ return `None` to indicate valid object """
        return None


class RateLawEquation(obj_model.Model):
    """ Rate law equation

    Attributes:
        expression (:obj:`str`): mathematical expression of the rate law
        transcoded (:obj:`str`): transcoded expression, suitable for evaluating as a Python expression
        modifiers (:obj:`list` of :obj:`Species`): species whose concentrations are used in the rate law
        parameters (:obj:`list` of :obj:`Parameter`): parameters whose values are used in the rate law

    Related attributes:
        rate_law (:obj:`RateLaw`): the `RateLaw` which uses this `RateLawEquation`
    """
    expression = LongStringAttribute(primary=True, unique=True)
    transcoded = LongStringAttribute()
    modifiers = ManyToManyAttribute(Species, related_name='rate_law_equations')
    parameters = ManyToManyAttribute('Parameter', related_name='rate_law_equations')

    class Meta(obj_model.Model.Meta):
        """
        Attributes:
            valid_functions (:obj:`tuple` of `builtin_function_or_method`): tuple of functions that
                can be used in a `RateLawEquation`s `expression`
            valid_used_models (:obj:`tuple` of `str`): names of `obj_model.Model`s in this module that a
                `RateLawEquation` is allowed to reference in its `expression`
        """
        attribute_order = ('expression', 'modifiers', 'parameters')
        tabular_orientation = TabularOrientation.inline
        ordering = ('rate_law',)
        valid_functions = (ceil, floor, exp, pow, log, log10, min, max)
        valid_used_models = ('Species', 'Parameter', 'Observable', 'Function')

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return self.expression

    @classmethod
    def deserialize(cls, attribute, value, objects):
        """ Deserialize value

        Args:
            attribute (:obj:`Attribute`): attribute
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model

        Returns:
            :obj:`tuple` of `object`, `InvalidAttribute` or `None`: tuple of cleaned value and cleaning error
        """
        modifiers = []
        parameters = []
        errors = []
        modifier_pattern = r'(^|[^a-z0-9_])({}\[{}\])([^a-z0-9_]|$)'.format(SpeciesType.id.pattern[1:-1],
                                                                            Compartment.id.pattern[1:-1])
        parameter_pattern = r'(^|[^a-z0-9_\[\]])({})([^a-z0-9_\[\]]|$)'.format(Parameter.id.pattern[1:-1])

        reserved_names = set([func.__name__ for func in RateLawEquation.Meta.valid_functions] + ['k_cat', 'k_m'])

        try:
            for match in re.findall(modifier_pattern, value, flags=re.I):
                species, error = Species.deserialize(match[1], objects)
                if error:
                    errors.append(['Invalid species'])
                else:
                    modifiers.append(species)
            for match in re.findall(parameter_pattern, value, flags=re.I):
                if match[1] not in reserved_names:
                    parameter, error = Parameter.deserialize(match[1], objects)
                    if error:
                        errors += error.messages
                    else:
                        parameters.append(parameter)
        except Exception as e:
            errors += ["deserialize fails on '{}': {}".format(value, str(e))]

        if errors:
            attr = cls.Meta.attributes['expression']
            return (None, InvalidAttribute(attribute, errors))

        # return value
        if cls not in objects:
            objects[cls] = {}
        serialized_val = value
        if serialized_val in objects[cls]:
            obj = objects[cls][serialized_val]
        else:
            obj = cls(expression=value, modifiers=det_dedupe(modifiers), parameters=det_dedupe(parameters))
            objects[cls][serialized_val] = obj
        return (obj, None)

    def validate(self):
        """ Determine whether a `RateLawEquation` is valid

        * Check that all of the modifiers and parameters contribute to the expression
        * Check that the modifiers and parameters encompass of the named entities in the expression

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors in an `InvalidObject` instance
        """
        errors = []

        # check modifiers
        modifier_ids = set((x.serialize() for x in self.modifiers))
        modifier_pattern = r'(^|[^a-z0-9_])({}\[{}\])([^a-z0-9_]|$)'.format(SpeciesType.id.pattern[1:-1],
                                                                            Compartment.id.pattern[1:-1])
        entity_ids = set([x[1] for x in re.findall(modifier_pattern, self.expression, flags=re.I)])
        if modifier_ids != entity_ids:
            for id in modifier_ids.difference(entity_ids):
                errors.append('Extraneous modifier "{}"'.format(id))

            for id in entity_ids.difference(modifier_ids):
                errors.append('Undefined modifier "{}"'.format(id))

        # check parameters
        parameter_ids = set((x.serialize() for x in self.parameters))
        parameter_pattern = r'(^|[^a-z0-9_\[\]])({})([^a-z0-9_\[\]]|$)'.format(Parameter.id.pattern[1:-1])
        entity_ids = set([x[1] for x in re.findall(parameter_pattern, self.expression, flags=re.I)])
        reserved_names = set([func.__name__ for func in RateLawEquation.Meta.valid_functions] + ['k_cat', 'k_m'])
        entity_ids -= reserved_names
        if parameter_ids != entity_ids:
            for id in parameter_ids.difference(entity_ids):
                errors.append('Extraneous parameter "{}"'.format(id))

            for id in entity_ids.difference(parameter_ids):
                errors.append('Undefined parameter "{}"'.format(id))

            for id in reserved_names:
                errors.append('Invalid parameter with a reserved_name "{}"'.format(id))

        # return error
        if errors:
            attr = self.__class__.Meta.attributes['expression']
            attr_err = InvalidAttribute(attr, errors)
            return InvalidObject(self, [attr_err])


class BiomassComponent(obj_model.Model):
    """ BiomassComponent

    A biomass reaction contains a list of BiomassComponent instances. Distinct BiomassComponents
    enable separate comments and references for each one.

    Attributes:
        id (:obj:`str`): unique identifier per BiomassComponent
        name (:obj:`str`): name
        biomass_reaction (:obj:`BiomassReaction`): the biomass reaction that uses the biomass component
        coefficient (:obj:`float`): the specie's reaction coefficient
        species (:obj:`Species`): species
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references
    """
    id = SlugAttribute()
    name = StringAttribute()
    biomass_reaction = ManyToOneAttribute('BiomassReaction', related_name='biomass_components')
    coefficient = FloatAttribute()
    species = ManyToOneAttribute(Species, related_name='biomass_components')
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='biomass_components')

    class Meta(obj_model.Model.Meta):
        unique_together = (('biomass_reaction', 'species'), )
        attribute_order = ('id', 'name', 'biomass_reaction',
                           'coefficient', 'species',
                           'comments', 'references')


class BiomassReaction(obj_model.Model):
    """ A pseudo-reaction used to represent the interface between metabolism and other 
    cell processes.

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        submodel (:obj:`Submodel`): submodel that uses this reaction
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references

    Related attributes:        
        objective_functions (:obj:`list` of :obj:`ObjectiveFunction`): objective functions that use this
            biomass reaction
        biomass_components (:obj:`list` of :obj:`BiomassComponent`): the components of this biomass reaction
    """
    id = SlugAttribute()
    name = StringAttribute()
    submodel = ManyToOneAttribute('Submodel', related_name='biomass_reactions')
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='biomass_reactions')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name', 'submodel', 'comments', 'references')
        indexed_attrs_tuples = (('id',), )

    def add_to_sbml_doc(self, sbml_document):
        """ Add a BiomassReaction to a libsbml SBML document.

        BiomassReactions are added to the SBML document because they can be used in a dFBA submodel's
        objective function. In fact the default objective function is the submodel's biomass reaction.
        Since SBML does not define BiomassReaction as a separate class, BiomassReactions are added
        to the SBML model as SBML reactions.
        CheckModel ensures that wc_lang BiomassReactions and Reactions have distinct ids.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.reaction`: the libsbml reaction that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml(sbml_document.getModel)

        # create SBML reaction in SBML document
        sbml_reaction = wrap_libsbml(sbml_model.createReaction)
        wrap_libsbml(sbml_reaction.setIdAttribute, self.id)
        wrap_libsbml(sbml_reaction.setName, self.name)
        wrap_libsbml(sbml_reaction.setReversible, False)
        wrap_libsbml(sbml_reaction.setFast, False)
        if self.comments:
            wrap_libsbml(sbml_reaction.setNotes, self.comments, True)

        # write biomass reaction participants to SBML document
        for biomass_component in self.biomass_components:
            if biomass_component.coefficient < 0:
                species_reference = wrap_libsbml(sbml_reaction.createReactant)
                wrap_libsbml(species_reference.setStoichiometry, -biomass_component.coefficient)
            elif 0 < biomass_component.coefficient:
                species_reference = wrap_libsbml(sbml_reaction.createProduct)
                wrap_libsbml(species_reference.setStoichiometry, biomass_component.coefficient)
            id = biomass_component.species.gen_sbml_id()
            wrap_libsbml(species_reference.setSpecies, id)
            wrap_libsbml(species_reference.setConstant, True)

        # the biomass reaction does not constrain the optimization, so set its bounds to 0 and INF
        fbc_reaction_plugin = wrap_libsbml(sbml_reaction.getPlugin, 'fbc')
        for bound in ['lower', 'upper']:
            # make a unique ID for each flux bound parameter
            # ids for wc_lang Parameters all start with 'parameter'
            param_id = "_biomass_reaction_{}_{}_bound".format(self.id, bound)
            param = create_sbml_parameter(sbml_model, id=param_id, value=0,
                                          units='mmol_per_gDW_per_hr')
            if bound == 'lower':
                wrap_libsbml(param.setValue, 0)
                wrap_libsbml(fbc_reaction_plugin.setLowerFluxBound, param_id)
            if bound == 'upper':
                wrap_libsbml(param.setValue, float('inf'))
                wrap_libsbml(fbc_reaction_plugin.setUpperFluxBound, param_id)
        return sbml_reaction


class Parameter(obj_model.Model):
    """ Parameter

    Attributes:
        id (:obj:`str`): unique identifier per model/submodel
        name (:obj:`str`): name
        model (:obj:`Model`): model
        submodels (:obj:`list` of :obj:`Submodel`): submodels
        value (:obj:`float`): value
        units (:obj:`str`): units of value
        comments (:obj:`str`): comments
        references (:obj:`list` of :obj:`Reference`): references

    Related attributes:
        functions (:obj:`list` of :obj:`FunctionExpression`): FunctionExpressions that use a Parameter
    """
    id = SlugAttribute(unique=False)
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='parameters')
    submodels = ManyToManyAttribute(Submodel, related_name='parameters')
    value = FloatAttribute(min=0)
    units = StringAttribute()
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='parameters')

    class Meta(obj_model.Model.Meta):
        unique_together = (('id', 'model', 'submodels', ), )
        attribute_order = ('id', 'name',
                           'model', 'submodels',
                           'value', 'units',
                           'comments', 'references')

    def add_to_sbml_doc(self, sbml_document):
        """ Add this Parameter to a libsbml SBML document.

        Args:
             sbml_document (:obj:`obj`): a `libsbml` SBMLDocument

        Returns:
            :obj:`libsbml.Parameter`: the libsbml Parameter that's created

        Raises:
            :obj:`LibSBMLError`: if calling `libsbml` raises an error
        """
        sbml_model = wrap_libsbml(sbml_document.getModel)
        # prefix id with 'parameter' so ids for wc_lang Parameters don't collide with ids for other libsbml parameters
        sbml_id = "parameter_{}".format(self.id)
        # TODO: use a standard unit ontology to map self.units to SBML model units
        if self.units == 'dimensionless':
            sbml_parameter = create_sbml_parameter(sbml_model, sbml_id, self.value, 'dimensionless_ud',
                                                   name=self.name)
        elif self.units == 's':
            sbml_parameter = create_sbml_parameter(sbml_model, sbml_id, self.value, 'second',
                                                   name=self.name)
        elif self.units == 'mmol/gDCW/h':
            sbml_parameter = create_sbml_parameter(sbml_model, sbml_id, self.value, 'mmol_per_gDW_per_hr',
                                                   name=self.name)
        else:
            sbml_parameter = create_sbml_parameter(sbml_model, sbml_id, self.value, 'dimensionless_ud',
                                                   name=self.name)

        return sbml_parameter


class Reference(obj_model.Model):
    """ Reference

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        title (:obj:`str`): title
        author (:obj:`str`): author(s)
        editor (:obj:`str`): editor(s)
        year (:obj:`int`): year
        type (:obj:`ReferenceType`): type
        publication (:obj:`str`): publication title
        publisher (:obj:`str`): publisher
        series (:obj:`str`): series
        volume (:obj:`str`): volume
        number (:obj:`str`): number
        issue (:obj:`str`): issue
        edition (:obj:`str`): edition
        chapter (:obj:`str`): chapter
        pages (:obj:`str`): page range
        comments (:obj:`str`): comments

    Related attributes:
        database_references (:obj:`list` of :obj:`DatabaseReference`): database references
        taxa (:obj:`list` of :obj:`Taxon`): taxa
        submodels (:obj:`list` of :obj:`Submodel`): submodels
        compartments (:obj:`list` of :obj:`Compartment`): compartments
        species_types (:obj:`list` of :obj:`SpeciesType`): species types
        species (:obj:`list` of :obj:`Species`): species
        concentrations (:obj:`list` of :obj:`Concentration`): concentrations
        reactions (:obj:`list` of :obj:`Reaction`): reactions
        rate_laws (:obj:`list` of :obj:`RateLaw`): rate laws
        biomass_components (:obj:`list` of :obj:`BiomassComponent`): biomass components
        parameters (:obj:`list` of :obj:`Parameter`): parameters
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='references')
    title = StringAttribute()
    author = StringAttribute()
    editor = StringAttribute()
    year = PositiveIntegerAttribute()
    type = EnumAttribute(ReferenceType)
    publication = StringAttribute()
    publisher = StringAttribute()
    series = StringAttribute()
    volume = StringAttribute()
    number = StringAttribute()
    issue = StringAttribute()
    edition = StringAttribute()
    chapter = StringAttribute()
    pages = StringAttribute()
    comments = LongStringAttribute()

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name',
                           'title', 'author', 'editor', 'year', 'type', 'publication', 'publisher',
                           'series', 'volume', 'number', 'issue', 'edition', 'chapter', 'pages',
                           'comments')


class DatabaseReference(obj_model.Model):
    """ Reference to a source database entry

    Attributes:
        database (:obj:`str`): database name
        id (:obj:`str`): id of database entry
        url (:obj:`str`): URL of database entry
        model (:obj:`Model`): model
        taxon (:obj:`Taxon`): taxon
        submodel (:obj:`Submodel`): submodel
        species_type (:obj:`SpeciesType`): species type
        reaction (:obj:`Reaction`): reaction
        reference (:obj:`Reference`): reference
    """

    database = StringAttribute(min_length=1)
    id = StringAttribute(verbose_name='ID', min_length=1)
    url = UrlAttribute(verbose_name='URL')
    model = ManyToOneAttribute(Model, related_name='database_references')
    taxon = ManyToOneAttribute(Taxon, related_name='database_references')
    submodel = ManyToOneAttribute(Submodel, related_name='database_references')
    compartment = ManyToOneAttribute(Compartment, related_name='database_references')
    species_type = ManyToOneAttribute(SpeciesType, related_name='database_references')
    reaction = ManyToOneAttribute(Reaction, related_name='database_references')
    reference = ManyToOneAttribute(Reference, related_name='database_references')

    class Meta(obj_model.Model.Meta):
        unique_together = (('database', 'id', ), )
        attribute_order = ('database', 'id', 'url',
                           'model', 'taxon', 'submodel', 'compartment', 'species_type', 'reaction', 'reference')
        frozen_columns = 2
        ordering = ('database', 'id', )

    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return '{}: {}'.format(self.database, self.id)
