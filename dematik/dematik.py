from jinja2 import Environment, PackageLoader, PrefixLoader, Markup, select_autoescape, StrictUndefined
from collections import Counter
from datetime import datetime
from field_data import FieldData
from blocks import Blocks
from markdown import markdown
from os.path import isfile, dirname
import traceback
import jinja2.exceptions
import json
import os

# This class allows to build process and forms form its definition
class Dematik:

    def __init__(self, backend, debug=False):
        # Debug mode means printing stack trace on errors
        self.debug = debug
        
        self.env = Environment(
            loader=PrefixLoader({
                'blocks-'+backend:   PackageLoader('dematik', 'blocks-'+backend),
                'macros-'+backend:   PackageLoader('dematik', 'macros-'+backend)
            }),
            autoescape=select_autoescape(['j2']),
            undefined=StrictUndefined
        )

        self.env.globals = {
            "now": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "get_text" : self.get_text,
            "get_md_text" : self.get_md_text,
            "get_items" : self.get_items,
            "get_varname" : self.get_varname,
            "get_id" : self.get_id,
            "is_in_listing" : self.is_in_listing,
            "is_in_filters" : self.is_in_filters,
        }

        self.fields_data = FieldData()
        self.blocks = Blocks(self.env, ['blocks-'+backend])
        self.reset()

    # Returns text or raise a ValueError
    def get_text(self, field_data):
        return getattr(self.fields_data, field_data)["label"]

    # Returns html from a markdown compatible text or raise a ValueError
    def get_md_text(self, field_data):
        return markdown(getattr(self.fields_data, field_data)["label"])
    
    # Returns a list of items or raise a ValueError
    def get_items(self, field_data):
        return getattr(self.fields_data, field_data)["items"]

     # Returns a varname or raise a ValueError
    def get_varname(self, field_data):
        return field_data.replace(':', '_')

     # Generate ID for form fields using a cache process
    def get_id(self, field_data=None):
        id = self.id

        # ID in cache for this field ?
        if field_data and field_data in self.ids_cache:
            # yes
            id = self.ids_cache[field_data]
        else:
            # no : generate a new ID and add it to the cache
            self.id += 1
            id = self.id
            if field_data:
                self.ids_cache[field_data] = id

        # Check that field_data is unique
        if field_data and field_data in self.used_field_data:
            raise Exception("Le nom %s a deja ete utilise. Merci d'utiliser d'ajouter un contexte ou creer un nouveau code" % field_data)
        elif field_data:
            self.used_field_data += [field_data]
       
        return id

    # Returns if a field should appear in listing
    def is_in_listing(self, field_data):
        return str(field_data in self.in_listing)

    # Returns if a field should appear in filters
    def is_in_filters(self, field_data):
        return str(field_data in self.in_filters)

    # Load field data from a file
    def load_field_data(self, path):
        self.fields_data.load(path)

    # Reset context
    # Should be done before each definition file process 
    def reset(self):
        # form name
        self.form = None

        # form metadata
        self.env.globals["formulaire"] = {}

        # form fields
        self.form_fields = ""

        # Used field code table (to prevent duplicate ID)
        self.used_field_data = []

        # form field id counter
        self.id = 1

        # ID cache dict : field data (string) : id (string)
        self.ids_cache = {}

        # list of fields that should appear in the admin listing
        self.in_listing = []

        # list of fields that should appear in the admin filters
        self.in_filters = []

    # Parse "formulaire" metadata
    def parseFormMetadata(self, tokens):
        metas = [ "description", "identifiant", "url" ]
        for meta in metas:
            if tokens[0] == meta and len(tokens) == 2:
                self.env.globals["formulaire"][meta] = self.get_text(tokens[1])
                return True
        if tokens[0] == "listing" and len(tokens) == 2:
            self.in_listing += tokens[1]
            return True
        if tokens[0] == "filter" and len(tokens) == 2:
            self.in_filters += tokens[1]
            return True
        return False

    # Parse form fields
    def parseFieldBlock(self, tokens):
        if tokens[0] in self.blocks:
            if "page" in tokens[0]:
                # Create an empty condition list if no condition is defined
                tokens += [[]]
                self.form_fields += self.blocks(tokens)
            elif "formulaire" in tokens[0]:
                # Form is rendered at the end of the process, safe this line
                self.form = tokens
            else:
                # Render the block
                self.form_fields += self.blocks(tokens)
            return True

        # Line could not be parsed, first token is unknown
        return False

    # Convert a process definition to a form file
    def render_form(self, path):
        context = ""
        try:
            with open(path) as f:
                for i, line in enumerate(f):
                    tokens = line.strip().split(' ')

                    # Ignore empty line or comment lines
                    if len(tokens) > 0 and tokens[0] and tokens[0][0] != '#':
                        context = path + ' line ' + str(i+1)
                        if not (self.parseFormMetadata(tokens)
                            or self.parseFieldBlock(tokens)):
                            print("{} - WARN - Line ignored - Block {} is not implemend, please implement it".format(
                                    context,
                                    tokens[0]))
        
        except Exception as e:
            if self.debug:
                traceback.print_exc()
            print(context + " - ERROR - " + str(e))
            return None
       
        # Generate form
        if self.form:
            return self.blocks(self.form + [Markup(self.form_fields)])
            
        print("ERROR - Il manque le nom du formulaire")
        return None
                
    # Process definition
    def generate(self, path):

        self.reset()

        id_before_parse = 0
        base_path = 'generated/' + path.replace('/','_') \
                    .replace('._', '') \
                    .replace('process_definitions_', '') \
                    .replace('.def', '')

        # Load ID cache
        if isfile(base_path + '.cache'):
            with open(base_path + '.cache') as f:
                self.ids_cache = json.load(f)
                if self.ids_cache.values():
                    self.id = max(self.ids_cache.values())
                    id_before_parse = self.id
        else:
            print("%s - INFO - Generation des ID sans cache" % path)

        # Render form
        form = self.render_form(path)
        if not form:
            print("%s - FATAL - Abandon de generation" % path)
            return
        
        # Create export directory if needed
        if not os.path.exists(dirname(base_path)):
            os.makedirs(dirname(base_path))

        # Save generated form
        with open(base_path + '.wcs', 'w+') as f:
            f.write(form)

        # Save ID cache for this form
        with open(base_path + '.cache', 'w+') as f:
            f.write(json.dumps(self.ids_cache))

        # Some stats
        print('{} - Nombre de champs : {} ({})'.format(path, len(self.used_field_data), self.id - id_before_parse - 1))

    # Print field data that has not been used yet 
    def show_unused_labels(self):
        print('Unused YAML labels')
        for label in self.fields_data.unused():
            print(" - " + label)