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
                       OneToOneAttribute, ManyToOneAttribute, ManyToManyAttribute,
                       InvalidModel, InvalidObject, InvalidAttribute, TabularOrientation)
import obj_model
from wc_utils.util.enumerate import CaseInsensitiveEnum, CaseInsensitiveEnumMeta
from wc_utils.util.list import det_dedupe
from wc_lang.sbml.util import (wrap_libsbml, str_to_xmlstr, LibSBMLError,
                               init_sbml_model, create_sbml_parameter, add_sbml_unit, UNIT_KIND_DIMENSIONLESS)
from wc_lang.expression_utils import RateLawUtils, WcLangExpression, WcLangExpressionError

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
    ('moles dm^-2', 9),
])


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


class OneToOneSpeciesAttribute(OneToOneAttribute):
    """ Species attribute """

    def __init__(self, related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(OneToOneSpeciesAttribute, self).__init__('Species',
                                                       related_name=related_name, min_related=1, min_related_rev=0,
                                                       verbose_name=verbose_name, verbose_related_name=verbose_related_name, help=help)

    def serialize(self, value, encoded=None):
        """ Serialize related object

        Args:
            value (:obj:`Model`): Python representation
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation
        """
        return value.serialize()

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of :obj:`list` of :obj:`SpeciesCoefficient`, :obj:`InvalidAttribute` or :obj:`None`: :obj:`tuple` of cleaned value
                and cleaning error
        """
        return Species.deserialize(self, value, objects)


class ObservableSpeciesParticipantAttribute(ManyToManyAttribute):
    """ Inline separated list of species and their weights of an observable

    Attributes:
        separator (:obj:`str`): list separator
    """

    def __init__(self, related_class, separator=' + ', related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_class (:obj:`class`): related class
            separator (:obj:`str`, optional): list separator
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(ObservableSpeciesParticipantAttribute, self).__init__(related_class, related_name=related_name,
                                                                    verbose_name=verbose_name,
                                                                    verbose_related_name=verbose_related_name,
                                                                    help=help)
        self.separator = separator

    def serialize(self, spec_coeffs, encoded=None):
        """ Serialize related object

        Args:
            spec_coeffs (:obj:`list` of `Model`): Python representation of species and their coefficients
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation
        """
        if not spec_coeffs:
            return ''

        spec_coeff_strs = []
        for spec_coeff_obj in spec_coeffs:
            spec_coeff_str = spec_coeff_obj.serialize(show_compartment=True, show_coefficient_sign=True)
            spec_coeff_strs.append(spec_coeff_str)

        return self.separator.join(spec_coeff_strs)

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of `list` of `related_class`, `InvalidAttribute` or `None`: tuple of cleaned value
                and cleaning error
        """
        if not value:
            return ([], None)

        pat_id = '([a-z][a-z0-9_]*)'
        pat_coeff = '\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\)'
        pat_spec_coeff = '({} )*({}\[{}\])'.format(pat_coeff, pat_id, pat_id)
        pat_observable = '^{}( \+ {})*$'.format(pat_spec_coeff, pat_spec_coeff)
        if not re.match(pat_observable, value, flags=re.I):
            return (None, InvalidAttribute(self, ['Incorrectly formatted observable: {}'.format(value)]))

        spec_coeff_objs = []
        errors = []
        for spec_coeff_match in re.findall(pat_spec_coeff, value, flags=re.I):
            spec_type_errors = []

            spec_type_id = spec_coeff_match[5]
            if spec_type_id in objects[SpeciesType]:
                spec_type = objects[SpeciesType][spec_type_id]
            else:
                spec_type_errors.append('Undefined species type "{}"'.format(spec_type_id))

            compartment_id = spec_coeff_match[6]
            if compartment_id in objects[Compartment]:
                compartment = objects[Compartment][compartment_id]
            else:
                spec_type_errors.append('Undefined compartment "{}"'.format(compartment_id))

            coefficient = float(spec_coeff_match[1] or 1.)

            if spec_type_errors:
                errors += spec_type_errors
            elif coefficient != 0:
                spec_id = Species.gen_id(spec_type.get_primary_attribute(), compartment.get_primary_attribute())
                obj, error = Species.deserialize(self, spec_id, objects)

                if error:
                    raise ValueError('Invalid object "{}"'.format(spec_primary_attribute)
                                     )  # pragma: no cover # unreachable due to error checking above

                if self.related_class not in objects:
                    objects[self.related_class] = {}
                serialized_value = self.related_class._serialize(obj, coefficient)
                if serialized_value in objects[self.related_class]:
                    spec_coeff_obj = objects[self.related_class][serialized_value]
                else:
                    spec_coeff_obj = self.related_class(species=obj, coefficient=coefficient)
                    objects[self.related_class][serialized_value] = spec_coeff_obj
                spec_coeff_objs.append(spec_coeff_obj)

        if errors:
            return (None, InvalidAttribute(self, errors))
        return (spec_coeff_objs, None)


class ObservableObservableParticipantAttribute(ManyToManyAttribute):
    """ Inline separated list of observables and their weights of an observable

    Attributes:
        separator (:obj:`str`): list separator
    """

    def __init__(self, related_class, separator=' + ', related_name='', verbose_name='', verbose_related_name='', help=''):
        """
        Args:
            related_class (:obj:`class`): related class
            separator (:obj:`str`, optional): list separator
            related_name (:obj:`str`, optional): name of related attribute on `related_class`
            verbose_name (:obj:`str`, optional): verbose name
            verbose_related_name (:obj:`str`, optional): verbose related name
            help (:obj:`str`, optional): help message
        """
        super(ObservableObservableParticipantAttribute, self).__init__(related_class, related_name=related_name,
                                                                       verbose_name=verbose_name,
                                                                       verbose_related_name=verbose_related_name,
                                                                       help=help)
        self.separator = separator

    def serialize(self, obs_coeffs, encoded=None):
        """ Serialize related object

        Args:
            obs_coeffs (:obj:`list` of `Model`): Python representation of observables and their coefficients
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation
        """
        if not obs_coeffs:
            return ''

        obs_coeff_strs = []
        for obs_coeff_obj in obs_coeffs:
            obs_coeff_str = obs_coeff_obj.serialize()
            obs_coeff_strs.append(obs_coeff_str)

        return self.separator.join(obs_coeff_strs)

    def deserialize(self, value, objects, decoded=None):
        """ Deserialize value

        Args:
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model
            decoded (:obj:`dict`, optional): dictionary of objects that have already been decoded

        Returns:
            :obj:`tuple` of `list` of `related_class`, `InvalidAttribute` or `None`: tuple of cleaned value
                and cleaning error
        """
        if not value:
            return ([], None)

        pat_id = '([a-z][a-z0-9_]*)'
        pat_coeff = '\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\)'
        pat_obs_coeff = '({} )*({})'.format(pat_coeff, pat_id, pat_id)
        pat_observable = '^{}( \+ {})*$'.format(pat_obs_coeff, pat_obs_coeff)
        if not re.match(pat_observable, value, flags=re.I):
            return (None, InvalidAttribute(self, ['Incorrectly formatted observable: {}'.format(value)]))

        obs_coeff_objs = []
        errors = []
        for obs_coeff_match in re.findall(pat_obs_coeff, value, flags=re.I):
            obs_errors = []

            obs_id = obs_coeff_match[5]
            if obs_id in objects[Observable]:
                obs = objects[Observable][obs_id]
            else:
                obs_errors.append('Undefined observable "{}"'.format(obs_id))

            coefficient = float(obs_coeff_match[1] or 1.)

            if obs_errors:
                errors += obs_errors
            elif coefficient != 0:
                if self.related_class not in objects:
                    objects[self.related_class] = {}
                serialized_value = self.related_class._serialize(obs, coefficient)
                if serialized_value in objects[self.related_class]:
                    obs_coeff_obj = objects[self.related_class][serialized_value]
                else:
                    obs_coeff_obj = self.related_class(observable=obs, coefficient=coefficient)
                    objects[self.related_class][serialized_value] = obs_coeff_obj
                obs_coeff_objs.append(obs_coeff_obj)

        if errors:
            return (None, InvalidAttribute(self, errors))
        return (obs_coeff_objs, None)


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
            participants (:obj:`list` of `SpeciesCoefficient`): Python representation of reaction participants
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

        id = '[a-z][a-z0-9_]*'
        stoch = '\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\)'
        gbl_part = '({} *)*({})'.format(stoch, id)
        lcl_part = '({} *)*({}\[{}\])'.format(stoch, id, id)
        gbl_side = '{}( *\+ *{})*'.format(gbl_part, gbl_part)
        lcl_side = '{}( *\+ *{})*'.format(lcl_part, lcl_part)
        gbl_pattern = '^\[({})\]: *({}|) *==> *({}|)$'.format(id, gbl_side, gbl_side)
        lcl_pattern = '^({}|) *==> *({}|)$'.format(lcl_side, lcl_side)

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
        parts_str = re.findall('(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*)(\[([a-z][a-z0-9_]*)\])*', value, flags=re.I)

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
                spec_primary_attribute = Species.gen_id(species_type, compartment)
                species, error = Species.deserialize(self, spec_primary_attribute, objects)
                if error:
                    raise ValueError('Invalid species "{}"'.format(spec_primary_attribute)
                                     )  # pragma: no cover # unreachable due to error checking above

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
            value (:obj:`list` of `SpeciesCoefficient`): value of attribute to validate

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

    def serialize(self, value, encoded=None):
        """ Serialize related object

        Args:
            value (:obj:`RateLawEquation`): the related RateLawEquation
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation of the rate law equation
        """
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
        return RateLawEquation.deserialize(self, value, objects)


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

        taxon (:obj:`Taxon`): taxon
        submodels (:obj:`list` of `Submodel`): submodels
        compartments (:obj:`list` of `Compartment`): compartments
        species_types (:obj:`list` of `SpeciesType`): species types
        observables (:obj:`list` of `Observable`): observables
        functions (:obj:`list` of `Function`): functions
        parameters (:obj:`list` of `Parameter`): parameters
        stop_conditions (:obj:`list` of `StopCondition`): stop conditions
        references (:obj:`list` of `Reference`): references
        database_references (:obj:`list` of `DatabaseReference`): database references
    """
    id = SlugAttribute()
    name = StringAttribute()
    version = RegexAttribute(min_length=1, pattern='^[0-9]+\.[0-9+]\.[0-9]+', flags=re.I)
    url = obj_model.core.StringAttribute(verbose_name='URL')
    branch = obj_model.core.StringAttribute()
    revision = obj_model.core.StringAttribute()
    wc_lang_version = RegexAttribute(min_length=1, pattern='^[0-9]+\.[0-9+]\.[0-9]+', flags=re.I,
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
            :obj:`list` of `Compartment`: compartments
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
            :obj:`list` of `SpeciesType`: species types
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
            :obj:`list` of `Submodel`: submodels
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
            :obj:`list` of `Species`: species
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
            :obj:`list` of `Concentration`: concentations
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
            :obj:`list` of `Reaction`: reactions
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
            :obj:`list` of `BiomassReaction`: biomass reactions
        """
        if '__type' in kwargs:
            __type = kwargs.pop('__type')

        biomass_reactions = []
        for submodel in self.submodels:
            if submodel.biomass_reaction and submodel.biomass_reaction.has_attr_vals(__type=__type, **kwargs):
                biomass_reactions.append(submodel.biomass_reaction)
        return det_dedupe(biomass_reactions)

    def get_rate_laws(self, __type=None, **kwargs):
        """ Get all rate laws from reactions

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of `RateLaw`: rate laws
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
            :obj:`list` of `Parameter`: parameters
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
            :obj:`list` of `Reference`: references
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
        references (:obj:`list` of `Reference`): references

        database_references (:obj:`list` of `DatabaseReference`): database references
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
        compartment (:obj:`Compartment`): the compartment that contains the submodel's species
        biomass_reaction (:obj:`BiomassReaction`): the growth reaction for a dFBA submodel
        objective_function (:obj:`ObjectiveFunction`, optional): objective function for a dFBA submodel;
            if not initialized, then `biomass_reaction` is used as the objective function
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        database_references (:obj:`list` of `DatabaseReference`): database references
        reactions (:obj:`list` of `Reaction`): reactions
        parameters (:obj:`list` of `Parameter`): parameters
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='submodels')
    algorithm = EnumAttribute(SubmodelAlgorithm, default=SubmodelAlgorithm.ssa)
    compartment = ManyToOneAttribute('Compartment', related_name='submodels')
    biomass_reaction = ManyToOneAttribute('BiomassReaction', related_name='submodels')
    objective_function = ObjectiveFunctionAttribute(related_name='submodels')
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='submodels')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name',
                           'algorithm', 'compartment', 'biomass_reaction',
                           'objective_function', 'comments', 'references')
        indexed_attrs_tuples = (('id',), )

    def get_species(self, __type=None, **kwargs):
        """ Get species in reactions

        Args:
            __type (:obj:`types.TypeType` or :obj:`tuple` of :obj:`types.TypeType`): subclass(es) of :obj:`Model`
            **kwargs (:obj:`dict` of `str`:`object`): dictionary of attribute name/value pairs to find matching
                objects

        Returns:
            :obj:`list` of `Species`: species in reactions
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
        reactions (:obj:`list` of `Reaction`): if linear, reactions whose fluxes are used in the
            objective function
        reaction_coefficients (:obj:`list` of `float`): parallel list of coefficients for reactions
        biomass_reactions (:obj:`list` of `BiomassReaction`): if linear, biomass reactions whose
            fluxes are used in the objective function
        biomass_reaction_coefficients (:obj:`list` of `float`): parallel list of coefficients for
            reactions in biomass_reactions

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
            :obj:`list` of `Species`: species produced by this objective function
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
                    tmp_species_ids.append(Species.gen_id(biomass_component.species_type,
                                                          biomass_reaction.compartment))
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
        references (:obj:`list` of `Reference`): references

        species (:obj:`list` of `Species`): species in this compartment
        submodels (:obj:`list` of `Submodel`): submodels that model reactions in this compartment
        database_references (:obj:`list` of `DatabaseReference`): database references
        biomass_reactions (:obj:`list` of `BiomassReaction`): biomass reactions defined for this
            compartment
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
        references (:obj:`list` of `Reference`): references

        database_references (:obj:`list` of `DatabaseReference`): database references
        concentrations (:obj:`list` of `Concentration`): concentrations
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='species_types')
    structure = LongStringAttribute()
    empirical_formula = RegexAttribute(pattern='^([A-Z][a-z]?\d*)*$')
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
        species_type (:obj:`SpeciesType`): species type
        compartment (:obj:`Compartment`): compartment

        concentration (:obj:`Concentration`): concentration
        species_coefficients (:obj:`list` of `SpeciesCoefficient`): participations in reactions and observables
        rate_law_equations (:obj:`list` of `RateLawEquation`): rate law equations
    """
    species_type = ManyToOneAttribute(SpeciesType, related_name='species', min_related=1)
    compartment = ManyToOneAttribute(Compartment, related_name='species', min_related=1)

    class Meta(obj_model.Model.Meta):
        attribute_order = ('species_type', 'compartment')
        frozen_columns = 1
        tabular_orientation = TabularOrientation.inline
        unique_together = (('species_type', 'compartment', ), )
        ordering = ('species_type', 'compartment')
        indexed_attrs_tuples = (('species_type', 'compartment'), )
        token_pattern = (token.NAME, token.LSQB, token.NAME, token.RSQB)

    @staticmethod
    def gen_id(species_type, compartment):
        """ Generate a Species' primary identifier

        Args:
            species_type (:obj:`object`): a `SpeciesType`, or its id
            compartment (:obj:`object`): a `Compartment`, or its id

        Returns:
            :obj:`str`: canonical identifier for a specie in a compartment, 'species_type_id[compartment_id]'
        """
        if isinstance(species_type, SpeciesType) and isinstance(compartment, Compartment):
            species_type_id = species_type.get_primary_attribute()
            compartment_id = compartment.get_primary_attribute()
        elif isinstance(species_type, string_types) and isinstance(compartment, string_types):
            species_type_id = species_type
            compartment_id = compartment
        else:
            raise ValueError("gen_id: incorrect parameter types: {}, {}".format(species_type, compartment))
        return '{}[{}]'.format(species_type_id, compartment_id)

    def id(self):
        """ Provide a Species' primary identifier

        Returns:
            :obj:`str`: canonical identifier for a specie in a compartment, 'specie_id[compartment_id]'
        """
        return self.serialize()

    def serialize(self):
        """ Provide a Species' primary identifier

        Returns:
            :obj:`str`: canonical identifier for a specie in a compartment, 'specie_id[compartment_id]'
        """
        return self.gen_id(self.species_type, self.compartment)

    @staticmethod
    def get(ids, species_iterator):
        """ Find some Species instances

        Args:
            ids (:obj:`Iterator` of `str`): an iterator over some species identifiers
            species_iterator (:obj:`Iterator`): an iterator over some species

        Returns:
            :obj:`list` of `Species` or `None`: each element of the `list` corresponds to an element
                of `ids` and contains either a `Species` with `id()` equal to the element in `ids`,
                or `None` indicating that `species_iterator` does not contain a matching `Species`
        """
        # TODO: this costs O(|ids||species_iterator|); replace with O(|ids|) operation using obj_model.Manager.get()
        rv = []
        for id in ids:
            s = None
            for specie in species_iterator:
                if specie.id() == id:
                    s = specie
                    # one match is enough
                    break
            rv.append(s)
        return rv

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
        if cls in objects and value in objects[cls]:
            return (objects[cls][value], None)

        match = re.match('^([a-z][a-z0-9_]*)\[([a-z][a-z0-9_]*)\]$', value, flags=re.I)
        if match:
            errors = []

            if match.group(1) in objects[SpeciesType]:
                species_type = objects[SpeciesType][match.group(1)]
            else:
                errors.append('Species type "{}" is not defined'.format(match.group(1)))

            if match.group(2) in objects[Compartment]:
                compartment = objects[Compartment][match.group(2)]
            else:
                errors.append('Compartment "{}" is not defined'.format(match.group(2)))

            if errors:
                return (None, InvalidAttribute(attribute, errors))
            else:
                if cls not in objects:
                    objects[cls] = {}
                serialized_val = cls.gen_id(species_type, compartment)
                if serialized_val in objects[cls]:
                    obj = objects[cls][serialized_val]
                else:
                    obj = cls(species_type=species_type, compartment=compartment)
                    objects[cls][serialized_val] = obj
                return (obj, None)

        return (None, InvalidAttribute(attribute, ['Invalid species']))

    def xml_id(self):
        """ Make a Species id that satisfies the SBML string id syntax.

        Use `make_xml_id()` to make a SBML id.

        Returns:
            :obj:`str`: an SBML id
        """
        return Species.make_xml_id(
            self.species_type.get_primary_attribute(),
            self.compartment.get_primary_attribute())

    @staticmethod
    def make_xml_id(species_type_id, compartment_id):
        """ Make a Species id that satisfies the SBML string id syntax.

        Replaces the '[' and ']' in Species.id() with double-underscores '__'.
        See Finney and Hucka, "Systems Biology Markup Language (SBML) Level 2: Structures and
        Facilities for Model Definitions", 2003, section 3.4.

        Returns:
            :obj:`str`: an SBML id
        """
        return '{}__{}__'.format(species_type_id, compartment_id)

    @staticmethod
    def xml_id_to_id(xml_id):
        """ Convert an `xml_id` to its species id.

        Returns:
            :obj:`str`: a species id
        """
        return xml_id.replace('__', '[', 1).replace('__', ']', 1)

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
        wrap_libsbml(sbml_species.setIdAttribute, self.xml_id())

        # add some SpeciesType data
        wrap_libsbml(sbml_species.setName, self.species_type.name)
        if self.species_type.comments:
            wrap_libsbml(sbml_species.setNotes, self.species_type.comments, True)

        # set Compartment, which must already be in the SBML document
        wrap_libsbml(sbml_species.setCompartment, self.compartment.id)

        # set the Initial Concentration
        wrap_libsbml(sbml_species.setInitialConcentration, self.concentration.value)

        return sbml_species


class Concentration(obj_model.Model):
    """ Species concentration

    Attributes:
        species (:obj:`Species`): species
        value (:obj:`float`): value
        units (:obj:`str`): units; default units is 'M'
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references
    """
    species = OneToOneSpeciesAttribute(related_name='concentration')
    value = FloatAttribute(min=0)
    units = EnumAttribute(ConcentrationUnit)
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
            :obj:`str`: value of primary attribute
        """
        return self.species.serialize()


class Observable(obj_model.Model):
    """ An observable is a weighted sum of the abundances of one or more species or other observables

    Attributes:
        id (:obj:`str`): id
        name (:obj:`str`): name
        model (:obj:`Model`): model
        species (:obj:`list` of :obj:`SpeciesCoefficient`): species and their coefficients
        observables (:obj:`list` of :obj:`ObservableCoefficient`): list of component observables and
            their coefficients
        comments (:obj:`str`): comments

    Related attributes:
        observable_coefficients (:obj:`list` of `ObservableCoefficient`): participations in observables
        functions (:obj:`list` of `FunctionExpression`): FunctionExpressions that use an Observable
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='observables')
    species = ObservableSpeciesParticipantAttribute('SpeciesCoefficient', related_name='observables')
    observables = ObservableObservableParticipantAttribute('ObservableCoefficient', related_name='observables')
    comments = LongStringAttribute()

    class Meta(obj_model.Model.Meta):
        """
        Attributes:
            valid_used_models (:obj:`tuple` of `str`): names of `obj_model.Model`s in this module that an
                `Observable` is allowed to reference in its `expression`
        """
        attribute_order = ('id', 'name', 'species', 'observables', 'comments')
        indexed_attrs_tuples = (('id',), )
        valid_used_models = ('Species', 'Observable')


class FunctionExpression(obj_model.Model):
    """ A mathematical expression using zero or more Observables, Parameters and other Functions.

    Attributes:
        expression (:obj:`LongStringAttribute`): mathematical expression of the Function
        analyzed_expr (:obj:`WcLangExpression`): an analyzed expression; not an `obj_model.Model`
        observables (:obj:`list` of `Observable`): Observables used by this function
        parameters (:obj:`list` of `Parameter`): Parameters used by this function
        functions (:obj:`list` of `Function`): other Functions used by this function

    Related attributes:
        functions (:obj:`list` of `Function`): Functions that use a Function
    """
    expression = LongStringAttribute(primary=True, unique=True)
    observables = ManyToManyAttribute(Observable, related_name='functions')
    parameters = ManyToManyAttribute('Parameter', related_name='functions')
    functions = ManyToManyAttribute('Function', related_name='functions')
    '''
    # construct object and create `analyzed_expr` attribute
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.analyzed_expr = None
    '''
    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return self.expression
    @classmethod
    def deserialize(cls, attribute, expression, objects):
        """ Deserialize expression

        Args:
            attribute (:obj:`Attribute`):
            expression (:obj:`str`): string representation of Python mathematical expression
            objects (:obj:`dict`): dictionary of objects which can be used in `expression`, grouped by model

        Returns:
            :obj:`tuple`: on error return (`None`, `InvalidAttribute`),
                otherwise return (object in this class with instantiated `analyzed_expr`, `None`)
        """
        expr_field = 'expression'
        try:
            analyzed_expr = WcLangExpression(cls, expr_field, expression, objects)
        except WcLangExpressionError as e:
            return (None, InvalidAttribute(attribute, [str(e)]))
        rv = analyzed_expr.tokenize()
        if rv[0] is None:
            errors = rv[1]
            return (None, InvalidAttribute(attribute, errors))

        _, used_objects = rv
        # todo: automate this section with valid_used_models
        observables = []
        if Observable in used_objects:
            observables = list(used_objects[Observable].values())
        parameters = []
        if Parameter in used_objects:
            parameters = list(used_objects[Parameter].values())
        functions = []
        if Function in used_objects:
            functions = list(used_objects[Function].values())
        # reuse an identical FunctionExpression if it exists, otherwise create it
        if cls not in objects:
            objects[cls] = {}
        if expression in objects[cls]:
            obj = objects[cls][expression]
        else:
            obj = cls(expression=expression, observables=observables, parameters=parameters,
                functions=functions)
            objects[cls][expression] = obj
        obj.analyzed_expr = analyzed_expr
        return (obj, None)
    def validate(self):
        """ Determine whether a `FunctionExpression` is valid by eval'ing its deserialized expression.

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors in an `InvalidObject` instance
        """
        try:
            self.analyzed_expr.test_eval_expr()
            # return `None` to indicate valid object
            return None
        except WcLangExpressionError as e:
            attr = self.__class__.Meta.attributes['expression']
            attr_err = InvalidAttribute(attr, [str(e)])
            return InvalidObject(self, [attr_err])
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
    def serialize(self, value):
        """ Serialize related object

        Args:
            value (:obj:`FunctionExpression`): the related FunctionExpression
            encoded (:obj:`dict`, optional): dictionary of objects that have already been encoded

        Returns:
            :obj:`str`: simple Python representation of the function expression
        """
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
        return FunctionExpression.deserialize(self, value, objects)
class Function(obj_model.Model):
    """ A reusable mathematical function.

    Attributes:
        id (:obj:`str`): id
        name (:obj:`str`): name
        model (:obj:`Model`): model
        expression (:obj:`FunctionExpression`): mathematical expression of the Function
        comments (:obj:`str`): comments

    Related attributes:
        functions (:obj:`list` of `Function`): Functions that use a Function
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='functions')
    expression = FunctionExpressionAttribute(related_name='function')
    comments = LongStringAttribute()
    class Meta(obj_model.Model.Meta):
        """
        Attributes:
            valid_functions (:obj:`tuple` of `builtin_function_or_method`): tuple of functions that
                can be used in this `Function`s `expression`
            valid_used_models (:obj:`tuple` of `str`): names of `obj_model.Model`s in this module that a
                `Function` is allowed to reference in its `expression`
        """
        unique_together = (('id', ), )
        attribute_order = ('id', 'name', 'expression', 'comments')
        valid_functions = (ceil, floor, exp, pow, log, log10, min, max)
        valid_used_models = ('Parameter', 'Observable', 'Function')
    def serialize(self):
        """ Generate string representation

        Returns:
            :obj:`str`: value of primary attribute
        """
        return self.expression.serialize()


class Reaction(obj_model.Model):
    """ Reaction

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        submodel (:obj:`Submodel`): submodel that reaction belongs to
        participants (:obj:`list` of `SpeciesCoefficient`): participants
        reversible (:obj:`bool`): indicates if reaction is thermodynamically reversible
        min_flux (:obj:`float`): minimum flux bound for solving an FBA model; negative for reversible reactions
        max_flux (:obj:`float`): maximum flux bound for solving an FBA model
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        database_references (:obj:`list` of `DatabaseReference`): database references
        rate_laws (:obj:`list` of `RateLaw`): rate laws; if present, rate_laws[0] is the forward
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
        wrap_libsbml(sbml_reaction.setCompartment, self.submodel.compartment.id)
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
            wrap_libsbml(species_reference.setSpecies, participant.species.xml_id())
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
            pattern = '^(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*)$'
        else:
            pattern = '^(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*\[[a-z][a-z0-9_]*\])$'

        match = re.match(pattern, value, flags=re.I)
        if match:
            errors = []

            coefficient = float(match.group(2) or 1.)

            if compartment:
                species_id = Species.gen_id(match.group(5), compartment.get_primary_attribute())
            else:
                species_id = match.group(5)

            species, error = Species.deserialize(attribute, species_id, objects)
            if error:
                return (None, error)

            serial_val = cls._serialize(species, coefficient)
            if cls in objects and serial_val in objects[cls]:
                return (objects[cls][serial_val], None)

            if cls not in objects:
                objects[cls] = {}
            serialized_val = cls._serialize(species, coefficient)
            if serialized_val in objects[cls]:
                obj = objects[cls][serialized_val]
            else:
                obj = cls(species=species, coefficient=coefficient)
                objects[cls][serialized_val] = obj
            return (obj, None)

        else:
            attr = cls.Meta.attributes['species']
            return (None, InvalidAttribute(attr, ['Invalid species coefficient']))


class ObservableCoefficient(obj_model.Model):
    """ A tuple of observable and coefficient

    Attributes:
        observable (:obj:`Observable`): observable
        coefficient (:obj:`float`): coefficient
    """
    observable = ManyToOneAttribute(Observable, related_name='observable_coefficients')
    coefficient = FloatAttribute(nan=False)

    class Meta(obj_model.Model.Meta):
        attribute_order = ('observable', 'coefficient')
        frozen_columns = 1
        tabular_orientation = TabularOrientation.inline
        ordering = ('observable',)

    def serialize(self):
        """ Serialize related object

        Returns:
            :obj:`str`: simple Python representation
        """
        return self._serialize(self.observable, self.coefficient)

    @staticmethod
    def _serialize(observable, coefficient):
        """ Serialize values

        Args:
            observable (:obj:`Observable`): observable
            coefficient (:obj:`float`): coefficient

        Returns:
            :obj:`str`: simple Python representation
        """
        coefficient = float(coefficient)

        if coefficient == 1:
            coefficient_str = ''
        elif coefficient % 1 == 0 and abs(coefficient) < 1000:
            coefficient_str = '({:.0f}) '.format(coefficient)
        else:
            coefficient_str = '({:e}) '.format(coefficient)

        return '{}{}'.format(coefficient_str, observable.serialize())

    @classmethod
    def deserialize(cls, attribute, value, objects):
        """ Deserialize value

        Args:
            attribute (:obj:`Attribute`): attribute
            value (:obj:`str`): String representation
            objects (:obj:`dict`): dictionary of objects, grouped by model

        Returns:
            :obj:`tuple` of `list` of `ObservableCoefficient`, `InvalidAttribute` or `None`: tuple of cleaned value
                and cleaning error
        """
        errors = []

        pattern = '^(\(((\d*\.?\d+|\d+\.)(e[\-\+]?\d+)?)\) )*([a-z][a-z0-9_]*)$'

        match = re.match(pattern, value, flags=re.I)
        if match:
            errors = []

            coefficient = float(match.group(2) or 1.)

            obs_id = match.group(5)

            observable, error = Observable.deserialize(obs_id, objects)
            if error:
                return (None, error)

            serial_val = cls._serialize(observable, coefficient)
            if cls in objects and serial_val in objects[cls]:
                return (objects[cls][serial_val], None)

            if cls not in objects:
                objects[cls] = {}
            serialized_val = cls._serialize(observable, coefficient)
            if serialized_val in objects[cls]:
                obj = objects[cls][serialized_val]
            else:
                obj = cls(observable=observable, coefficient=coefficient)
                objects[cls][serialized_val] = obj
            return (obj, None)

        else:
            attr = cls.Meta.attributes['observable']
            return (None, InvalidAttribute(attr, ['Invalid observable coefficient']))


class RateLaw(obj_model.Model):
    """ Rate law

    Attributes:
        reaction (:obj:`Reaction`): reaction
        direction (:obj:`RateLawDirection`): direction
        equation (:obj:`RateLawEquation`): equation
        k_cat (:obj:`float`): v_max (reactions enz^-1 s^-1)
        k_m (:obj:`float`): k_m (M)
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references
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
                transcoded = RateLawUtils.transcode(self.equation, self.equation.modifiers, self.equation.parameters)
                concentrations = {}
                parameters = {}
                for s in self.equation.modifiers:
                    concentrations[s.id()] = 1.0
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
        analyzed_expr (:obj:`WcLangExpression`): an analyzed expression
        transcoded (:obj:`str`): transcoded expression, suitable for evaluating as a Python expression
        modifiers (:obj:`list` of `Species`): species whose concentrations are used in the rate law
        parameters (:obj:`list` of `Species`): parameters whose values are used in the rate law

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
        modifier_pattern = '(^|[^a-z0-9_])({}\[{}\])([^a-z0-9_]|$)'.format(SpeciesType.id.pattern[1:-1],
                                                                           Compartment.id.pattern[1:-1])
        parameter_pattern = '(^|[^a-z0-9_\[\]])({})([^a-z0-9_\[\]]|$)'.format(Parameter.id.pattern[1:-1])

        reserved_names = set([func.__name__ for func in RateLawEquation.Meta.valid_functions] + ['k_cat', 'k_m'])

        try:
            for match in re.findall(modifier_pattern, value, flags=re.I):
                species, error = Species.deserialize(attribute, match[1], objects)
                if error:
                    errors += error.messages
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
        modifier_pattern = '(^|[^a-z0-9_])({}\[{}\])([^a-z0-9_]|$)'.format(SpeciesType.id.pattern[1:-1],
                                                                           Compartment.id.pattern[1:-1])
        entity_ids = set([x[1] for x in re.findall(modifier_pattern, self.expression, flags=re.I)])
        if modifier_ids != entity_ids:
            for id in modifier_ids.difference(entity_ids):
                errors.append('Extraneous modifier "{}"'.format(id))

            for id in entity_ids.difference(modifier_ids):
                errors.append('Undefined modifier "{}"'.format(id))

        # check parameters
        parameter_ids = set((x.serialize() for x in self.parameters))
        parameter_pattern = '(^|[^a-z0-9_\[\]])({})([^a-z0-9_\[\]]|$)'.format(Parameter.id.pattern[1:-1])
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
        species_type (:obj:`SpeciesType`): the specie type
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references
    """
    id = SlugAttribute()
    name = StringAttribute()
    biomass_reaction = ManyToOneAttribute('BiomassReaction', related_name='biomass_components')
    coefficient = FloatAttribute()
    species_type = ManyToOneAttribute(SpeciesType, related_name='biomass_components')
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='biomass_components')

    class Meta(obj_model.Model.Meta):
        unique_together = (('biomass_reaction', 'species_type'), )
        attribute_order = ('id', 'name', 'biomass_reaction',
                           'coefficient', 'species_type',
                           'comments', 'references')


class BiomassReaction(obj_model.Model):
    """ BiomassReaction

    A pseudo-reaction used to estimate a cell's growth.

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        compartment (:obj:`Compartment`): the compartment containing this BiomassReaction's species
        comments (:obj:`str`): comments
        references (:obj:`list` of `Reference`): references

        submodels (:obj:`list` of `Submodel`): submodels that use this biomass reaction
        objective_functions (:obj:`list` of `ObjectiveFunction`): objective functions that use this
            biomass reaction
        biomass_components (:obj:`list` of `BiomassComponent`): the components of this biomass reaction
    """
    id = SlugAttribute()
    name = StringAttribute()
    compartment = ManyToOneAttribute(Compartment, related_name='biomass_reactions')
    comments = LongStringAttribute()
    references = ManyToManyAttribute('Reference', related_name='biomass_reactions')

    class Meta(obj_model.Model.Meta):
        attribute_order = ('id', 'name', 'compartment', 'comments', 'references')
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
        wrap_libsbml(sbml_reaction.setCompartment, self.compartment.id)
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
            id = Species.make_xml_id(
                biomass_component.species_type.get_primary_attribute(),
                self.compartment.id)
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
        references (:obj:`list` of `Reference`): references

    Related attributes:
        functions (:obj:`list` of `FunctionExpression`): FunctionExpressions that use a Parameter
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


class StopCondition(obj_model.Model):
    """ Stop condition (Boolean-valued expression of one or more observables)

    Attributes:
        id (:obj:`str`): unique identifier
        name (:obj:`str`): name
        model (:obj:`Model`): model
        expression (:obj:`str`): expression
        analyzed_expr (:obj:`WcLangExpression`): an analyzed expression
        comments (:obj:`str`): comments
    """
    id = SlugAttribute()
    name = StringAttribute()
    model = ManyToOneAttribute(Model, related_name='stop_conditions')
    expression = LongStringAttribute()
    comments = LongStringAttribute()

    class Meta(obj_model.Model.Meta):
        """
        Attributes:
            valid_functions (:obj:`tuple` of `builtin_function_or_method`): tuple of functions that
                can be used in a `StopCondition`s `expression`
            valid_used_models (:obj:`tuple` of `str`): names of `obj_model.Model`s in this module that a
                `StopCondition` is allowed to reference in its `expression`
        """
        attribute_order = ('id', 'name', 'expression', 'comments')
        valid_functions = (ceil, floor, exp, pow, log, log10, min, max)
        valid_used_models = ('Parameter', 'Observable', 'Function')

    def validate(self):
        """ Determine whether a `StopCondition` is valid by checking whether
        `expression` is a valid Python expression.

        Returns:
            :obj:`InvalidObject` or None: `None` if the object is valid,
                otherwise return a list of errors in an `InvalidObject` instance
        """
        expr = self.expression

        # to evaluate the expression, set variables for the observable identifiers to their values
        # test validation with values of 1.0
        errors = []

        for match in re.findall(r'(\A|\b)([a-z][a-z0-9_]*)(\b|\Z)', expr, re.IGNORECASE):
            if not self.model.observables.get_one(id=match[1]):
                errors.append('Observable "{}" not defined'.format(match[1]))
            # todo: recreates the suffix match bug: fix by parsing expression
            expr = expr.replace(match[1], '1.')

        local_ns = {func.__name__: func for func in self.Meta.valid_functions}

        try:
            if not isinstance(eval(expr, {}, local_ns), bool):
                errors.append("expression must be Boolean-valued: {}".format(self.expression))
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

        database_references (:obj:`list` of `DatabaseReference`): database references
        taxa (:obj:`list` of `Taxon`): taxa
        submodels (:obj:`list` of `Submodel`): submodels
        compartments (:obj:`list` of `Compartment`): compartments
        species_types (:obj:`list` of `SpeciesType`): species types
        concentrations (:obj:`list` of `Concentration`): concentrations
        reactions (:obj:`list` of `Reaction`): reactions
        rate_laws (:obj:`list` of `RateLaw`): rate laws
        parameters (:obj:`list` of `Parameter`): parameters
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
