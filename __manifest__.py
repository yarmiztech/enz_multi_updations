# -*- coding: utf-8 -*-
{
    'name': "Enz Multi Updation",
    'author':
        'YARMIZ',
    'summary': """
This module will help to assign the targets to sales persons
""",

    'description': """
        Long description of module's purpose
    """,
    'website': "",
    'category': 'base',
    'version': '12.0',
    'depends': ['base','account',"stock","sale","contacts","enz_mc_owner"],
    "images": ['static/description/icon.png'],
    'data': [
        'security/ir.model.access.csv',
        'security/cah_security.xml',
        'data/seq.xml',
        'views/orders.xml',
        'views/invoice_cancellation.xml',
        'views/cash_book_report.xml',
        'report/tax_invoice_report.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': True,
}
