""" Utilities for writing/reading a `wc_lang` model to/from SBML

Includes

* Exception definitions for `wc_lang.sbml`
* Higher level functions for creating SBML objects
* Utilities for wrapping libSBML calls and initializing libSBML models

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2019-01-24
:Copyright: 2017-2019, Karr Lab
:License: MIT
"""

from libsbml import (LIBSBML_OPERATION_SUCCESS, OperationReturnValue_toString,
                     SBMLNamespaces, SBMLDocument)
from wc_utils.util.units import unit_registry, are_units_equivalent
import enum
import libsbml
import math
import pint
import types
import warnings
import wc_lang.core
import xml.sax.saxutils
# import wc_lang.util


class LibSbmlUnitKind(int, enum.Enum):
    """ SBML unit kinds """
    ampere = 0
    avogadro = 1
    becquerel = 2
    candela = 3
    celsius = 4
    coulomb = 5
    dimensionless = 6
    farad = 7
    gram = 8
    gray = 9
    henry = 10
    hertz = 11
    invalid = 36
    item = 12
    joule = 13
    katal = 14
    kelvin = 15
    kilogram = 16
    liter = 17
    litre = 18
    lumen = 19
    lux = 20
    meter = 21
    metre = 22
    mole = 23
    newton = 24
    ohm = 25
    pascal = 26
    radian = 27
    second = 28
    siemens = 29
    sievert = 30
    steradian = 31
    tesla = 32
    volt = 33
    watt = 34
    weber = 35


class LibSbmlError(Exception):
    ''' Exception raised when libSBML returns an error '''


class LibSbmlInterface(object):
    '''Methods for compactly using libSBML to create SBML objects.

    The libSBML method calls provide narrow interfaces, typically exchanging one
    value per call, which creates verbose code. The methods below aggregate multiple
    libSBML method calls to enable more compact usage.
    '''

    @classmethod
    def create_doc(cls, level=3, version=2, packages=None):
        """ Create an SBMLDocument that, optionally, uses package(s).

        Args:
            level (:obj:`int`, optional): SBML level number
            version (:obj:`int`, optional): SBML version number
            packages (:obj:`dict` that maps :obj:`str` to :obj:`int`, optional): dictionary of required packages
                that maps package identifiers to package numbers

        Returns:
            :obj:`libsbml.SBMLDocument`: SBML document
        """
        packages = packages or {}

        # create name spaces for SBML document
        namespaces = [SBMLNamespaces, level, version]
        for package_id, package_version in packages.items():
            namespaces.append(package_id)
            namespaces.append(package_version)
        sbml_ns = cls.call_libsbml(*namespaces)

        # create SBML document
        doc = cls.call_libsbml(SBMLDocument, sbml_ns)

        # set package requirements
        for package in packages:
            cls.call_libsbml(doc.setPackageRequired, package, False)

        # return SBML document
        return doc

    @classmethod
    def is_doc_compatible(cls, doc, level=3, version=2):
        """ Check the compatibility of an SBML document with a specific level and version

        Args:
            doc (:obj:`libsbml.SBMLDocument`): SBML document
            level (:obj:`int`, optional): SBML level number
            version (:obj:`int`, optional): SBML version number
        """
        # SBML compatibility method for the version being used
        method = getattr(doc, 'checkL{}v{}Compatibility'.format(level, version))
        return 0 == cls.call_libsbml(method, returns_int=True)

    @classmethod
    def create_model(cls, doc):
        """ Create a SBML model

        Args:
            doc (:obj:`libsbml.SBMLDocument`): SBML document

        Returns:
            :obj:`libsbml.Model`: SBML model
        """
        return cls.call_libsbml(doc.createModel)

    @classmethod
    def init_model(cls, model, doc, packages=None):
        """ Create and initialize an SMBL model.

        Args:
            model (:obj:`wc_lang.core.Model`): model
            doc (:obj:`libsbml.SBMLDocument`): a `libsbml` SBMLDocument
            packages (:obj:`dict` that maps :obj:`str` to :obj:`int`, optional): dictionary of required packages
                that maps package identifiers to package numbers

        Returns:
            :obj:`libsbml.Model`: the SBML model
        """

        # create model
        sbml_model = cls.create_model(doc)

        # enable plugins for packages
        packages = packages or {}
        for package_id in packages.keys():
            plugin = cls.call_libsbml(sbml_model.getPlugin, package_id)
            cls.call_libsbml(plugin.setStrict, True)

        # Set units
        cls.create_units(model, sbml_model)

        # return SBML model
        return sbml_model

    @classmethod
    def create_units(cls, model, sbml_model):
        """ Set time, extent, and substance units

        Args:
            model (:obj:`wc_lang.core.Model`): model
            sbml_model (:obj:`libsbml.Model`): SBML model that encodes the model

        Returns:
            :obj:`dict`: dictionary that maps units to ids of SBML unit definitions
        """
        import wc_lang.util

        # Define units
        units = wc_lang.util.get_model_units(model)
        units_to_sbml = {}
        for unit in units:
            sbml_unit = cls.create_unit(unit, sbml_model)
            if sbml_unit:
                units_to_sbml[unit] = sbml_unit.getId()

        # set top-level units (time, substance, extent, volume)
        units = cls.gen_base_unit_id(model.time_units)
        cls.call_libsbml(sbml_model.setTimeUnits, units)

        assert len(wc_lang.core.Species.units.choices) == 1
        units = cls.gen_base_unit_id(wc_lang.core.Species.units.choices[0])
        cls.call_libsbml(sbml_model.setExtentUnits, units)
        cls.call_libsbml(sbml_model.setSubstanceUnits, units)

        assert len(wc_lang.core.Compartment.init_volume_units.choices) == 1
        units = cls.gen_base_unit_id(wc_lang.core.Compartment.init_volume_units.choices[0])
        cls.call_libsbml(sbml_model.setVolumeUnits, units)

        # return dictionary to SBML units
        return units_to_sbml

    @classmethod
    def create_unit(cls, unit, sbml_model):
        """ Add a unit definition to a SBML model

        Args:            
            unit (:obj:`unit_registry.Unit`): unit
            sbml_model (:obj:`libsbml.Model`): SBML model that encodes the model

        Returns:
            :obj:`libsbml.UnitDefinition`: unit definition
        """
        id = cls.gen_unit_id(unit)
        if hasattr(libsbml, 'UNIT_KIND_' + id[5:].upper()):
            return None

        unit_def = cls.call_libsbml(sbml_model.createUnitDefinition)
        cls.call_libsbml(unit_def.setIdAttribute, id)

        unit_registry = unit._REGISTRY
        magnitude, root_units = unit_registry.parse_expression(str(unit)).to_root_units().to_tuple()

        scale = int(math.floor(math.log10(magnitude)))
        multiplier = magnitude / pow(10, scale)

        for i_root_unit, (kind, exponent) in enumerate(root_units):
            if i_root_unit == 0:
                unit_scale = scale
                unit_multiplier = multiplier
            else:
                unit_scale = 0
                unit_multiplier = 1.
            cls.create_base_unit(unit_def, kind, exponent=exponent, scale=unit_scale, multiplier=unit_multiplier)

        return unit_def

    @classmethod
    def gen_unit_id(cls, unit):
        """ Generate an SBML unit id for a unit

        Args:
            unit (:obj:`unit_registry.Unit`): unit

        Returns:
            :obj:`str`: SBML id for unit
        """
        id = 'unit_' + str(unit) \
            .replace(' / ', '_per_') \
            .replace(' * ', '_times_') \
            .replace(' ** ', '_pow_')
        return id

    @classmethod
    def gen_base_unit_id(cls, unit):
        """ Generate an SBML base unit id for a unit

        Args:
            unit (:obj:`unit_registry.Unit`): unit

        Returns:
            :obj:`str`: SBML id for base unit
        """
        unit_registry = unit._REGISTRY
        if are_units_equivalent(unit, unit_registry.parse_units('molecule')):
            return 'item'
        return cls.normalize_unit_kind(str(unit))

    @classmethod
    def create_base_unit(cls, unit_def, kind, exponent=1, scale=0, multiplier=1.0):
        """ Add a unit to a SBML unit definition

        Each SBML unit has four attributes:

        * `kind`
        * `exponent`
        * `scale`
        * `multiplier`

        Args:
            unit_def (:obj:`libsbml.UnitDefinition`): SBML unit definition
            kind (:obj:`str`): unit kind
            exponent (:obj:`int`, optional): exponent of the unit
            scale (:obj:`int`, optional): scale of the unit
            multiplier (:obj:`float`, optional): multiplier of the unit

        Returns:
            :obj:`libsbml.Unit`: SBML unit
        """
        kind = cls.normalize_unit_kind(kind)
        kind_val = getattr(libsbml, 'UNIT_KIND_' + kind.upper())

        unit = cls.call_libsbml(unit_def.createUnit)
        cls.call_libsbml(unit.setKind, kind_val)
        cls.call_libsbml(unit.setExponent, exponent)
        cls.call_libsbml(unit.setScale, scale)
        cls.call_libsbml(unit.setMultiplier, multiplier)
        return unit

    @classmethod
    def normalize_unit_kind(cls, kind):
        """ Normalize unit kind for SBML

        Args
            kind (:obj:`str`): unit kind

        Returns:
            :obj:`str`: normalized unit kind
        """
        if kind == 'liter':
            kind = 'litre'
        elif kind == 'meter':
            kind = 'metre'
        return kind

    @classmethod
    def parse_units(cls, sbml_model):
        """ Parse SBML units to Python

        Args:
            sbml_model (:obj:`libsbml.Model`): SBML model

        Returns:
            :obj:`dict`: dictionary that maps ids of unit definitions to instance of `unit_registry.Quantity`
        """
        units = {}

        for type in ['Time', 'Substance', 'Volume']:
            if not getattr(sbml_model, 'isSet' + type + 'Units')():
                raise LibSbmlError('{} units must be set'.format(type))

            sbml_unit_id = getattr(sbml_model, 'get' + type + 'Units')()
            if sbml_unit_id == 'item':
                units[sbml_unit_id] = unit_registry.parse_expression('molecule')
            else:
                units[sbml_unit_id] = unit_registry.parse_expression(sbml_unit_id)

        assert sbml_model.getExtentUnits() == sbml_model.getSubstanceUnits(), \
            LibSbmlError('Substance and extent units must be the same')
        assert not sbml_model.isSetLengthUnits(), \
            LibSbmlError('Length units must be unset')
        assert not sbml_model.isSetAreaUnits(), \
            LibSbmlError('Area units must be unset')

        for i_unit_def in range(sbml_model.getNumUnitDefinitions()):
            sbml_unit_def = sbml_model.getUnitDefinition(i_unit_def)
            units[sbml_unit_def.getId()] = cls.parse_unit(sbml_unit_def)
        return units

    @classmethod
    def parse_unit(cls, sbml_unit_def):
        """ Parse a unit from an SBML unit definition.

        Args:
            sbml_unit_def (:obj:`libSBML.UnitDefinition`): SBML unit definition
        
        Returns:
            :obj:`unit_registry.Quantity`: units
        """
        unit = unit_registry.parse_units('1')
        for i_unit in range(sbml_unit_def.getNumUnits()):
            sbml_unit = sbml_unit_def.getUnit(i_unit)
            unit *= unit_registry.parse_expression('{} * ({} * 10 ** {}) ** {}'.format(
                sbml_unit.multiplier, LibSbmlUnitKind(sbml_unit.kind).name, sbml_unit.scale, sbml_unit.exponent))
        return unit

    @classmethod
    def create_parameter(cls, sbml_model, id, value, units, name=None, constant=True):
        """ Add a parameter to an SBML model.

        Args:
            sbml_model (:obj:`libsbml.Model`): SBML model
            id (:obj:`str`): id
            value (:obj:`obj`): value
            units (:obj:`unit_registry.Unit`): units
            name (:obj:`str`, optional): name
            constant (:obj:`str`, optional): whether the parameter is a constant

        Returns:
            :obj:`libsbml.Parameter`: SBML parameter

        Raises:
            :obj:`LibSbmlError`: if a libSBML calls fails
            :obj:`ValueError`: if a `Parameter` with id `id` is already in use
        """
        sbml_parameter = cls.call_libsbml(sbml_model.createParameter)
        cls.call_libsbml(sbml_parameter.setIdAttribute, id)
        if name is not None:
            cls.call_libsbml(sbml_parameter.setName, name)
        if value is not None:
            cls.call_libsbml(sbml_parameter.setValue, value)
        if units is not None:
            cls.call_libsbml(sbml_parameter.setUnits, cls.gen_unit_id(units))
        cls.call_libsbml(sbml_parameter.setConstant, constant)
        return sbml_parameter

    @classmethod
    def parse_parameter(cls, sbml_parameter):
        """ Parse a parameter from an SBML parameter.

        Args:
            sbml_parameter (:obj:`libSBML.Parameter`): SBML parameter

        Returns:
            :obj:`str`: id
            :obj:`str`: name
            :obj:`float`: value
            :obj:`unit_registry.Unit`: units
        """
        id = sbml_parameter.getId()
        name = sbml_parameter.getName() or None
        value = sbml_parameter.getValue()
        sbml_model = sbml_parameter.getModel()
        sbml_unit_def_id = sbml_parameter.getUnits()
        sbml_unit_def = sbml_model.getUnitDefinition(sbml_unit_def_id)
        if sbml_unit_def is None:
            raise LibSbmlError('Unit {} must be defined'.format(sbml_unit_def_id))
        units = cls.parse_unit(sbml_unit_def)
        if not sbml_parameter.getConstant():
            raise LibSbmlError('Parameters must be constant')
        return (id, name, value, units)

    @classmethod
    def call_libsbml(cls, method, *args, returns_int=False, debug=False):
        """ Call a libSBML method and handle any errors.

        Unfortunately, libSBML methods that do not return data usually report errors via return codes,
        instead of exceptions, and the generic return codes contain virtually no information.
        This function wraps these methods and raises useful exceptions when errors occur.

        Set `returns_int` `True` to avoid raising false exceptions or warnings from methods that return
        integer values.

        Args:
            method (:obj:`type`, :obj:`types.FunctionType`, or :obj:`types.MethodType`): `libsbml` method to execute
            args (:obj:`list`): a `list` of arguments to the `libsbml` method
            returns_int (:obj:`bool`, optional): whether the method returns an integer; if `returns_int`
                is `True`, then an exception will not be raised if the method call returns an integer
            debug (:obj:`bool`, optional): whether to print debug output

        Returns:
            :obj:`obj` or `int`: if the call does not return an error, return the `libsbml`
                method's return value, either an object that has been created or retrieved, or an integer
                value, or the `libsbml` success return code, `LIBSBML_OPERATION_SUCCESS`

        Raises:
            :obj:`LibSbmlError`: if the `libsbml` call raises an exception, or returns None, or
            returns a known integer error code != `LIBSBML_OPERATION_SUCCESS`
        """
        new_args = []
        for arg in args:
            new_args.append(arg)
        if new_args:
            new_args_str = ', '.join([str(a) for a in new_args])
            call_str = "method: {}; args: {}".format(method, new_args_str)
        else:
            call_str = "method: {}".format(method)
        if debug:
            print('libSBML call:', call_str)
        try:
            rc = method(*tuple(new_args))
        except BaseException as error:
            raise LibSbmlError("Error '{}' in libSBML method call '{}'.".format(error, call_str))
        if rc == None:
            raise LibSbmlError("libSBML returned None when executing '{}'.".format(call_str))
        elif type(rc) is int:
            # if `method` returns an int value, do not interpret rc as an error code
            if returns_int:
                if debug:
                    print('libSBML returns an int:', rc)
                return rc

            if rc == LIBSBML_OPERATION_SUCCESS:
                if debug:
                    print('libSBML returns: LIBSBML_OPERATION_SUCCESS')
                return rc
            else:
                error_code = OperationReturnValue_toString(rc)
                if error_code is None:
                    if debug:
                        print("libSBML returns:", rc)
                    warnings.warn("call_libsbml: unknown error code {} returned by '{}'."
                                  "\nPerhaps an integer value is being returned; if so, to avoid this warning "
                                  "pass 'returns_int=True' to call_libsbml().".format(error_code, call_str), UserWarning)
                    return rc
                else:
                    raise LibSbmlError("LibSBML returned error code '{}' when executing '{}'."
                                       "\nWARNING: if this libSBML call returns an int value, then this error may be "
                                       "incorrect; to avoid this error pass 'returns_int=True' to call_libsbml().".format(
                                           error_code, call_str))
        else:
            # return data provided by libSBML method
            if debug:
                print('libSBML returns:', rc)
            return rc

    @classmethod
    def str_to_xml_node(cls, str):
        """ Convert a Python string to an XML string that can be stored as a Note in an SBML document.

        Args:
            str (:obj:`str`): a string

        Returns:
            :obj:`libsbml.XMLNode`: an XML string that can be stored as a `Note` in an SBML document
        """
        return cls.call_libsbml(libsbml.XMLNode.convertStringToXMLNode,
                                "<p xmlns=\"http://www.w3.org/1999/xhtml\">{}</p>".format(xml.sax.saxutils.escape(str)))
