#!/usr/bin/env python3

import sys
import re
import pprint
import json
from functools import singledispatch

SWAGGER_INDENT = 4

pp = pprint.PrettyPrinter(indent=4)

class PropertyType():
    def __init__(self, required):
        self.required = required


class SimplePropertyType(PropertyType):
    def __init__(self, typeString: str, required: bool = False):
        self.type = typeString.lower()
        super().__init__(required)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return pp.pformat(self.to_swagger_dict())

    def to_swagger_dict(self):
        return {
            'type': self.type
        }
    
class NumberPropertyType(PropertyType):
    def __init__(self, typeString: str, required: bool = False):
        _class_type_map = {
            'int': {
                'type': 'integer',
                'format': 'int32'
            },
            'long': {
                'type': 'integer',
                'format': 'int64'
            },
            'float': {
                'type': 'number',
                'format': 'float'
            },
            'double': {
                'type': 'number',
                'format': 'double'
            }
        }
        lower_case_type = typeString.lower()
        type_and_format = _class_type_map.get(lower_case_type, {'type': 'number'})
        self.type = type_and_format.get('type', None)
        self.format = type_and_format.get('format') # This returns None if a typeString is not recognized in above map

        super().__init__(required)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return pp.pformat(self.to_swagger_dict())
    
    def to_swagger_dict(self):
        res = {}
        res['type'] = self.type
        if self.format is not None:
            res['format'] = self.format
        return res


class ArrayPropertyType(PropertyType):
    def __init__(self, items: PropertyType, required: bool = False):
        self.type = "array"
        self.items = items
        super().__init__(required)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return pp.pformat(self.to_swagger_dict())

    def to_swagger_dict(self):
        return {
            'type': self.type,
            'items': self.items
        }


class ReferencePropertyType(PropertyType):
    def __init__(self, className: str, required: bool = False):
        self.className = className
        super().__init__(required)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return pp.pformat(self.to_swagger_dict())
    
    def to_swagger_dict(self):
        return {
            '$ref': '#/definitions/{}'.format(self.className)
        }


class SwaggerProperty:
    def __init__(self, pname: str, ptype: PropertyType, required: bool = False):
        self.property_name = pname
        self.propertyType = ptype
        self.required = required

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return pp.pformat(self.to_swagger_dict())
    
    def to_swagger_dict(self):
        rep = self.propertyType
        return rep


class SwaggerDoc:
    def __init__(self, className):
        self.type = "object"
        self.name = className
        self.properties = []
        self.requiredProperties = []

    def addProperty(self, property):
        self.properties += [property]
        if property.required:
            self.requiredProperties += [property.property_name]

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return pp.pformat(self.to_swagger_dict())
    
    def to_swagger_dict(self):
        rep = {}
        rep[self.name] = {
            'type': "object",
            'required': self.requiredProperties,
            'properties': {}
        }
        for prop in self.properties:
            rep[self.name]['properties'][prop.property_name] = prop.propertyType
        return rep

@singledispatch
def to_serializable(val):
    """Default json serialization"""
    return val

@to_serializable.register(PropertyType)
@to_serializable.register(SimplePropertyType)
@to_serializable.register(NumberPropertyType)
@to_serializable.register(ArrayPropertyType)
@to_serializable.register(ReferencePropertyType)
@to_serializable.register(SwaggerProperty)
@to_serializable.register(SwaggerDoc)
def ts_swagger(obj):
    """Override json serialization for Swagger-related classses"""
    return obj.to_swagger_dict()

def is_simple_type(s: str):
    """ Simple extensible function to determine if a Scala class is a SimplePropertyType """
    switcher = {
        'String': True,
        'Char': True,
        'Boolean': True
    }
    return switcher.get(s, False)

def is_number_type(s: str):
    """ Simple extensible function to determine if a Scala class is a NumberPropertyType """
    switcher = {
        'Int': True,
        'Long': True,
        'Float': True,
        'Double': True
    }
    return switcher.get(s, False)

def isArrayType(s: str):
    """ Simple extensible function to determine if a Scala class is a ArrayPropertyType """
    switcher = {
        'Array': True,
        'List': True,
        'ArrayBuffer': True
    }
    return switcher.get(s, False)

def extract_super_type(s: str):
    """ Takes a type string and returns the container type (i.e. Option from Option[String] or List from List[String])
    """
    match = re.search(r'^(.*)\[.*$', s) # Search for pattern <Type>[<SubType>] and extract <Type> into group #1
    if match is None:
        return None
    else:
        return match.group(1)

def extract_sub_type(s: str):
    """ Takes a type string and returns the sub type (i.e. String from Option[String] or List[String])
    """
    match = re.search(r'^.*\[(.*)\]$', s) # Extract type from the outermost parentheses into group #1
    if match is None:
        print('[ERROR]: No subtype found for string "{}"'.format(s))
        raise Exception("Invalid input: No outer type found")
    else:
        return match.group(1)


def to_property_type(typeString: str):
    """ Takes a type string and parses it to return the appropriate PropertyType
    """
    print('Processing typeString "{}"'.format(typeString))
    superType = extract_super_type(typeString)
    subType = typeString

    required = True
    if superType is not None:
        if superType == 'Option':
            required = False
        subType = extract_sub_type(typeString)

    if isArrayType(superType):
        listType = extract_sub_type(typeString)
        return ArrayPropertyType(to_property_type(listType), required = required)
    elif is_simple_type(subType): # Base case
        return SimplePropertyType(subType, required = required)
    elif is_number_type(subType):
        return NumberPropertyType(subType, required = required)
    else:
        return ReferencePropertyType(subType, required = required) # Default is Reference Type if no other type is found


def get_class_strings_from_file():
    """ Reads file input.txt and returns array of strings with spaces removed
        for each case class in the file. The file must contain only the case class
        definitions or the output will be unpredictable
    """
    with open("input.txt", "r") as file:
        if file.mode == 'r':
            contents = file.read()
        else:
            print("Error opening file to read")
            sys.exit()
    
    class_strings = contents.split("case class")
    split_contents = ["".join(item.split()) for item in class_strings]
    split_contents.remove('') # Remove extraneous empty string caused by above action
    return split_contents

def create_swagger_doc(case_class_string):
    """ Constructs swagger doc object from the provided case class string by extracting the 
        class name and parameters and converting the parameters to the appropriate sub-class of
        ParameterType to ensure correct serialization
    """
    split_contents = re.split(r'[(,)]', case_class_string)
    split_contents.remove('')
    className = split_contents[0]
    del split_contents[0]
    result = SwaggerDoc(className)

    for parameter in split_contents:
        parameter_without_defaults = re.sub(r'=.*', '', parameter)
        split_parameter = parameter_without_defaults.split(':')
        name = split_parameter[0]
        typeName = split_parameter[1]
        propType = to_property_type(typeName)
        print('Adding property {} with type {}'.format(name, propType))
        result.addProperty(SwaggerProperty(name, propType, propType.required))

    return result

def main():
    case_classes_strings = get_class_strings_from_file()
    for case_class_string in case_classes_strings:
        case_class_doc = create_swagger_doc(case_class_string)
        with open('output/{}_output_swagger.json'.format(case_class_doc.name), 'w') as out_file:
            out_file.write(json.dumps(case_class_doc, default=to_serializable, sort_keys=True, indent=SWAGGER_INDENT))

if __name__ == '__main__':
    main()
