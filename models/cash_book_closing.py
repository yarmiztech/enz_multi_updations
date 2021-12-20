# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _

from datetime import date
from datetime import datetime
from datetime import datetime, timedelta
from odoo.exceptions import UserError, ValidationError
import calendar
import re
import json
from dateutil.relativedelta import relativedelta
import pgeocode
import qrcode
from PIL import Image
from random import choice
from string import digits
import json
import re
import uuid
from functools import partial



class CashBookInfo(models.Model):
    _inherit = "cash.book.info"

    closed = fields.Boolean(default=False)




class CashBookClosing(models.Model):
    _name = "cash.book.closing"
    _order = "id desc"

    name = fields.Char("Name", index=True, default=lambda self: _('New'))
    state = fields.Selection([('draft', 'Draft'), ('validate', 'Done'), ('cancelled', 'Cancelled')], readonly=True,
                             default='draft', copy=False, string="Status")

    today_cash_lines = fields.One2many('cash.book.closing.line','cash_book')
    date = fields.Date('Date', required=True, default=fields.Date.context_today)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            if 'company_id' in vals:
                vals['name'] = self.env['ir.sequence'].with_context(force_company=vals['company_id']).next_by_code(
                    'cash.book.closing') or _('New')
            else:
                vals['name'] = self.env['ir.sequence'].next_by_code('cash.book.closing') or _('New')
        return super(CashBookClosing, self).create(vals)


    @api.onchange('date')
    def onchange_date(self):
        self.today_cash_lines = False
        today_data = self.env['cash.book.info'].search([('closed','=',False),('date', '=', self.date)])
        if self.date:
           land_list = []
           self.today_cash_lines = False
           for each_data in today_data:
                # each_data.closed = True
                line = (0, 0, {
                    'payment_type':each_data.payment_type,
                    'description': each_data.description,
                    'account': each_data.account.id,
                    'debit':each_data.debit,
                    'credit':each_data.credit,
                    'balance':each_data.balance
                })
                land_list.append(line)
           self.today_cash_lines = land_list
       #     self.env['cash.book.info'].create({
       #     'date': datetime.today().date(),
       #     'account_journal': today_data[-1].account_journal.id,
       #     # 'partner_id': self.partner_id.id,
       #     'company_id': 1,
       #     'description': 'Opening Balance/Cash',
       #     'payment_type': 'inbound',
       #     # 'partner_type': self.partner_type,
       #     'debit': today_data[-1].debit,
       #     'credit': today_data[-1].credit,
       #     'account': today_data[-1].account.id,
       #     # 'payment_id': self.id,
       #     'balance': today_data[-1].balance
       # })

    def action_cash_book_close(self):
        print('dfdrgfd')
        today_data = self.env['cash.book.info'].search([('date', '=', self.date)])
        self.write({'state':'validate'})
        for each in today_data:
            each.closed = True
        self.env['cash.book.info'].create({
            'date': datetime.today().date() + relativedelta(days=1),
            'account_journal': today_data[-1].account_journal.id,
            # 'partner_id': self.partner_id.id,
            'company_id': 1,
            'description': 'Opening Balance/Cash',
            'payment_type': 'inbound',
            # 'partner_type': self.partner_type,
            'debit': today_data[-1].balance,
            'credit': 0,
            'account': today_data[-1].account.id,
            # 'payment_id': self.id,
            'balance': today_data[-1].balance
        })


class CashBookClosingLines(models.Model):
    _name = "cash.book.closing.line"

    cash_book = fields.Many2one('cash.book.closing')
    payment_type = fields.Selection([('outbound', 'Send Money'), ('inbound', 'Receive Money')], string='Payment Type')
    description = fields.Char(string='Description')
    account = fields.Many2one('account.account',string="Account")
    debit = fields.Float(string='Debit')
    credit = fields.Float(string='Credit')
    balance = fields.Float(string='Balance')



class InterBranchTransferLine(models.Model):
    _inherit = 'inter.branch.transfer.line'

    product_hsn_code = fields.Char(string="HSN Code")
    tax_ids = fields.Many2many('account.tax', string='Tax', help="Only for tax excluded from price")


class InterBranchTransfer(models.Model):
    _inherit = 'inter.branch.transfer'

    vehicle_no = fields.Char(string="Vehicle No")


