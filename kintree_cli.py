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

ref_to_category = {'R': ['Electronic Components', 'Resistors'], 'RN': ['Electronic Components', 'Resistors'], 'C':  ['Electronic Components', 'Capacitors'], 'CN':  ['Electronic Components', 'Capacitors'], 'D': ['Electronic Components', 'Diodes'], 'F': ['Electronic Components', 'Fuses'], 'Y': ['Electronic Components', 'Crystals'], 'J': ['Electronic Components', 'Connectors'], 'Q': ['Electronic Components', 'Transistors'], 'FB': ['Electronic Components', 'Ferrites'], 'U': ['Electronic Components', 'ICs'], 'L': ['Electronic Components', 'Inductors'], 'H': ['Standoffs & Spacers'], 'FL': ['Electronic Components', 'Chokes & Filters'], 'BRD': ['Bare PCBs'], 'CBL': ['Cable'], 'CBA': ['Cable Assemblies'], 'P': ['Cable Parts'], 'W': ['Cable Parts'] , 'B': ['Batteries'], 'MOD': ['Electronic Components', 'Modules'], 'SNS': ['Electronic Components', 'Sensors'], 'DSP': ['Displays'] }

def cap_generic(s: str, params = None) -> str:
    (val, unit, ) = re.search("([0-9]+[.]*[0-9]*)[ ]*([µuUmpP])[ ]*[Ff]*",s).groups()
    # val = ''
    # # Allow for a missing leading zero
    # if res:
    #     (val, ) = res.groups()
    # else:
    #     (val, ) =  re.search("([0-9]*[.][0-9]+)[ ]*[µuUmpP][ ]*[Ff]*",s).groups()
    # Make sure 'u' or 'p' aren't capitalised
    unit = unit.lower().replace('µ', 'u')

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
    (voltage,) = re.search("(\d+)[ ]*v",s.lower()).groups()

    if not (len(foot) and len(val) and len(unit) and len(tol) and len(voltage)):
        raise ValueError("Unable to find all parameters: ", foot, val, unit, tol, voltage)

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

    (tol,) = re.search("([0-9]+[.]*[0-9]*%)",s).groups()

    return "R_{}_{}{}_{}".format(foot, val, unit, tol)

ref_to_generic = { 'R': res_generic, 'C': cap_generic }


def create_part(search_form, category = [], ipn = '', template = False, variant = None, assembly = False):
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
    part_info['assembly'] = assembly

    part = None
    # Search for the IPN
    for _retry in range(0,3):
        try:
            part = inventree_api.get_part_from_ipn(search_term, search_form['revision'])
        except:
            continue
        break
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
        for _retry in range(0,3):
            try:
                _alt_result = inventree_interface.inventree_create_alternate(
                    part_info=part_info,
                    part_ipn=search_term,
                )
            except:
                continue
            break
    else:
        if category is None:
            print("Category cannot be blank when creating new part")
            return None
        part_info['category_tree'] = category
        # Create new part
        for _retry in range(0,3):
            try:
                _new_part, part_pk, part_info = inventree_interface.inventree_create(
                    part_info=part_info,
                    kicad=False,
                    symbol=None,
                    footprint=None,
                    show_progress=False,
                    is_custom=False,
                    stock=None,
                )
            except:
                continue
            break
    return part_pk

def is_template(ref: str, mpn: str) -> tuple[bool, str]:
    # Only care about the first one in the list
    ref_prefix = re.search("([A-Z]+)[0123456789]", ref).groups()[0]

    return (mpn[:(len(ref_prefix)+1)] == ref_prefix + '_', ref_prefix)

# bom parts must have: 'mpn','refs','qty' fields
def create_assembly(assembly: dict, bom: list[dict]) -> bool:
    ipn = assembly['ipn']
    search_form = {}
    for field in search_fields_list:
        search_form[field] = ''
    search_form['name'] = assembly.get('name', ipn)
    search_form['description'] = assembly.get('desc', '')
    search_form['revision'] = assembly['rev']
    search_form['manufacturer_name'] = 'Micromelon'
    search_form['manufacturer_part_number'] = ipn

    overwrite = not bool(assembly.get('append', False))

    inventree_interface.connect_to_server()

    pk  = create_part(search_form, category = ["Assembled PCBs"], assembly=True)

    if overwrite:
        inventree_api.delete_bom(pk)

    result = True

    for part in bom:
        (template_flag, _ref_prefix) = is_template(part['refs'], part['mpn'])
        if 'micromelon' in part['manf'].lower():
            # Must have a valid revision
            if not len(part['rev']):
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

    if not len(generic):
        return None

    print("")
    part_id = inventree_api.fetch_part('', generic)
    if part_id:
        print("Found existing generic: ", generic)
        return (part_id.pk, generic)

    print("Create new generic: '", generic, "'? (Y/n): ", end = '')
    confirm = input("")
    if not(len(confirm)) or confirm.upper() == 'Y':
        search_form = {}
        for field in search_fields_list:
            search_form[field] = ''
        search_form['name'] = generic
        search_form['manufacturer_part_number'] = generic
        return (create_part(search_form, category,  template = True), generic)
    
    return None


def search_and_create(part_list, variants=False, rev_default = '') -> list:
    inventree_interface.connect_to_server()
    result = []
    for part in part_list:
        ref = part['refs']
        manf = part['manf']
        mpn = part['mpn']
        rev = part.get('rev', rev_default)


        (template_flag, ref_prefix) = is_template(ref, mpn)

        category = ref_to_category.get(ref_prefix)
        if category is None:
            print("Unknown reference prefix: ", ref_prefix)
            continue


        # Do not create internal parts here
        # They will all be assemblies that should be created
        # separately
        if 'micromelon' in manf.lower():
            # Must have a valid revision
            if not len(rev):
                print("No revision found for internal part")
                continue
            # Create Bare PCB part
            if 'a' not in mpn.lower():
                search_form = {}
                for field in search_fields_list:
                    search_form[field] = ''
                search_form['name'] = mpn
                search_form['manufacturer_name'] = manf
                search_form['manufacturer_part_number'] = mpn
                search_form['revision'] = rev
                create_part(search_form, category)
            continue

        # Template part
        if template_flag:
            search_form = {}
            for field in search_fields_list:
                search_form[field] = ''
            search_form['name'] = mpn
            search_form['manufacturer_part_number'] = mpn
            create_part(search_form, category,  template = True)
            continue

        # Any part without a manf field is has an IPN specified
        if not len(manf):
            search_term = mpn
            # Search for the IPN
            for _retry in range(0,3):
                try:
                    part = inventree_api.get_part_from_ipn(search_term, rev)
                except:
                    continue
                break
            # Account for revision mismatch
            if part and part.revision != rev:
                part = None

            if part:
                # TODO: set the manufacturer and the continue as if part was not in inventree
                return
            else:
                print("Part does not have manf and is not an inventree IPN: ", mpn)
                return

        
        generic_id = None
        local_res = False
        for supp in usual_suppliers:
            (search_form, raw_form) = run_search(supp, mpn, manf)
            if len(search_form['name']) < 1:
                continue
            print(search_form)
            part = None
            # Only need to search for and update the variants once
            if variants and generic_id is None:
                res = find_generic(ref_prefix, search_form, raw_form, category)
                if res is not None:
                    (generic_id, _) = res
                    # print("Do you wish to set the name of part: ", mpn, " to :", generic_name, " ? (Y/n):", end='')
                    # confirm = input("")
                    # if not(len(confirm)) or confirm.upper() == 'Y':
                    #     search_form['name'] = generic_name
                part = create_part(search_form, category, variant=str(generic_id))
            else:
                part = create_part(search_form, category)

            if part:
                local_res = True

        if not local_res:
            print("Unable to create part: ", mpn)
            result.append(mpn)

    return result


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
    parser.add_argument(
        "-a", "--assembly", required=False,
        help="Create/modify an assembly part, and add the provided items to the BOM. Must be a valid python dict with the following fields: ipn, rev, name (optional, defaults to ipn), desc (optional), append (optional, defaults to False)"
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
    # create_assembly("999999A", [{'mpn': "ERA-6AEB49R9V", 'refs': "R1", 'qty': 1}], overwrite=False)
    # search_and_create([{'refs': "J1", 'manf': "Sullins",'mpn': "LPPB121NFFN-RC"}], variants=True)
    # exit(0)

    parser = init_argparse()
    args = parser.parse_args()
    if args.settings:
        settings.CONFIG_DIGIKEY_API = args.settings
        settings.CONFIG_MOUSER_API = args.settings
        settings.CONFIG_ELEMENT14_API = args.settings
        settings.CONFIG_IPN_PATH = args.settings
        settings.INVENTREE_CONFIG = args.settings

        settings.load_ipn_settings()
        settings.load_inventree_settings()

    if args.digi_token:
        settings.DIGIKEY_STORAGE_PATH = "/tmp"
        os.environ['DIGIKEY_STORAGE_PATH'] = settings.DIGIKEY_STORAGE_PATH
        if not os.path.exists(os.environ['DIGIKEY_STORAGE_PATH']):
            os.makedirs(os.environ['DIGIKEY_STORAGE_PATH'], exist_ok=True)
        shutil.copyfile(args.digi_token, "/tmp/token_storage.json")
        print("Copied token file to /tmp")
        print(os.listdir("/tmp"))

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

    if args.interactive:
        while 1:
            ref = get_input("Type").upper()
            if ref is None or ref.upper() not in ref_to_category.keys():
                print("Invalid type, valid types are: ", list(ref_to_category.keys()))
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
                search_and_create(part, variants=True)

            print("--------------------------------")
    else: 
        csv_str = args.string
        print("Path: ", args.path)
        if os.path.exists(args.path):
            with open(args.path, 'r') as file:
                csv_str = file.read()
        print("CSV srt: ", csv_str)
        # Remove any windows line endings
        csv_str = csv_str.replace('\r', '')
        # Split into lines
        csv_str = csv_str.split('\n')
        r = csv.reader(csv_str, delimiter=';')

        ref_fields = ['refs', 'mpn', 'manf', ['qty', 'quantity'], ['rev', 'revision'], 'conn_mpn', 'conn_manf']
        ref_dict = {}
        header_row = 0
        for row in r: 
            ref_dict = {}
            for item in row:
                i = row.index(item)
                for field in ref_fields:
                    keys = field
                    if type(field) == str:
                        keys = [field]
                    res = False
                    for k in keys:
                        if k == item.lower():
                            ref_dict[keys[0]] = i
                            res = True
                            break
                    if res:
                        break
            print(ref_dict)
            if len(ref_dict) == len(ref_fields):
                break
            header_row += 1


        if header_row > len(row) - 2:
            print("Invalid CSV Formatting, could not find all the required headers")
            exit(1)

        extra_rows = {}
        unique_parts = {}
        part_list = []
        part_list_dict = []
        max_len = max(*ref_dict.values()) + 1
        for row in list(r)[header_row + 1:]: 
            if len(row) < max_len:
                continue
            conn_mpn = row[ref_dict['conn_mpn']].lstrip()
            conn_manf = row[ref_dict.get('conn_manf', '')].lstrip()
            ref = row[ref_dict['refs']]
            # if conn_mpn is entered, conn_manf must be too
            if len(conn_mpn):
                if not conn_mpn.startswith('['):
                    print("Invalid conn_mpn: ", conn_mpn)
                    # conn_mpn = "['" + conn_manf + "', '" + conn_mpn + "', 1']"
                else:
                    # Make sure fields are stringified
                    conn_mpn = re.sub("([^\]]),[ ]*", "\g<1>', '", conn_mpn)
                    conn_mpn = re.sub("\]", "']", conn_mpn)
                    conn_mpn = re.sub("\[", "['", conn_mpn)
                    # Enclose all in square brackets
                    conn_mpn = "[" + "]"
                    conn_bom = eval(conn_mpn)
                    print(conn_bom)
                    if type(conn_bom) is not list:
                        print("Invalid conn_mpn field: ", conn_mpn)
                    extra_rows[ref] = conn_bom

            mpn = row[ref_dict['mpn']]
            manf = row[ref_dict['manf']]
            qty = row[ref_dict['qty']]
            rev = row[ref_dict['rev']]

            if len(ref) and len(mpn) and len(qty):
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
        for (parent, bom) in extra_rows.items():
            # Split the ref into individual numbers
            par_r = re.search("([A-Z]+)\d", parent).groups()[0]
            par_i = []
            par_ranges = re.findall(par_r + "\d", parent)
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

                    for sub_ref in re.split(",| |\|", ref):
                        ref_total += "{}:{}{} ".format(sub_ref,par_r,par_n)
                ref_total = ref_total[:-1]

                part = {'refs': ref_total, 'manf': manf, 'mpn': mpn, 'qty': qty_total, 'rev': rev}

                # Check for matches in part_list
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

        print("List: ", part_list)

        assembly_dict = {}
        if args.assembly:
            assembly_dict = eval(args.assembly)
            rev = assembly_dict['rev'].replace('V','')
            rev = rev.replace('v','')
            assembly_dict['rev'] = rev
            # IPN of board is one char less than the assembly IPN
            # Match revision to assembly
            part_list.append({'refs': 'BRD1', 'manf': 'Micromelon', 'mpn': assembly_dict['ipn'][:-1], 'rev': rev, 'qty': 1})
        res = search_and_create(part_list, args.variants)
        if len(res):
            print("Parts could not be added: ", res)
        res = not len(res)
        if res and args.assembly:
            res = create_assembly(assembly_dict, part_list)
        exit(not res)
