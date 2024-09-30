from sys import exception
from kintree.config.settings import load_cache_settings
from kintree.gui.views.main import *
from kintree.gui.views.settings import *
from kintree.database import inventree_api

import re
import argparse
import sys
import csv

smt_sizes = ['0201', '0402', '0603', '0805','1206','1210', '1812', '2010', '2512']


search_fields_list = [
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

usual_suppliers = ["Digi-Key", "Mouser", "Element14"]

rename_supppliers = {"Digi-Key": "DigiKey"}

ref_to_category = {'R': ['Electronic Components', 'Resistors'], 'C':  ['Electronic Components', 'Capacitors'], 'D': ['Electronic Components', 'Diodes'], 'F': ['Electronic Components', 'Fuses'], 'Y': ['Electronic Components', 'Crystals'], 'J': ['Electronic Components', 'Connectors'], 'Q': ['Electronic Components', 'Transistors'], 'FB': ['Electronic Components', 'Ferrites'], 'U': ['Electronic Components', 'ICs'], 'L': ['Electronic Components', 'Inductors'], 'H': 'Standoffs & Spacers', 'FL': ['Electronic Components', 'Chokes & Filters'] }

settings_file = [
    global_settings.INVENTREE_CONFIG,
    global_settings.CONFIG_IPN_PATH,
]

settings = {
    **config_interface.load_inventree_user_settings(settings_file[0]),
    **config_interface.load_file(settings_file[1]),
}
load_cache_settings()

def cap_generic(s: str, params = None) -> str:
    (val, unit,) = re.search("([0-9][.][0-9]+)[ ]*([µuUmpP])[ ]*[Ff]*",s).groups()
    # Make sure 'u' or 'p' aren't capitalised
    unit = unit.lower()
    if unit == 'µ':
        unit = 'u'

    foot = ''
    for size in smt_sizes:
        if size in s:
            foot = size
            break
    if 'metric' in s.lower():
        (foot,) = re.search("(\d{4}).+[Mm][Ee][Tt][Rr][Ii][Cc].+",s).groups()
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
            (height,) = re.search("([0-9]+[.][0-9]+)[ ]*mm",params[height_key]+"mm").groups()
            (diameter,) = re.search("([0-9]+[.][0-9]+)[ ]*mm",params[size_key]+"mm").groups()
            # Convert to float to remove trailing zeros
            foot = "{}x{}".format(float(diameter), float(height))

    tol = ''
    tol_res = re.search("([XYN][57P][RV0])",s)
    if tol_res is None:
        tol_key = ''
        for key in params.keys():
            if 'tolerance' in key.lower():
                tol_key = key
                break
        if len(tol_key):
            (tol,) = re.search("([0-9]+[.]*[0-9]+%)",params[tol_key]).groups()
        else:
            (tol,) = re.search("([0-9]+[.]*[0-9]+%)",s).groups()
    else:
        (tol, )  = tol_res.groups()
    (voltage,) = re.search("(\d+)[ ]*v",s.lower()).groups()

    if not (len(foot) and len(val) and len(unit) and len(tol) and len(voltage)):
        raise ValueError("Unable to find all parameters")

    return "C_{}_{}{}_{}".format(foot, val, unit, tol, voltage)

def res_generic(s: str, params = None) -> str:
    (val, unit, _ohm,) = re.search("([0-9]+[.]*[0-9]+)[ ]*([kKmM])*[ ]*([Oo][Hh][Mm])*",s).groups()
    # Make sure 'k' isn't capitalised
    if unit is None:
        unit = 'R'
    if unit.lower() == 'k':
        unit = 'k'

    if '.' in val:
        val = val.replace('.', unit)
        unit = ''


    foot = ''
    for size in smt_sizes:
        if size in s:
            foot = size
            break
    if 'metric' in s.lower():
        (foot,) = re.search("(\d{4}).+[Mm][Ee][Tt][Rr][Ii][Cc].+",s).groups()

    (tol,) = re.search("([0-9]+[.]*[0-9]+%)",s).groups()

    return "R_{}_{}{}_{}".format(foot, val, unit, tol)

ref_to_generic = { 'R': res_generic, 'C': cap_generic }


def create_part(search_form, category = [], ipn = '', template = False, variant = None):
    part_info = copy.deepcopy(search_form)
    part_number = part_info.get('manufacturer_part_number', None)
    # Update IPN (later overwritten)
    if len(ipn) == 0:
        ipn = part_number
    search_term = ipn
    part_info['IPN'] = ipn
    print("IPN: ", ipn)
    if variant:
        part_info['variant'] = variant
    part_info['template'] = template

    # Search for the IPN, falling back to the mpn
    part = inventree_api.fetch_part('', search_term)

    # part = None
    #
    # category_pk = inventree_api.get_inventree_category_id(category)
    # if category_pk <= 0:
    #     cprint(f'[ERROR]\tCategory ({category}) does not exist in InvenTree', silent=settings.SILENT)
    #     return None
    # else:
    #     # Check if part already exists
    #     part = inventree_api.is_new_part(category_pk, part_info)


    if part:
        if template:
            print("Part is template, skipping")
            return None
        # Create alternate
        alt_result = inventree_interface.inventree_create_alternate(
            part_info=part_info,
            part_ipn=search_term,
        )
        return part.pk
    else:
        if category is None:
            print("Category cannot be blank when creating new part")
            return None
        part_info['category_tree'] = category
        # part_info['category_code'] = 'CON'
        # Category code
        # if settings.CONFIG_IPN.get('IPN_CATEGORY_CODE', False):
        #     if data_from_views['InvenTree'].get('Create New Code', False):
        #         part_info['category_code'] = data_from_views['InvenTree'].get('New Category Code', '')
        #     else:
        #         part_info['category_code'] = data_from_views['InvenTree'].get('IPN: Category Code', '')
        # Create new part
        new_part, part_pk, part_info = inventree_interface.inventree_create(
            part_info=part_info,
            kicad=False,
            symbol=None,
            footprint=None,
            show_progress=False,
            is_custom=False,
            stock=None,
        )
        return part_pk


def run_search(supplier, pn, manf = ''):
    # # Get supplier
    # supplier = inventree_interface.get_supplier_name(supplier)
    # Supplier search
    part_supplier_info = inventree_interface.supplier_search(
        supplier,
        pn,
        manf
    )

    part_supplier_form = None

    print(part_supplier_info)

    search_form = {}
    for field in search_fields_list:
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

def find_generic(ref_prefix, search_form, raw_form, category):
    generic = ''
    # try: 
    generic = ref_to_generic[ref_prefix](search_form['description'], params=raw_form['parameters'])
    # except ValueError as e:
    #     print("Unable to parse generic: ", e)
    # except:
    #     print("Unable to parse generic")
    #
    if not len(generic):
        return None

    print("")
    part_id = inventree_api.fetch_part('', generic)
    if part_id:
        print("Found existing generic: ", generic)
        return part_id.pk

    print("Create new generic: '", generic, "'? (Y/n): ", end = '')
    confirm = input("")
    if not(len(confirm)) or confirm.upper() == 'Y':
        search_form = {}
        for field in search_fields_list:
            search_form[field] = ''
        search_form['name'] = generic
        search_form['manufacturer_part_number'] = generic
        return create_part(search_form, category,  template = True)
    
    return None


def search_and_create(part_list, variants=False):
    inventree_interface.connect_to_server()
    for part in part_list:
        ref = part[0]
        manf = part[1]
        mpn = part[2]

        ref_prefix = ref.rstrip('0123456789') 
        category = ref_to_category.get(ref_prefix)
        if category is None:
            print("Unknown reference prefix: ", ref_prefix)
            continue

        # Template part
        if mpn[:(len(ref_prefix)+1)] == ref_prefix + '_':
            search_form = {}
            for field in search_fields_list:
                search_form[field] = ''
            search_form['name'] = mpn
            search_form['manufacturer_part_number'] = mpn
            create_part(search_form, category,  template = True)
            continue
        
        generic_id = None
        for supp in usual_suppliers:
            (search_form, raw_form) = run_search(supp, mpn, manf)
            if len(search_form['name']) < 1:
                continue
            print(search_form)
            # Only need to search for and update the variants once
            if variants and generic_id is None:
                generic_id = find_generic(ref_prefix, search_form, raw_form, category)
                create_part(search_form, category, variant=str(generic_id))
            else:
                create_part(search_form, category)




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
    parser.add_argument("-p", "--path",
                        required= False,
                        help="Path to a CSV file, ';' delimited")

    parser.add_argument("-s", "--string",
                        required= False,
                        help="CSV string, ';' delimited")

    return parser

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
                # 65: 'up',
                # 66: 'down',
                # 67: 'right',
                # 68: 'left'
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
            # print("")
            # out = input("<Paste Mode>: ")
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
                print("\b \b", end='', flush=True)
                out = out[:-1]
        elif c in ['up', 'down', 'left', 'right', 'tab']:
            out = out
        else:
            print(c, end='', flush=True)
            out += c

    if not len(out):
       return None

    return out


if __name__ == "__main__":
    search_and_create([["R1", "Panasonic","ERA-6AEB49R9V"]], variants=True)

    # parser = init_argparse()
    # args = parser.parse_args()
    #
    # if args.interactive:
    #     while 1:
    #         ref = get_input("Type")
    #         if ref is None or ref.upper() not in ref_to_category.keys():
    #             print("Invalid type, valid types are: ", list(ref_to_category.keys()))
    #             continue
    #         manf = get_input("Manf")
    #         if manf is None:
    #             continue
    #         mpn = get_input("Mpn")
    #         if mpn is None:
    #             continue
    #
    #         print("--------------------------------")
    #         print("Type: ", ref.upper())
    #         print("Manf: ", manf)
    #         print("MPN: ", mpn)
    #         confirm = input("Is this correct (Y/n): ")
    #         if not len(confirm) or 'Y' in confirm.upper():
    #             search_and_create([[ref.upper(), manf,mpn]])
    #
    #         print("--------------------------------")
    # else: 
    #     csv_str = args.string
    #     if os.path.exists(args.path):
    #         with open(args.path, 'r') as file:
    #             csv_str = file.read()
    #     # Remove any windows line endings
    #     csv_str = csv_str.replace('\r', '')
    #     # Split into lines
    #     csv_str = csv_str.split('\n')
    #     r = csv.reader(csv_str, delimiter=';')
    #
    #     ref_ind = -1
    #     mpn_ind = -1
    #     manf_ind = -1
    #     header_row = 0
    #     for row in r: 
    #         ref_ind = -1
    #         mpn_ind = -1
    #         manf_ind = -1
    #         for k in row:
    #             i = row.index(k)
    #             if 'ref' in k.lower():
    #                 ref_ind = i
    #             elif 'mpn' in k.lower():
    #                 mpn_ind = i
    #             elif 'manf' in k.lower():
    #                 manf_ind = i
    #
    #         if manf_ind > -1 and mpn_ind > -1 and ref_ind > -1:
    #             break
    #
    #
    #     if header_row > len(row) - 2:
    #         print("Invalid CSV Formatting, could not find all the required headers")
    #         exit
    #
    #     part_list = []
    #     max_len = max(ref_ind, mpn_ind, manf_ind) + 1
    #     for row in list(r)[header_row + 1:]: 
    #         if len(row) < max_len:
    #             continue
    #         # Only care about the first one in the list
    #         ref = re.split(",| |\|", row[ref_ind])[0]
    #         mpn = row[mpn_ind]
    #         manf = row[manf_ind]
    #
    #         if len(ref) and len(mpn) and len(manf):
    #             part_list.append([ref, manf, mpn])
    #     search_and_create(part_list)
    #
    #
    # # search_and_create([["D1", "onsemi","BAT54"]])
    # # search_and_create([["R1", "","R_0603_10k_5%"]])
    # # search_and_create([["R1", "TE Connectivity","CRGP0402F82K"]])
    # # search_and_create([["C1", "Murata","GRM188R60J226MEA0D"]])
    # # search_and_create([["C1", "Wurth","865080545012"]])
