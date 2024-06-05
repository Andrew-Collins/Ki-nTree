from kintree.config.settings import load_cache_settings
from kintree.gui.views.main import *
from kintree.gui.views.settings import *
from kintree.database import inventree_api


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


settings_file = [
    global_settings.INVENTREE_CONFIG,
    global_settings.CONFIG_IPN_PATH,
]

settings = {
    **config_interface.load_inventree_user_settings(settings_file[0]),
    **config_interface.load_file(settings_file[1]),
}
load_cache_settings()

def create_part(search_form, category = [], ipn = ''):
    part_info = copy.deepcopy(search_form)
    part_number = part_info.get('manufacturer_part_number', None)
    # Update IPN (later overwritten)
    if len(ipn) == 0:
        ipn = part_number
    search_term = ipn
    part_info['IPN'] = ipn
    print("IPN: ", ipn)

    # Search for the IPN, falling back to the mpn
    part = inventree_api.fetch_part('', search_term)

    if part:
        print("Found part: ", part)
        # Create alternate
        alt_result = inventree_interface.inventree_create_alternate(
            part_info=part_info,
            part_ipn=search_term,
            show_progress=True,
        )
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


    return search_form

# def main(page: ft.Page):
def main():
    # search_form = run_search("Digi-Key", "BAT54", "Diotec")
    search_form = run_search("Element14", "BAT54", "Diodes Inc")
    print(search_form)

    inventree_interface.connect_to_server()
    create_part(search_form, ['Electronic Components'])


if __name__ == "__main__":
    main()
