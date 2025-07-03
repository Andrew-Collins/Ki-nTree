from sys import exception
from typing import is_typeddict
from kintree.config.settings import load_cache_settings
from kintree.gui.views.main import *
from kintree.gui.views.settings import *
from kintree.database import inventree_api

import re
import argparse
import sys
import csv
import shutil

DEFAULT_FAB = 'JLCPCB'

SMT_SIZES = ['0201', '0402', '0603', '0805','1206','1210', '1812', '2010', '2512']

SEARCH_FIELDS_LIST = [
    'name',
    'description',
    'revision',
    'keywords',
    'supplier_name',
    'supplier_part_number',
    'supplier_link',
    'manufacturer_name',
    'manufacturer_part_number',
    'datasheet',
    'image',
]

USUAL_SUPP = ["Mouser", "Digi-Key", "Element14"]

RENAME_SUPP = {"Digi-Key": "DigiKey"}

REF_TO_CATEGORY = {'R': ['Electronic Components', 'Resistors'], 'RN': ['Electronic Components', 'Resistors'], 'C':  ['Electronic Components', 'Capacitors'], 'CN':  ['Electronic Components', 'Capacitors'], 'D': ['Electronic Components', 'Diodes'], 'F': ['Electronic Components', 'Fuses'], 'Y': ['Electronic Components', 'Crystals'], 'J': ['Electronic Components', 'Connectors'], 'Q': ['Electronic Components', 'Transistors'], 'FB': ['Electronic Components', 'Ferrites'], 'U': ['Electronic Components', 'ICs'], 'L': ['Electronic Components', 'Inductors'], 'H': ['Standoffs & Spacers'], 'FL': ['Electronic Components', 'Chokes & Filters'], 'BRD': ['Bare PCBs'], 'CBL': ['Cable'], 'CBA': ['Cable Assemblies'], 'P': ['Cable Parts'], 'W': ['Cable Parts'] , 'B': ['Batteries'], 'MOD': ['Electronic Components', 'Modules'], 'SNS': ['Electronic Components', 'Sensors'], 'DSP': ['Displays'], 'SW': ['Switches & Buttons'], 'BT': ['Battery Holders'], 'TH': ['Electronic Components', 'Thermistors'] }

def cap_generic(s: str, params = None) -> str:
    cap_units = ['p','n','u','m','']
    (val, unit, ) = re.search("((?:[0-9]*[.])?[0-9]+)[ ]*([µuUmpP])[ ]*[Ff]*",s).groups()
    # val = ''
    # # Allow for a missing leading zero
    # if res:
    #     (val, ) = res.groups()
    # else:
    #     (val, ) =  re.search("([0-9]*[.][0-9]+)[ ]*[µuUmpP][ ]*[Ff]*",s).groups()
    # Make sure 'u' or 'p' aren't capitalised
    unit = unit.lower().replace('µ', 'u')

    # Increase the unit if >1000
    while float(val) > 1000 and len(unit):
        val = str(int(float(val)/1000))
        unit = cap_units[cap_units.index(unit) + 1]

    foot = ''
    for size in SMT_SIZES:
        if size in s:
            foot = size
            break
    if 'metric' in s.lower():
        (foot,) = re.search(r'(\d{4}).+[Mm][Ee][Tt][Rr][Ii][Cc].+',s).groups()
    # # search in mm
    # if len(foot) == 0:
    #     (x,y,) = re.search("(\d).*x[ ]*(\d)mm",s).groups()
    #     foot = "{}x{}".format(x,y)
    if len(foot) == 0 and type(params) == dict:
        package_key = ''
        for key in params.keys():
            print('key: ', key.lower())
            if 'package' in key.lower():
                package_key = key
                break
        if 'can' in s.lower() or (len(package_key) and 'can' in str(params[package_key]).lower()):
            height_key = ''
            for key in params.keys():
                if 'height' in key.lower():
                    height_key = key
                    break
            size_key = ''
            for key in params.keys():
                if 'size' in key.lower() or 'diameter' in key.lower():
                    size_key = key
                    break
            if len(height_key) == 0 or len(size_key) == 0:
                raise ValueError("Keys for can cap not found")
            # 'mm' is appended in case of a unitless field
            (height,) = re.search("((?:[0-9]*[.])?[0-9]+)[ ]*mm",params[height_key]+"mm").groups()
            (diameter,) = re.search("((?:[0-9]*[.])?[0-9]+)[ ]*mm",params[size_key]+"mm").groups()
            # Convert to float to remove trailing zeros
            foot = "{}x{}".format(float(diameter), float(height))

    tol = ''
    tol_res = re.search("([XYNC][57P0][RV0G])",s)
    if tol_res is None:
        tol_key = ''
        for key in params.keys():
            if 'tolerance' in key.lower():
                tol_key = key
                break
        if len(tol_key):
            (tol,) = re.search("([0-9]+[.]*[0-9]*%)",params[tol_key]).groups()
        else:
            (tol,) = re.search("([0-9]+[.]*[0-9]*%)",s).groups()
    else:
        (tol, )  = tol_res.groups()
    (voltage,) = re.search("((?:[0-9]*[.])?[0-9]+)[ ]*v",s.lower()).groups()

    if not (len(foot) and len(val) and len(unit) and len(tol) and len(voltage)):
        raise ValueError("Unable to find all parameters: ", foot, val, unit, tol, voltage)

    return "C_{}_{}{}_{}V_{}".format(foot, val, unit, voltage, tol)

def res_generic(s: str, params = None) -> str:
    (val, unit,) = re.search("((?:[0-9]*[.])?[0-9]+)[ ](?!mw|mW|w|W)*([kKmMrR])*[ ]*(?:[Oo][Hh][Mm])*",s).groups()
    # print("val: ", val, " unit: ", unit)
    # Make sure 'k' isn't capitalised
    if unit is None:
        unit = 'R'
    elif unit.lower() == 'k':
        unit = 'k'
    elif unit.lower() == 'r':
        unit = 'R'

    if '.' in val:
        val = val.replace('.', unit)
        unit = ''


    foot = ''
    for size in SMT_SIZES:
        if size in s:
            foot = size
            break
    if 'metric' in s.lower():
        (foot,) = re.search(r'(\d{4}).+[Mm][Ee][Tt][Rr][Ii][Cc].+',s).groups()

    (tol,) = re.search("((?:[0-9]*[.])?[0-9]+%)",s).groups()

    return "R_{}_{}{}_{}".format(foot, val, unit, tol)

ref_to_generic = { 'R': res_generic, 'C': cap_generic }

def delete_failed_parts():
    cnt = 0
    while 1:
        part = inventree_api.delete_part_from_ipn(part_ipn='000000-00')
        # Delete at most 3 at a time for safety
        if cnt >= 2 or part is None:
            break
        cnt += 1


def find_part(mpn, rev):
    part = None
    # Search for the IPN
    for _retry in range(0,3):
        try:
            part = inventree_api.get_part_from_ipn(mpn, rev)
        except:
            continue
        break;
    return part


def create_part(search_form, category = [], ipn = '', template = False, variant = None, assembly = False, trackable = False):
    part_info = copy.deepcopy(search_form)
    # Update IPN (later overwritten)
    if len(ipn) == 0:
        ipn = part_info.get('manufacturer_part_number', '')
    search_term = ipn
    part_info['IPN'] = ipn
    print("IPN/Rev: ", ipn, '/', search_form['revision'])
    if variant:
        part_info['variant'] = variant
    part_info['template'] = template
    part_info['assembly'] = assembly
    part_info['trackable'] = trackable

    part = None
    # Search for the IPN
    for _retry in range(0,3):
        try:
            part = inventree_api.get_part_from_ipn(search_term, search_form['revision'])
            part_pk = None

            # Account for revision mismatch
            if part and part.revision != search_form['revision']:
                part = None

            if part:
                part_pk = part.pk
                if template or assembly:
                    print("Part is template or assembly, skipping")
                    return part_pk
                # Create alternate
                _alt_result = inventree_interface.inventree_create_alternate(
                    part_info=part_info,
                    part_ipn=search_term,
                )
            else:
                if category is None:
                    print("Category cannot be blank when creating new part")
                    return None
                part_info['category_tree'] = category

                if assembly:
                    print("Int Supp", part_info['supplier_name'], part_info['supplier_part_number'])

                try:
                    # Create new part
                    _new_part, part_pk, part_info = inventree_interface.inventree_create(
                        part_info=part_info,
                        kicad=False,
                        symbol=None,
                        footprint=None,
                        show_progress=False,
                        is_custom=False,
                        stock=None,
                    )
                except Exception as e: 
                    print("Failed new: ", e)
                    delete_failed_parts()
                    continue
            break
        except Exception as e:
            print("create_part error: ", e)
            continue
    return part_pk

def is_template(ref: str, mpn: str) -> tuple[bool, str]:
    # Only care about the first one in the list
    ref_prefix = re.search("([A-Z]+)[0123456789]", ref).groups()[0]

    return (mpn[:(len(ref_prefix)+1)] == ref_prefix + '_', ref_prefix)

# bom parts must have: 'mpn','refs','qty' fields
def create_assembly(assembly: dict, bom: list[dict]) -> bool:
    ipn = assembly['ipn']
    manf = assembly.get('manf', '')
    search_form = {}
    for field in SEARCH_FIELDS_LIST:
        search_form[field] = ''

    # Process what type of assembly
    category = assembly.get('category', '')
    print("Category:", category)

    if inventree_api.get_inventree_category_id(category) == -1:
        print("Invalid category for assembly: ", category)
        return False

    search_form['name'] = assembly.get('name', ipn)
    desc = assembly.get('desc', '')
    if len(desc) and 'Assembled PCBs' in category:
        search_form['description'] = 'PCB Assembly ' + desc
    search_form['revision'] = assembly.get('rev', '')
    search_form['manufacturer_name'] = manf
    search_form['manufacturer_part_number'] = ipn
    search_form['supplier_name'] = assembly.get('supp', '')
    search_form['supplier_part_number'] = assembly.get('spn', '')
    images = assembly.get('image', [])
    if len(images) > 1:
        search_form['image'] = images[1]

    attachments = assembly.get('attachments', [])
    if len(attachments) > 1:
        attachments = attachments[1]

    overwrite = not bool(assembly.get('append', False))

    inventree_interface.connect_to_server()

    pk  = create_part(search_form, category = category, assembly=True, trackable=('pcb' in category[0].lower()))

    if pk and len(attachments):
        for attachment in attachments:
            inventree_api.upload_part_attachment(attachment, pk)

    if overwrite:
        inventree_api.delete_bom(pk)

    result = True

    for part in bom:
        (template_flag, _ref_prefix) = is_template(part['refs'], part['mpn'])
        if 'micromelon' in part['manf'].lower():
            # Must have a valid revision
            if not len(part.get('rev', '')):
                part['rev'] = assembly['rev']

        # Search for the IPN
        inv_part = None
        for _retry in range(0,3):
            try:
                inv_part = inventree_api.get_part_from_ipn(part['mpn'], part['rev'])
            except:
                continue
            break
        part_pk = -1 
        if inv_part:
            part_pk = inv_part.pk
        data = {'part': pk, 'quantity': part['qty'], 'sub_part': part_pk, 'reference': part['refs'], 'allow_variants': template_flag, 'inherited': False}
        local_res = False
        for _retry in range(0,3):
            try:
                local_res = inventree_api.add_bom_item(pk, data)
            except:
                continue
            break
        if not local_res:
            print("Unable to add item: ", part)
            result = False
    return result


def run_search(supplier, pn, manf = ''):
    # # Get supplier
    # supplier = inventree_interface.get_supplier_name(supplier)
    # Supplier search
    part_supplier_info = inventree_interface.supplier_search(
        supplier,
        pn.replace(',', ''),
        manf
    )

    part_supplier_form = None

    print(part_supplier_info)

    search_form = {}
    for field in SEARCH_FIELDS_LIST:
        search_form[field] = ''

    if part_supplier_info:
        # Translate to user form format
        part_supplier_form = inventree_interface.translate_supplier_to_form(
            supplier=supplier,
            part_info=part_supplier_info,
        )
        if part_supplier_form:
            for _field_idx, field_name in enumerate(search_form.keys()):
                try:
                    search_form[field_name] = part_supplier_form.get(field_name, '')
                except IndexError:
                    pass


    return (search_form, part_supplier_info)

def find_generic(ref_prefix, search_form, raw_form, category, create = False):
    generic = ''
    try: 
        generic = ref_to_generic[ref_prefix](search_form['description'], params=raw_form['parameters'])
    except ValueError as e:
        print("Unable to parse generic: ", e)
    except:
        print("Unable to parse generic")

    if not len(generic):
        return None

    print("")
    part_id = inventree_api.fetch_part('', generic)
    if part_id:
        print("Found existing generic: ", generic)
        return (part_id.pk, generic)


    if create:
        print("Create new generic: '", generic, "'? (Y/n): ", end = '')
        confirm = input("")
        if not(len(confirm)) or confirm.upper() == 'Y':
            search_form = {}
            for field in SEARCH_FIELDS_LIST:
                search_form[field] = ''
            search_form['name'] = generic
            search_form['manufacturer_part_number'] = generic
            return (create_part(search_form, category,  template = True), generic)
    else:
        return (0, generic)
    
    return None


def search_and_create(part_list, dry, variants=False, rev_default = '',) -> tuple[list[str],list[tuple[str, str]]]:
    print("Dry: ", dry)
    inventree_interface.connect_to_server()
    not_found = []
    name_mismatch = []
    for curr_part in part_list:
        ref = curr_part['refs']
        manf = curr_part['manf']
        mpn = curr_part['mpn']
        rev = curr_part.get('rev', rev_default)


        (template_flag, ref_prefix) = is_template(ref, mpn)

        category = REF_TO_CATEGORY.get(ref_prefix)
        if category is None:
            print("Unknown reference prefix: ", ref_prefix)
            continue

        # Get part if it exists
        search_term = mpn
        part = None
        bom_flag = False
        print("Search Term:", mpn, rev)
        for _retry in range(0,3):
            try:
                part = inventree_api.get_part_from_ipn(search_term, rev)
            except:
                continue
            break

        # Account for revision mismatch
        if part and part.revision != rev:
            part = None

        if part is not None:
            bom_items = part.getBomItems()
            bom_flag = len(bom_items) > 0
            print("Bom flag: ", bom_flag, bom_items)
            print("Found existing part: ", mpn, "/", rev)

        # Bom parts do not get updated here
        if bom_flag:
            result.append(mpn)
            continue
        # Special case for PCBs
        elif 'micromelon' in manf.lower() and mpn.lower()[-1] != 'a' and re.search(r"\d{6}", mpn) is not None:
            # Must have a valid revision
            if not len(rev):
                print("No revision found for internal part")
                continue

            part = None
            for _retry in range(0,3):
                try:
                    part = inventree_api.get_part_from_ipn(search_term, rev)
                except:
                    continue
                break
            if part is not None:
                print("Found existing part/rev: ", mpn, "/", rev)
                not_found.append(mpn)
                continue
                
            # Create Bare PCB part
            elif not dry[1] and 'a' not in mpn.lower():
                search_form = {}
                for field in search_fields_list:
                    search_form[field] = ''
                search_form['name'] = mpn
                search_form['manufacturer_name'] = manf
                search_form['manufacturer_part_number'] = mpn
                search_form['revision'] = rev
                if len(curr_part.get('image', '')):
                    search_form['image'] = curr_part['image']
                if len(curr_part.get('desc', '')):
                    search_form['description'] = curr_part['desc']
                part_pk = create_part(search_form, category, trackable=True)
                if part_pk and len(curr_part.get('attachments', '')):
                    for attachment in curr_part['attachments']:
                        inventree_api.upload_part_attachment(attachment, part_pk)
            continue

        # Template part
        if not dry[0] and template_flag:
            search_form = {}
            for field in SEARCH_FIELDS_LIST:
                search_form[field] = ''
            search_form['name'] = mpn
            search_form['manufacturer_name'] = manf
            search_form['manufacturer_part_number'] = mpn
            search_form['revision'] = rev
            # Default PCB manufacturer
            search_form['supplier_name'] = DEFAULT_FAB
            search_form['supplier_part_number'] = mpn
            if len(curr_part.get('image', '')):
                search_form['image'] = curr_part['image']
            if len(curr_part.get('desc', '')):
                search_form['description'] = curr_part['desc']
            part_pk = create_part(search_form, category, trackable=True)
            if part_pk and len(curr_part.get('attachments', '')):
                for attachment in curr_part['attachments']:
                    inventree_api.upload_part_attachment(attachment, part_pk)
            continue
        # Template part
        elif not dry and template_flag:
            search_form = {}
            for field in SEARCH_FIELDS_LIST:
                search_form[field] = ''
            search_form['name'] = mpn
            search_form['manufacturer_part_number'] = mpn
            create_part(search_form, category,  template = True)
            continue

        local_res = False

        # Cannot do supplier search if no manf currently, so short circuit
        if not len(manf):
            if part:
                # TODO: set the manufacturer and the continue as if part was not in inventree
                continue
            else:
                print("Part does not have manf and is not an inventree IPN: ", mpn)
                not_found.append(mpn)
                continue
        elif part:
            local_res = True
        
        generic_id = None
        # This sets what the ipn will be, it should match the supplier mpn
        # However suppliers can have different mpns for the same part (especially for molex parts)
        # So one supplier will need to be picked, the priority of which supplier mpn to use is set by `usual_suppliers`
        # But if the provided mpn matches an existing ipn, then that is used
        # But if this provided mpn matches a part from a supplier then it must match at least one supplier mpn
        if part:
            chosen_ipn = mpn
        else:
            chosen_ipn = None
        ipn_match = False
        valid_supp_mpn = None
        for supp in USUAL_SUPP:
            (search_form, raw_form) = run_search(supp, mpn, manf)
            if len(search_form['name']) < 1:
                continue
            local_res = True
            print("Found part")
            supp_mpn = search_form.get('manufacturer_part_number', None)
            if not valid_supp_mpn:
                valid_supp_mpn = supp_mpn
            if chosen_ipn is None:
                chosen_ipn = supp_mpn 

            # Check if the ipn matches this supplier's mpn
            ipn_match = ipn_match or (supp_mpn == chosen_ipn)

            part = None
            var = None
            # Only need to search for and update the variants once
            if generic_id is None:
                res = find_generic(ref_prefix, search_form, raw_form, category, variants and not dry[0])
                if res is not None:
                    (generic_id, generic_name) = res
                    if variants:
                        var = str(generic_id)
                        print("Variant: ", var)
                    elif generic_name not in not_found:
                        not_found.append((mpn, generic_name))
            if dry[0]:
                continue
            print("Creating normal")
            part = create_part(search_form, category, ipn=chosen_ipn, variant=var)
        if chosen_ipn != mpn:
            print("Chosen spn does not match mpn")
            name_mismatch.append((mpn, chosen_ipn))
        elif not ipn_match and valid_supp_mpn:
            print("ipn does not match spn")
            name_mismatch.append((mpn, valid_supp_mpn))

        if not local_res:
            print("Unable to create part: ", mpn)
            not_found.append(mpn)

    return (not_found, name_mismatch)

import sys,tty,os,termios
def getkey():
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    try:
        while True:
            b = os.read(sys.stdin.fileno(), 3).decode()
            if len(b) == 3:
                k = ord(b[2])
            else:
                k = ord(b)

            key_mapping = {
                127: 'backspace',
                10: 'return',
                32: ' ',
                9: 'tab',
                27: 'esc',
                22: 'paste',
            }
            return key_mapping.get(k, chr(k))
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def get_input(name: str) -> str | None:
    print(name + ": ", end='', flush=True)
    out = ""
    paste_mode=True
    while 1:
        if paste_mode: 
            out = input("")
            break

        c = getkey()
        if c == 'esc':
            out = ""
            print("")
            break
        elif c == 'return':
            print("")
            break
        elif c == 'paste':
            paste_mode=True
        elif c == 'backspace':
            if len(out):
                print('\b \b', end='', flush=True)
                out = out[:-1]
        elif c in ['up', 'down', 'left', 'right', 'tab']:
            out = out
        else:
            print(c, end='', flush=True)
            out += c

    if not len(out):
       return None

    return out

def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [option] ... [input]",
        description="Add or modify inventree parts"
    )
    parser.add_argument(
        "-i", "--interactive", required=False,
        action='store_true',
        help="Run in interactive mode"
    )
    # parser.add_argument(
    #     "-r", "--replace", required=False,
    #     action='store_true',
    #     help="Replace parts with generics"
    # )
    # parser.add_argument(
    #     "-c", "--check", required=False,
    #     action='store_true',
    #     help="Check if parts exist"
    # )
    parser.add_argument(
        "-a", "--assembly", required=False,
        help="Create/modify an assembly part, and add the provided items to the BOM. Must be a valid python dict with the following fields: ipn, rev, name (optional, defaults to ipn), desc (optional), append (optional, defaults to False), image (optional, [PCB image, PCBA image] defaults to []), attachments (optional, list of attachments [PCB Attachments, PCBA Attachments], defaults to [])"
    )
    parser.add_argument(
         "--dry", required=False,
        choices=['all', 'parts', 'assemblies'],
        help="Do not create parts in inventree"
    )
    parser.add_argument(
        "--settings", required=False,
        help="Settings file, containing inventree, IPN, and supplier API settings"
    )
    parser.add_argument(
        "--digi_token", required=False,
        help="Digikey token file"
    )
    parser.add_argument("--variants",
                        required= False,
                        help="Create template parts and link to variants (always on in interactive mode)")
    parser.add_argument("-p", "--path",
                        required= False,
                        help="Path to a CSV file, ';' delimited")
    parser.add_argument("-s", "--string",
                        required= False,
                        help="CSV string, ';' delimited")

    return parser

def stringify_list_dict(obj):
    # Make sure fields are stringified
    obj = re.sub("\[[\s\t]*\[", "[[", obj)
    obj = re.sub("\][\s\t]*\]", "]]", obj)
    obj = re.sub("([^\]]),", "\g<1>', '", obj)
    obj = re.sub("([^\]]): ", "\g<1>': ", obj)
    obj = re.sub("([^\]])\]", "\g<1>']", obj)
    obj = re.sub("\[([^\[])", "['\g<1>", obj)
    # Only the opening dict bracket needs to be quoted
    obj = re.sub("{", "{'", obj)
    # Enclose all in square brackets if not dict or already an overall list
    if not obj.startswith("[["):
        obj = "[" + obj + "]"
    return obj


def unique_item(manf, mpn, rev):
    return manf + "_" + mpn + "_" + rev

class Assembly:
    def __init__(self, ipn, manf, rev):
        self.ipn = ipn
        self.manf = manf
        self.rev = rev
        self.blanks = []
        self.sub_assemblies = {}
        self.parts = {}
        self.csv = []
        self.headers = {}
        self.header_row = 0
        self.path = []
        
    def add_combine_parts(self, part):
        curr = unique_item(part['manf'], part['mpn'], part['rev'])
        # Get existing (or default to part)
        updated = self.parts.get(curr, part)
        # Update existing
        if updated != part:
            # Combine refs
            updated['refs'] += ' ' + part['refs']
            # Combine qty
            updated['qty'] += part['qty']
        # Updated parts dict
        self.parts[curr] = updated

    def process_conn(self, ref, apn, manf, rev, conn_manf, conn_mpn):
        conn_bom = []
        # conn_mpn defaults to 'apn.csv'
        if not len(conn_mpn):
            conn_mpn = apn + '.csv' 
        # if conn_mpn is entered, conn_manf must be too
        elif conn_mpn.startswith('['):
            conn_mpn = stringify_list_dict(conn_mpn)
            conn_bom = eval(conn_mpn)
            bom_type = type(conn_bom)
            if bom_type != list:
                print("Invalid conn_mpn field: ", conn_mpn)
                return

            csv_str = "refs;mpn;manf;qty;rev;conn_mpn;conn_manf;supp;spn\n" 
            for j in range(0, len(conn_bom)):
                for i in range(0, len(conn_bom[j])):
                    conn_bom[j][i] = conn_bom[j][i].lstrip()

                [refc, manf, mpn, qty] = conn_bom[j]
                csv_str += "{};{};{};{};;;;;".format(refc + ref, mpn, manf, qty)
                # # Create part, ref must be made unique buy appending the ref for the owning part
                # part = {'refs': refc + ref, 'manf': manf, 'mpn': mpn, 'qty': int(qty), 'rev': ''}
                # self.add_combine_parts(part)
            conn_mpn = csv_str

        if conn_manf == 'sub':
            sub = Assembly(apn, manf, rev)
            sub.csv_parse(conn_mpn, self.path)
            # TODO basic check of subassembly
            self.sub_assemblies[apn] = sub
        elif conn_manf == 'local':
            for j in range(0, len(conn_bom)):
                [refc, manf, mpn, qty] = conn_bom[j]
                # Create part, ref must be made unique buy appending the ref for the owning part
                part = {'refs': refc + ref, 'manf': manf, 'mpn': mpn, 'qty': int(qty), 'rev': ''}
                self.add_combine_parts(part)

    def csv_parse(self, csv_str, path_prefix=''):
        path,_ext = os.path.splitext(path_prefix + '/' + csv_str)
        path += '.csv'
        print("Path: ", path)
        if os.path.exists(path):
            self.path = os.path.dirname(path)
            with open(path, 'r') as file:
                csv_str = file.read()
        print("CSV str: ", csv_str)
        # Remove any windows line endings
        csv_str = csv_str.replace('\r', '')
        # Split into lines
        csv_str = csv_str.split('\n')
        self.csv = list(csv.reader(csv_str, delimiter=';'))

        REF_FIELDS = ['refs', 'mpn', 'manf', ['qty', 'quantity'], ['rev', 'revision'], 'conn_mpn', 'conn_manf', 'supp', 'spn']
        PASS_MASK = (1 << (len(REF_FIELDS) - 2)) - 1;
        for row in self.csv: 
            mask = 0
            self.headers = {}
            for item in row:
                i = row.index(item)
                for j, field in enumerate(REF_FIELDS):
                    keys = field
                    if type(field) == str:
                        keys = [field]
                    res = False
                    for k in keys:
                        if k == item.lower():
                            self.headers[keys[0]] = i
                            mask |= 1 << j
                            res = True
                            break
                    if res:
                        break
            self.header_row += 1
            # The 'supp' and 'spn' are optional
            if mask & PASS_MASK == PASS_MASK:
                break

        if self.header_row > len(row) - 1:
            print("Invalid CSV Formatting, could not find all the required headers")
            return

        max_len = max(*self.headers.values()) + 1
        for row in self.csv[self.header_row:]: 
            if len(row) < max_len:
                continue
            conn_mpn = row[self.headers['conn_mpn']].lstrip()
            conn_manf = row[self.headers.get('conn_manf', '')].lstrip()
            ref = row[self.headers['refs']]
            mpn = row[self.headers['mpn']]
            manf = row[self.headers['manf']]
            rev = row[self.headers['rev']]

            self.process_conn(ref, mpn, manf, rev, conn_manf, conn_mpn)

            qty = row[self.headers['qty']]
            if not len(ref) and len(qty):
                continue
            elif not len(mpn):
                self.blanks.append(ref)
                continue

            part = {'refs': ref, 'manf': manf,'mpn': mpn, 'qty': int(qty), 'rev': rev}
            # New entry or append to existing
            self.add_combine_parts(part)


    def create(self, dry, variants) -> list: 
        res = []
        for sub in self.sub_assemblies.values():
            res += sub.create(dry, variants)
        # Don't run on entries that are sub assemblies
        # they are created later 
        no_sub = []
        for p in self.parts.values():
            if p.get('mpn', '') not in self.sub_assemblies.keys():
                no_sub.append(p)
            
        res += search_and_create(no_sub, dry, variants)

        return res


    def check(self) -> bool:
        # this could be conglomerated, but it just costs some time
        for sub in self.sub_assemblies.values():
            sub.check()

        inventree_interface.connect_to_server()
        res = True
        for row in self.csv[self.header_row:]: 
            mpn = row[self.headers['mpn']].lstrip()
            rev = row[self.headers['rev']].lstrip()
            local_res = find_part(mpn, rev) is None
            print("Res: ", local_res)
            if local_res:
                print("Unable to find part: ", mpn, " ", rev)
            res &= not local_res
        return res


    def assembly(self, assembly_dict) -> bool:
        return create_assembly(assembly_dict, list(self.parts.values()))

    def parse(self, csv_str, assembly_dict, dry, variants) -> dict | None:
        self.csv_parse(csv_str)

        # Create all bom parts (including those in sub assemblies)
        res = self.create(dry, variants)

        # if args.replace:
        #     #
        #     print("Found mpns with generics")

        possible_generics = []
        for part in res:
            if type(part) is tuple:
                possible_generics.append(part)

        for part in possible_generics:
            res.remove(part)
            print(part[0], " could be replaced by: ", part[1])

        if len(res):
            print("Parts could not be added: ", res)

        if len(self.blanks):
            print("Parts have no mpn: ", self.blanks)

        res = not len(res) and not len(self.blanks)

        if assembly_dict is None:
            return res

        # Remove 'V' from rev
        rev = assembly_dict.get('rev', '').replace('V','').replace('v','')
        # rev can be a tuple/list:
        # (Board Rev, Assembly Rev)
        if type(rev) == str:
            rev = (rev, rev)
        assembly_dict['rev'] = rev[1]

        # Parse attachments
        attachments = assembly_dict.get('attachments', [])
        if len(attachments):
            attachments = attachments[0]

        # Parse images
        images = assembly_dict.get('image', [])
        pcb_image = ''
        if len(images):
            pcb_image = images[0]

        # Parse description
        desc = assembly_dict.get('desc', '')
        if len(desc):
            desc = 'PCB ' + desc

        # Add the bare board if the assembly is PCBA
        if assembly_dict.get('category', '') == 'PCBA':
            # IPN of board is one char less than the assembly IPN
            # Match revision to assembly
            board_ipn = assembly_dict['ipn'][:-1]
            self.parts[board_ipn] = {'refs': 'BRD1', 'manf': 'Micromelon', 'mpn': board_ipn, 'rev': rev[0], 'qty': 1, 'image': pcb_image, 'desc': desc, 'attachments': attachments}


        # Only create assembly if no errors, not a dry run
        # and assembly dict is specified
        if dry or not res or not len(assembly_dict):
            return None 

        for sub in self.sub_assemblies.values():
            # Find the supplier and spn from the top level assembly
            supp = ''
            spn = ''
            ref = ''
            for row in self.csv[self.header_row:]:
                if row[self.headers['mpn']] != sub.ipn:
                    continue
                supp = row[self.headers['supp']]
                spn = row[self.headers['spn']]
                ref = row[self.headers['refs']]
                break;

            # spn => ipn if supp is specified
            if len(supp) and not len(spn):
                spn = sub.ipn

            # Category is the ref prefix
            (_, ref_prefix) = is_template(ref, sub.ipn)

            category = REF_TO_CATEGORY.get(ref_prefix)

            # Assemble dict for the sub assembly
            sub_dict = {'manf': sub.manf, 'ipn': sub.ipn, 'name': sub.ipn, 'supp': supp, 'spn': spn, 'desc': '', 'rev': sub.rev, 'category': category} 
            # Create parts for the sub assemblies
            res &= sub.assembly(sub_dict)
        res &= self.assembly(assembly_dict)
        if not res:
            return None
        return assembly_dict

def main():
    parser = init_argparse()
    args = parser.parse_args()

    # Collect settings
    if args.settings:
        settings.CONFIG_DIGIKEY_API = args.settings
        settings.CONFIG_MOUSER_API = args.settings
        settings.CONFIG_ELEMENT14_API = args.settings
        settings.CONFIG_IPN_PATH = args.settings
        settings.INVENTREE_CONFIG = args.settings

        settings.load_ipn_settings()
        settings.load_inventree_settings()

    # Digikey token can be manually provided
    if args.digi_token:
        token_path = os.path.dirname(args.digi_token)
        if len(token_path) == 0:
            token_path = os.getcwd()
        settings.DIGIKEY_STORAGE_PATH = token_path
        os.environ['DIGIKEY_STORAGE_PATH'] = settings.DIGIKEY_STORAGE_PATH

    # The cli checks itself, disable the later checks
    settings.CHECK_EXISTING = False

    # settings_file = [
    #     global_settings.INVENTREE_CONFIG,
    #     global_settings.CONFIG_IPN_PATH,
    # ]
    #
    # if args.settings_inv:
    #     settings_file[0] = args.settings_inv
    # if args.settings_ipn:
    #     settings_file[1] = args.settings_ipn
    #
    # settings = {
    #     **config_interface.load_inventree_user_settings(settings_file[0]),
    #     **config_interface.load_file(settings_file[1]),
    # }
    # load_cache_settings()

    dry = [args.dry == 'all' or args.dry == 'parts', args.dry == 'all' or args.dry == 'assemblies']

    if args.interactive:
        while 1:
            print("Valid Types: ", list(REF_TO_CATEGORY.keys()))
            ref = (get_input("Type") or '').upper()
            if not len(ref) or ref not in REF_TO_CATEGORY.keys():
                print("Invalid type, valid types are: ", list(REF_TO_CATEGORY.keys()))
                continue
            manf = get_input("Manf")
            if manf is None:
                continue
            mpn = get_input("Mpn")
            if mpn is None:
                continue

            print("--------------------------------")
            print("Type: ", ref)
            print("Manf: ", manf)
            print("MPN: ", mpn)
            confirm = input("Is this correct (Y/n): ")
            if not len(confirm) or 'Y' in confirm.upper():
                part = [{'refs': ref+'1', 'manf': manf, 'mpn': mpn, 'qty': 1}]
                search_and_create(part, dry, variants=True)
            print("--------------------------------")
        return;


    # Only progress if bom provided
    if not len(args.bom):
        return;

    # Parse assembly_dict
    assembly_dict = None
    ipn = ''
    rev = ''
    if args.assembly:
        assembly_dict = eval(args.assembly)
        ipn = assembly_dict.get('ipn', '')
        manf = assembly_dict.get('manf', 'Micromelon')
        rev = assembly_dict.get('rev', '')

    # Parse provided list of parts and create assembly if assembly_dict specified
    assembly = Assembly(ipn, manf, rev)
    res = assembly.parse(args.bom, assembly_dict, args.dry, args.variants)

    blank_parts = []
    extra_rows = {}
    extra_assemblies = {}
    unique_parts = {}
    part_list = []
    part_list_dict = []
    max_len = max(*ref_dict.values()) + 1
    for row in list(r)[first_line:]: 
        if len(row) < max_len:
            continue
        conn_mpn = row[ref_dict['conn_mpn']].lstrip()
        conn_manf = row[ref_dict.get('conn_manf', '')].lstrip()
        ref = row[ref_dict['refs']]
        # if conn_mpn is entered, conn_manf must be too
        if len(conn_mpn):
            if not (conn_mpn.startswith('[') or conn_mpn.startswith('{')):
                print("Invalid conn_mpn: ", conn_mpn)
                # conn_mpn = "['" + conn_manf + "', '" + conn_mpn + "', 1']"
            else:
                # Make sure fields are stringified
                conn_mpn = re.sub(r'\[[\s\t]*\[', "[[", conn_mpn)
                conn_mpn = re.sub(r'\][\s\t]*\]', "]]", conn_mpn)
                conn_mpn = re.sub(r'([^\]]),', r'\g<1>\', \'', conn_mpn)
                conn_mpn = re.sub(r'([^\]]): ', r'\g<1>\': ', conn_mpn)
                conn_mpn = re.sub(r'([^\]])\]', r'\g<1>\']', conn_mpn)
                conn_mpn = re.sub(r'\[([^\[])', r'[\'\g<1>', conn_mpn)
                # Only the opening dict bracket needs to be quoted
                conn_mpn = re.sub("{", "{'", conn_mpn)
                # Enclose all in square brackets if not dict or already an overall list
                if not (conn_mpn.startswith('{') or conn_mpn.startswith("[[")):
                    conn_mpn = "[" + conn_mpn + "]"
                conn_bom = eval(conn_mpn)
                bom_type = type(conn_bom)
                if bom_type not in [list, dict]:
                    print("Invalid conn_mpn field: ", conn_mpn)

                print("type: ", bom_type)
                if bom_type == dict:
                    for k,v in conn_bom.items():
                        for j in range(0, len(v)):
                            for i in range(0, len(v[j])):
                                v[j][i] = v[j][i].lstrip()
                        if k not in extra_rows.keys():
                            extra_rows[k] = {}
                        extra_rows[k][ref] = v
                else:
                    for j in range(0, len(conn_bom)):
                        for i in range(0, len(conn_bom[j])):
                            conn_bom[j][i] = conn_bom[j][i].lstrip()
                    if board_ipn not in extra_rows.keys():
                        extra_rows[board_ipn] = {}
                    extra_rows[board_ipn][ref] = conn_bom

        mpn = row[ref_dict['mpn']]
        manf = row[ref_dict['manf']]
        qty = row[ref_dict['qty']]
        rev = row[ref_dict['rev']]

        valid_flag = len(ref) and len(qty)
        if not valid_flag:
            continue
        elif not len(mpn):
            blank_parts.append(ref)
            continue

        qty = int(qty)
        part = {'refs': ref, 'manf': manf, 'mpn': mpn, 'qty': qty, 'rev': rev}
        # New entry or append to existing
        unique_item = manf + "_" + mpn + "_" + rev
        # Combine and update
        if unique_item in unique_parts:
            updated = copy.deepcopy(unique_parts[unique_item])
            # Combine refs
            updated['refs'] += ' ' + ref
            # Combine qty
            updated['qty'] += qty
            # Replace part_list entry with updated entry
            part_list[part_list.index(unique_parts[unique_item])] = updated
            # Replace unique_parts entry with updated entry
            unique_parts[unique_item] = updated
        # New
        else:
            unique_parts[unique_item] = part
            part_list.append(part)

    # Go through extra_rows and merge
    # [ref, manf, mpn, qty]
    for (board, d) in extra_rows.items():
        for (parent, bom) in d.items():
            # Split the ref into individual numbers
            par_r = re.search(r'([A-Z]+)\d', parent).groups()[0]
            par_i = []
            par_ranges = re.findall(par_r + r'\d', parent)
            for rang in par_ranges:
                item = rang.replace(par_r, "")
                sp = item.split('-')
                start = int(sp[0])
                fin = start + 1
                # If there is a '-', then the trailing number is the end
                if len(sp) > 1:
                    fin = int(fin) + 1

                # append all in the range (x1000)
                for i in range(start, fin):
                    # par_i.append(i*1000)
                    par_i.append(i)

            for entry in bom:
                [ref, manf, mpn, qty] = entry[:4]
                qty = int(qty)
                rev = ''
                # rev is optional
                if len(entry) > 4:
                    rev = entry[4]
                # No need to sort into indiv items, as the formatting can stay the same
                # The numbers have to be unique within each ref
                qty_total = len(par_i)*qty
                ref_inds = []
                ref_total = ""
                for par_n in par_i:
                    # def ref_mult(matchobj):
                    #     n = int(matchobj.group(0))
                    #     return str(par_n + n)
                    # ref_total += re.sub("\d+", ref_mult, ref) + " "

                    for sub_ref in re.split(',| |\|', ref):
                        ref_total += "{}:{}{} ".format(sub_ref,par_r,par_n)
                ref_total = ref_total[:-1]

                part = {'refs': ref_total, 'manf': manf, 'mpn': mpn, 'qty': qty_total, 'rev': rev}

                # Check for matches in part_list
                unique_item = manf + "_" + mpn + "_" + rev

                if board == board_ipn:
                    # Combine and update
                    if unique_item in unique_parts:
                        updated = copy.deepcopy(unique_parts[unique_item])
                        # Combine refs
                        updated['refs'] += ' ' + ref
                        # Combine qty
                        updated['qty'] += qty
                        # Replace part_list entry with updated entry
                        part_list[part_list.index(unique_parts[unique_item])] = updated
                        # Replace unique_parts entry with updated entry
                        unique_parts[unique_item] = updated
                    # New
                    else:
                        unique_parts[unique_item] = part
                        part_list.append(part)
                else:
                    if board not in extra_assemblies.keys():
                        extra_assemblies[board] = []
                    part['refs'] += ":" + board_ipn 
                    extra_assemblies[board].append(part)


    print('List: ', part_list)
    print('Extra assemblies: ', extra_assemblies)

    if args.replace:
        #
        print('Found mpns with generics')

    if len(assembly_dict):
        # rev can be a list or str:
        # [Board Rev, Assembly Rev] or Rev
        rev = assembly_dict['rev']
        if type(rev) == str:
            rev = (rev, rev)
        elif type(rev) != list:
            print("'rev' cannot be a",type(rev))
            exit(0)
            
        for i in range(0,len(rev)):
            rev[i] = rev[i].replace('v','').replace('V','')

        print("Rev:", rev)
        assembly_dict['rev'] = rev[1]
        images = assembly_dict.get('image', [])
        attachments = assembly_dict.get('attachments', [])
        pcb_image = ''
        if len(images):
            pcb_image = images[0]
        if len(attachments):
            attachments = attachments[0]
        desc = assembly_dict.get('desc', '')
        if len(desc):
            desc = 'PCB ' + desc
        # IPN of board is one char less than the assembly IPN
        # Match revision to assembly
        part_list.append({'refs': 'BRD1', 'manf': 'Micromelon', 'mpn': assembly_dict['ipn'][:-1], 'rev': rev[0], 'qty': 1, 'image': pcb_image, 'desc': desc, 'attachments': attachments})
    (res, mismatch) = search_and_create(part_list, dry, args.variants)
    possible_generics = []
    for part in res:
        if type(part) is tuple:
            possible_generics.append(part)

    for part in possible_generics:
        res.remove(part)
        print(part[0], " could be replaced by: ", part[1])

    if len(res):
        print("Parts could not be added: ", res)
    if len(blank_parts):
        print("Parts have no mpn: ", blank_parts)
    if len(mismatch):
        print("Part name doesn't match supplier's (ours, theirs): ", mismatch)

    res = not len(res) and not len(blank_parts) and not len(mismatch)
    if not dry[1] and res and args.assembly:
        res &= create_assembly(assembly_dict, part_list)
        for board, board_list in extra_assemblies.items():
            assembly_dict['ipn'] = board
            assembly_dict['name'] = board
            assembly_dict['desc'] = ''
            assembly_dict['image'] = []
            assembly_dict['attachments'] = []
            res &= create_assembly(assembly_dict, board_list)
    exit(not res)

if __name__ == '__main__':
    main()

# Snippet to transfer suppliers
    # REAL_ID=<insert_int>
    # FAKE_ID=<insert_int>
    # inventree_interface.connect_to_server()
    # # print(inventree_api.get_all_companies())
    #
    # response = inventree_api.inventree_api.get("/company/"+str(FAKE_ID)+"/", id=str(FAKE_ID))
    # print(response)
    # parts = inventree_api.Company(inventree_api.inventree_api, pk=FAKE_ID).getSuppliedParts()
    # print("Num parts:", len(parts))
    # fail_flag = False
    # for p in parts:
    #     print("SPK:",p.pk, "PK:", p.part, "SKU:", p.SKU)
    #     local_flag = False
    #     for _retry in range(0,3):
    #         try:
    #             response = inventree_api.inventree_api.patch("company/part/"+str(p.pk),
    #             {
    #                 'supplier': REAL_ID,
    #             },
    #             headers = {"id": str(p.part)})
    #             local_flag = True
    #             break
    #         except Exception as e:
    #             if "unique set" in format(e):
    #                 local_flag = True
    #                 break
    #             print(e)
    #             continue
    #     if not local_flag:
    #         print("Failed")
    #         fail_flag = True
    #
    # print("Success?", not fail_flag)
