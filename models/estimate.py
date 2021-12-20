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



class SaleEstimateLines(models.Model):
    _inherit = "sale.estimate.lines"



    vahicle_char = fields.Many2one('vehicle.simply', string='Vehicle')

    def _compute_read_case(self):
        for each in self:
            if each.estimate_id.est_order_id:
                if each.owner_status == 'draft':
                   each.read_case = False
                else:
                    each.read_case = True
            else:
                each.read_case =False


class VehicleSimply(models.Model):
    _inherit = 'vehicle.simply'


    vehi_reg = fields.Char('Registration No',required=True)


class SalesExecutiveCollections(models.Model):
    _inherit = "executive.collection"

    state = fields.Selection([('draft', 'Draft'), ('validate', 'Validate'),('reverse', 'Reverse Entry'), ('cancelled', 'Cancelled')], readonly=True, default='draft', copy=False, string="Status")



    def action_confirm(self):

        for line in self.partner_invoices:
            stmt = self.env['account.bank.statement']
            if line.amount_total == 0.0:
                raise UserError(_("Please mention paid amount for this partner %s ") % (line.partner_id.name))
            cv = 0
            if line.check_type == 'cheque':
                journal = self.env['account.journal'].search(
                    [('name', '=', 'Bank'), ('company_id', '=', self.env.user.company_id.id)])
            else:
                journal = line.journal_id.id
            if not stmt:
                # _get_payment_info_JSON
                # bal = sum(self.env['account.move.line'].search([('journal_id', '=', line.journal_id.id)]).mapped(
                #     'debit'))

                if self.env['account.bank.statement'].search([('company_id', '=', line.journal_id.company_id.id),
                                                              ('journal_id', '=', line.journal_id.id)]):
                    bal = self.env['account.bank.statement'].search(
                        [('company_id', '=', line.journal_id.company_id.id),
                         ('journal_id', '=', line.journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                stmt = self.env['account.bank.statement'].create({'name': line.partner_id.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': line.journal_id.id,
                                                                  'balance_end_real': bal+line.amount_total

                                                                  })

            payment_list = []
            pay_id_list = []
            account = self.env['account.invoice'].search(
                [('partner_id', '=', line.partner_id.id),('company_id','=',line.journal_id.company_id.id),('state', '=', 'open')])
            amount = line.amount_total
            actual = 0
            if account:
               for check_inv in account:
                if amount:
                    if check_inv.amount_total >= amount:
                        actual = amount

                        product_line = (0, 0, {
                            'date': line.date,
                            'name': check_inv.display_name,
                            'partner_id': line.partner_id.id,
                            'ref': check_inv.display_name,
                            'amount': amount
                        })
                        amount = amount - amount
                        payment_list.append(product_line)
                    else:
                        if check_inv.amount_total != 0:
                            amount = amount - check_inv.amount_total
                            actual = check_inv.amount_total
                            product_line = (0, 0, {
                                'date': line.date,
                                'name': check_inv.display_name,
                                'partner_id': line.partner_id.id,
                                'ref': check_inv.display_name,
                                'amount': check_inv.amount_total
                            })
                            payment_list.append(product_line)

                    j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
                    pay_id = self.env['account.payment'].create({'partner_id': line.partner_id.id,
                                                                 # 'amount': check_inv.amount_total,
                                                                 'amount': actual,
                                                                 'partner_type': self.partner_type,
                                                                 'company_id': self.env.user.company_id.id,
                                                                 'payment_type': self.payment_type,
                                                                 'payment_method_id': self.payment_method_id.id,
                                                                 # 'journal_id': line.journal_id.id,
                                                                 'journal_id': line.journal_id.id,
                                                                 'communication': 'Cash Collection',
                                                                 'invoice_ids': [(6, 0, check_inv.ids)]
                                                                 })
                    pay_id.action_validate_invoice_payment()
                    pay_id.action_cash_book()
                    for k in pay_id.move_line_ids:
                        pay_id_list.append(k.id)
                    line.payments += pay_id
                    invoices = self.env['account.invoice'].search(
                        [('partner_id', '=', line.partner_id.id),
                         ('company_id', '=', self.env.user.company_id.id), ('state', '!=', 'paid')])
                    if invoices.mapped('residual'):
                        bal = sum(invoices.mapped('residual'))
                    else:
                        bal = sum(invoices.mapped('amount_total'))
                    bal += self.env['partner.ledger.customer'].search(
                        [('partner_id', '=', line.partner_id.id), ('description', '=', 'Opening Balance')]).balance
                    bal_ref = self.env['partner.ledger.customer'].search(
                        [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])

                    if bal_ref:
                        bal = self.env['partner.ledger.customer'].search(
                        [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])[
                        -1].balance

                    self.env['partner.ledger.customer'].sudo().create({
                        'date': datetime.today().date(),
                        # 'invoice_id': inv.id,
                        'description': 'Cash',
                        'partner_id': line.partner_id.id,
                        'company_id': 1,
                        'account_journal': line.journal_id.id,
                        'account_move': line.payments.mapped('move_line_ids').mapped('move_id')[0].id,
                        'credit': line.amount_total,
                        'balance': bal - line.amount_total,
                    })
            else:
                if not account:
                    actual = amount

                j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

                pay_id = self.env['account.payment'].create({'partner_id': line.partner_id.id,
                                                             # 'amount': check_inv.amount_total,
                                                             'amount': actual,
                                                             'partner_type': self.partner_type,
                                                             'company_id': self.env.user.company_id.id,
                                                             'payment_type': self.payment_type,
                                                             'payment_method_id': self.payment_method_id.id,
                                                             # 'journal_id': line.journal_id.id,
                                                             'journal_id': line.journal_id.id,
                                                             'communication': 'Cash Collection',
                                                             # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                             })
                pay_id.post()
                pay_id.action_cash_book()
                product_line = (0, 0, {
                    'date': self.payment_date,
                    'name': self.display_name,
                    'partner_id': line.partner_id.id,
                    'ref': self.name,
                    'amount': actual
                })
                payment_list.append(product_line)

                for k in pay_id.move_line_ids:
                    pay_id_list.append(k.id)
                line.payments += pay_id
                invoices = self.env['account.invoice'].search(
                    [('partner_id', '=', line.partner_id.id),
                     ('company_id', '=', self.env.user.company_id.id), ('state', '!=', 'paid')])
                if invoices:
                    if invoices.mapped('residual'):
                        bal = sum(invoices.mapped('residual'))
                    else:
                        bal = sum(invoices.mapped('amount_total'))
                bal += self.env['partner.ledger.customer'].search(
                    [('partner_id', '=', line.partner_id.id), ('description', '=', 'Opening Balance')]).balance
                bal_ref = self.env['partner.ledger.customer'].search(
                    [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])

                if bal_ref:
                    bal = self.env['partner.ledger.customer'].search(
                        [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])[
                        -1].balance

                self.env['partner.ledger.customer'].sudo().create({
                    'date': datetime.today().date(),
                    # 'invoice_id': inv.id,
                    'description': 'Cash',
                    'partner_id': line.partner_id.id,
                    'company_id': 1,
                    'account_journal': line.journal_id.id,
                    'account_move': line.payments.mapped('move_line_ids').mapped('move_id')[0].id,
                    'credit': line.amount_total,
                    'balance': bal - line.amount_total,
                })

        if stmt:
            stmt.line_ids = payment_list
            stmt.move_line_ids = pay_id_list
            stmt.write({'state': 'confirm'})
            self.write({'state': 'validate'})

        self.action_accountant_record()
    def action_reverse(self):
        self.write({'state':'reverse'})
        for line in self.partner_invoices.filtered(lambda a:a.reverse == True):
            stmt = self.env['account.bank.statement']
            if line.amount_total == 0.0:
                raise UserError(_("Please mention paid amount for this partner %s ") % (line.partner_id.name))
            cv = 0
            if line.check_type == 'cheque':
                journal = self.env['account.journal'].search(
                    [('name', '=', 'Bank'), ('company_id', '=', self.env.user.company_id.id)])
            else:
                journal = line.journal_id.id
            if not stmt:
                # _get_payment_info_JSON
                # bal = sum(self.env['account.move.line'].search([('journal_id', '=', line.journal_id.id)]).mapped(
                #     'debit'))

                if self.env['account.bank.statement'].search([('company_id', '=', line.journal_id.company_id.id),
                                                              ('journal_id', '=', line.journal_id.id)]):
                    bal = self.env['account.bank.statement'].search(
                        [('company_id', '=', line.journal_id.company_id.id),
                         ('journal_id', '=', line.journal_id.id)])[0].balance_end_real
                else:
                    bal = 0

                stmt = self.env['account.bank.statement'].create({'name': line.partner_id.name,
                                                                  'balance_start': bal,
                                                                  # 'journal_id': line.journal_id.id,
                                                                  'journal_id': line.journal_id.id,
                                                                  'balance_end_real': bal-line.amount_total

                                                                  })

            payment_list = []
            pay_id_list = []
            account = self.env['account.invoice'].search(
                [('partner_id', '=', line.partner_id.id),('company_id','=',line.journal_id.company_id.id),('state', '=', 'open')])
            amount = line.amount_total
            actual = 0
            if account:
               for check_inv in account:
                if amount:
                    if check_inv.amount_total >= amount:
                        actual = amount

                        product_line = (0, 0, {
                            'date': line.date,
                            'name': check_inv.display_name,
                            'partner_id': line.partner_id.id,
                            'ref': check_inv.display_name,
                            'amount': -amount
                        })
                        amount = amount - amount
                        payment_list.append(product_line)
                    else:
                        if check_inv.amount_total != 0:
                            amount = amount - check_inv.amount_total
                            actual = check_inv.amount_total
                            product_line = (0, 0, {
                                'date': line.date,
                                'name': check_inv.display_name,
                                'partner_id': line.partner_id.id,
                                'ref': check_inv.display_name,
                                'amount': -check_inv.amount_total
                            })
                            payment_list.append(product_line)

                    j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]
                    pay_id = self.env['account.payment'].create({'partner_id': line.partner_id.id,
                                                                 # 'amount': check_inv.amount_total,
                                                                 'amount': actual,
                                                                 # 'partner_type': self.partner_type,
                                                                 'company_id': self.env.user.company_id.id,
                                                                   'partner_type': 'supplier',
                                                                 'payment_type': 'outbound',
                                                                 'payment_method_id': self.payment_method_id.id,
                                                                 # 'journal_id': line.journal_id.id,
                                                                 'journal_id': line.journal_id.id,
                                                                 'communication': 'Reverse Cash Collection',
                                                                 'invoice_ids': [(6, 0, check_inv.ids)]
                                                                 })
                    pay_id.action_validate_invoice_payment()
                    pay_id.action_cash_book()
                    for k in pay_id.move_line_ids:
                        pay_id_list.append(k.id)
                    line.payments += pay_id
                    invoices = self.env['account.invoice'].search(
                        [('partner_id', '=', line.partner_id.id),
                         ('company_id', '=', self.env.user.company_id.id), ('state', '!=', 'paid')])
                    if invoices.mapped('residual'):
                        bal = sum(invoices.mapped('residual'))
                    else:
                        bal = sum(invoices.mapped('amount_total'))
                    bal += self.env['partner.ledger.customer'].search(
                        [('partner_id', '=', line.partner_id.id), ('description', '=', 'Opening Balance')]).balance
                    bal_ref = self.env['partner.ledger.customer'].search(
                        [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])

                    if bal_ref:
                        bal = self.env['partner.ledger.customer'].search(
                        [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])[
                        -1].balance

                    self.env['partner.ledger.customer'].sudo().create({
                        'date': datetime.today().date(),
                        # 'invoice_id': inv.id,
                        'description': 'Reverse Entry Cash',
                        'partner_id': line.partner_id.id,
                        'company_id': 1,
                        'account_journal': line.journal_id.id,
                        'account_move': line.payments.mapped('move_line_ids').mapped('move_id')[0].id,
                        'credit': 0,
                        'debit': line.amount_total,
                        'balance': bal + line.amount_total,
                    })
            else:
                if not account:
                    actual = amount

                j = self.env['account.payment.method'].search([('name', '=', 'Manual')])[0]

                pay_id = self.env['account.payment'].create({'partner_id': line.partner_id.id,
                                                             # 'amount': check_inv.amount_total,
                                                             'amount': actual,
                                                             # 'partner_type': self.partner_type,
                                                             'company_id': self.env.user.company_id.id,
                                                             # 'payment_type': self.payment_type,
                                                             'partner_type': 'supplier',
                                                             'payment_type': 'outbound',
                                                             'payment_method_id': self.payment_method_id.id,
                                                             # 'journal_id': line.journal_id.id,
                                                             'journal_id': line.journal_id.id,
                                                             'communication': 'Reverse Cash Collection',
                                                             # 'invoice_ids': [(6, 0, check_inv.ids)]
                                                             })
                pay_id.post()
                # pay_id.action_cash_book()
                pay_id.action_reverse_cash_book()
                product_line = (0, 0, {
                    'date': self.payment_date,
                    'name': self.display_name,
                    'partner_id': line.partner_id.id,
                    'ref': self.name,
                    'amount': -actual
                })
                payment_list.append(product_line)

                for k in pay_id.move_line_ids:
                    pay_id_list.append(k.id)
                line.payments += pay_id
                invoices = self.env['account.invoice'].search(
                    [('partner_id', '=', line.partner_id.id),
                     ('company_id', '=', self.env.user.company_id.id), ('state', '!=', 'paid')])
                if invoices:
                    if invoices.mapped('residual'):
                        bal = sum(invoices.mapped('residual'))
                    else:
                        bal = sum(invoices.mapped('amount_total'))
                bal += self.env['partner.ledger.customer'].search(
                    [('partner_id', '=', line.partner_id.id), ('description', '=', 'Opening Balance')]).balance
                bal_ref = self.env['partner.ledger.customer'].search(
                    [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])

                if bal_ref:
                    bal = self.env['partner.ledger.customer'].search(
                        [('company_id', '=', self.env.user.company_id.id), ('partner_id', '=', line.partner_id.id)])[
                        -1].balance

                self.env['partner.ledger.customer'].sudo().create({
                    'date': datetime.today().date(),
                    # 'invoice_id': inv.id,
                    'description': 'Reverse Entry Cash',
                    'partner_id': line.partner_id.id,
                    'company_id': 1,
                    'account_journal': line.journal_id.id,
                    'account_move': line.payments.mapped('move_line_ids').mapped('move_id')[0].id,
                    'credit': 0,
                    'debit': line.amount_total,
                    'balance': bal + line.amount_total,
                })

            if stmt:
                stmt.line_ids = payment_list
                stmt.move_line_ids = pay_id_list
                stmt.write({'state': 'confirm'})
            # self.write({'state': 'validate'})

        # self.action_accountant_record()

class ResSubPartners(models.Model):
    _inherit = "res.sub.partner"


    @api.onchange('complete_address')
    def onchange_complete_address(self):
        if self.complete_address:
            print('ffdgdfg')
            if self.sub_partner:
                self.partner.partner.write({'complete_address' : self.complete_address})
                # print(self.partner.partner.complete_address,'dfdfd')



class EstimateOrders(models.Model):
    _inherit = 'estimate.orders'
    _order = 'id desc'

    estimate_user_id = fields.Many2one('res.users', string='Sales Person')


    def action_oder_confirm(self):
        res = super(EstimateOrders, self).action_oder_confirm()
        estimate = self.env['sale.estimate'].search([('est_order_id', '=', self.id)])
        if estimate:
            estimate.estimate_order_shop = self.estimate_order_shop
            estimate.estimate_user_id = False
        return res


class SaleEstimate(models.Model):
    _inherit = 'sale.estimate'


    def total_sales_create(self):
        res = super(SaleEstimate, self).total_sales_create()
        if self.est_order_id:
            print('vfdgfdgfdgf,yessss')
            self.est_order_id.write({'estimate_user_id': self.env.user.id})
        return res




class TodayChequeLines(models.Model):
    _inherit = "today.cheques.line"

    debited_account = fields.Many2one('account.journal', string='Debit A/C',required=False)
    debit_mandory = fields.Boolean(default=False)


    # @api.onchange('debit_mandory')
    # def onchange_debit_mandory(self):
    #     if self.debit_mandory == True:
    #         self.debit_mandory

class TodayCheques(models.Model):
    _inherit = "today.cheques"

    def complete_submission_rec(self):
        for line in self.today_lines:
            before_rec = self.env['cheque.submission'].search(
                [('partner_id', '=', line.partner_id.id), ('check_no', '=', line.check_no)])
            if before_rec:
                if line.status == "deposit":
                    before_rec[0].clearing_date = line[0].clearing_date
                if line.status :
                    before_rec[0].status = line.status
                    before_rec[0].type_state = line.status
            sales_person = self.env['res.users']
            check_line = self.env['executive.cheque.collection.line']
            advance_check_line = self.env['advance.cheque.collection.line']
            if self.sales_person:
                sales_person = self.sales_person.id
            if line.check_line:
                check_line = line.check_line.id
            if line.advance_check_line:
                advance_check_line = line.advance_check_line.id
            if not before_rec :
                if line.debit_mandory:
                    self.env['cheque.submission'].create({
                        'type_state': line.status,
                        'submitted_date': line.submitted_date,
                        'from_date': self.from_date,
                        'to_date': self.to_date,
                        'date': line.clearing_date,
                        'sales_person': sales_person,
                        'partner_id': line.partner_id.id,
                        'check_line': check_line,
                        'advance_check_line': advance_check_line,
                        'balance_amount': line.balance_amount,
                        'amount_total': line.amount_total,
                        'ref_id': line.ref_id.id,
                        # 'journal_id':line.journal_id.id,
                        'check_no': line.check_no,
                        'check_type': line.check_type,
                        'check_manual_date': line.check_manual_date,
                        'bank_name': line.bank_name,
                        'status': line.status,
                        'state': line.state,
                        'holder_name': line.holder_name.id,
                        'debited_account': line.debited_account.id,
                        'account_id': line.account_id.id,
                        # 'collected_cheque':line.collected_cheque.id,
                    })

class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    balance_invoice_qty = fields.Integer(string="Balance Invoice Qty")




    def action_invoice_brothers_cancel(self):
        print('sdfdsf')
        view_id = self.env.ref('enz_multi_updations.sales_sales_invoice_cancel')
        return {
            'name': _('Invoice Cancel'),
            'type': 'ir.actions.act_window',
            'res_model': 'sales.invoice.cancel',
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'current',
            'view_id': view_id.id,
            'views': [(view_id.id, 'form')],
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_invoice_id': self.id,

            }
        }




    @api.multi
    def _compute_inv_mc_qty(self):
        for each_inv in self:
            each_inv.inv_mc_qty = sum(each_inv.invoice_line_ids.filtered(lambda a:a.is_rounding_line != True).mapped('quantity'))



class SalesInvoiceCancel(models.Model):
    _name = 'sales.invoice.cancel'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, default='New', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer',domain=['|',('estimator','=',True),('is_subc','=',True)])
    invoice_id = fields.Many2one('account.invoice')
    state = fields.Selection(
        [('draft', 'Draft'),
         ('done', 'Done'),
         ('cancel', 'Cancel')
         ],default='draft')
    sales_return_lines = fields.One2many('sales.invoice.cancel.lines', 'return_id')
    branch_id = fields.Many2one('company.branches', string='Branch')
    company_id = fields.Many2one('res.company',string='Company')
    create_date = fields.Date(string='Date')
    vehicle = fields.Char('Vehicle No')
    amount_total = fields.Monetary(string='Total Amount', compute='_compute_amount', currency_field='company_currency_id', )
    tax_amount = fields.Monetary(string='Tax Amount', compute='_compute_tax_amount', currency_field='company_currency_id', )
    grand_amount = fields.Monetary(string='Grand Total', compute='_compute_grand_amount', currency_field='company_currency_id', )
    company_currency_id = fields.Many2one('res.currency', string="Company Currency",default=lambda self: self.env.user.company_id.currency_id,
                                          store=True)
    user_id = fields.Many2one('res.users', 'Users',  index=True, ondelete='cascade',default=lambda self: self.env.user)
    vat = fields.Char('GSTIN')
    complete_address = fields.Text('Complete Address')
    new_invoices = fields.Many2one('account.invoice',string='Invoices')
    new_invoices_count = fields.Integer(string='Invoices', compute='_compute_invoices_count')


    @api.model
    def create(self, vals):
        if not vals.get('name') or vals['name'] == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('sales.invoice.cancel') or _('New')
        return super(SalesInvoiceCancel, self).create(vals)

    @api.depends('new_invoices')
    def _compute_invoices_count(self):
         for each in self:
             each.new_invoices_count = len(each.new_invoices)

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if self.partner_id:
            moves = self.env['account.invoice'].search([('partner_id','=',self.partner_id.id),('state','not in',('cancel','done'))])
            return {'domain': {'invoice_id': [('id', 'in', moves.ids)]}}

    @api.onchange('complete_address')
    def onchange_complete_address(self):
        if self.complete_address:
            if self.partner_id:
                self.partner_id.complete_address = self.complete_address
    @api.onchange('vat')
    def onchange_vat(self):
        if self.vat:
            if self.partner_id:
                self.partner_id.vat = self.vat

    @api.onchange('invoice_id')
    def onchange_invoice_id(self):
        if self.invoice_id:
            self.company_id = self.invoice_id.company_id
            self.branch_id = self.invoice_id.branch_id
            self.vehicle = self.invoice_id.vehicle
            list_of_lines = []
            for line in self.invoice_id.invoice_line_ids:
                quantity = 0
                if self.invoice_id.balance_invoice_qty:
                    quantity = self.invoice_id.balance_invoice_qty
                else:
                    quantity = line.quantity
                if line.product_id:
                    dict = (0,0,{
                        'product_id':line.product_id.id,
                        # 'product_uom_qty':line.quantity,
                        'product_uom_qty':quantity,
                        'price_unit':line.price_unit,
                        'est_line_id':self.invoice_id.est_line_id.id,
                        'invoice_line_ids':line.id,
                        'tax_ids': [(6, 0, line.invoice_line_tax_ids.ids)],
                    })
                    list_of_lines.append(dict)
            self.sales_return_lines = list_of_lines

    @api.depends('sales_return_lines')
    def _compute_amount(self):
        for l in self:
            l.amount_total = sum(l.sales_return_lines.filtered(lambda a:a.product_id != False).mapped('sub_total'))

    @api.depends('sales_return_lines')
    def _compute_grand_amount(self):
        for each in self:
            each.grand_amount = each.amount_total + each.tax_amount

    @api.depends('sales_return_lines')
    def _compute_tax_amount(self):
        for l in self:
            for line in l.sales_return_lines:
                if line.product_id:
                    actual = line.sub_total
                    for tax in line.tax_ids:
                        tax_value_system = actual * sum(tax.children_tax_ids.mapped('amount')) / 100
                        l.tax_amount += tax_value_system

    def action_cancel_create(self):
            if self.invoice_id:
                self.invoice_id.sudo().write({'state':'cancel'})

            ledger_invoices = self.env['partner.ledger.customer'].sudo().search([('invoice_id','=',self.invoice_id.id),('company_id','=',self.invoice_id.company_id.id)])
            if ledger_invoices:
                for each_ledger in ledger_invoices:
                    each_ledger.unlink()

            # override the context to get rid of the default filtering
            product_list = []
            for line in self.sales_return_lines:
                line_dict = (0,0,{
                    'name': line.product_id.name,
                    'account_id': self.invoice_id.account_id.id,
                    'price_unit': line.price_unit,
                    'quantity': line.product_uom_qty,
                    # 'discount': 0.0,
                    'uom_id': line.product_id.uom_id.id,
                    'product_id': line.product_id.id,
                    'invoice_line_tax_ids': [(6, 0, line.tax_ids.ids)]})
                product_list.append(line_dict)

            new_inv = self.env['account.invoice'].create({
                'type': 'out_invoice',
                'partner_id': self.partner_id.id,
                'currency_id': self.invoice_id.currency_id.id,
                'company_id': self.invoice_id.company_id.id,
                'branch_id': self.branch_id.id,
                'est_line_id': self.sales_return_lines[0].est_line_id.id,
                'invoice_line_ids':product_list,
                'origin': self.name})
            new_inv.write({'estimate_id': self.invoice_id.estimate_id.id})
            new_inv.remarks = self.invoice_id.remarks
            new_inv.b2b_company_name = self.partner_id.b2b_company_name
            new_inv.site = self.partner_id.site
            new_inv.complete_address = self.complete_address
            new_inv.vehicle = self.vehicle
            if not self.invoice_id.balance_invoice_qty:
                self.invoice_id.balance_invoice_qty = sum(self.invoice_id.mapped('invoice_line_ids').filtered(lambda a:a.is_rounding_line != True).mapped('quantity')) - sum(new_inv.mapped('invoice_line_ids').filtered(lambda a:a.is_rounding_line != True).mapped('quantity'))
            else:
                self.invoice_id.balance_invoice_qty = self.invoice_id.balance_invoice_qty-sum(new_inv.mapped('invoice_line_ids').filtered(lambda a:a.is_rounding_line != True).mapped('quantity'))
            if new_inv.amount_total > round(new_inv.amount_total):
                rounding_line = self.env['account.invoice.line'].create({
                    'name': 'Rounding 0.05',
                    'invoice_id': new_inv.id,
                    'account_id': self.env['account.cash.rounding'].search(
                        [('name', '=', 'Rounding 0.05')]).account_id.id,
                    'price_unit': -(new_inv.amount_total - round(new_inv.amount_total)),
                    'quantity': 1,
                    'is_rounding_line': True,
                    'sequence': 9999  # always last line
                })
            else:
                if new_inv.amount_total < round(new_inv.amount_total):
                    rounding_line = self.env['account.invoice.line'].create({
                        'name': 'Rounding 0.05 Up',
                        'invoice_id': new_inv.id,
                        'account_id': self.env['account.cash.rounding'].search(
                            [('name', '=', 'Rounding up 0.05')]).account_id.id,
                        'price_unit': round(new_inv.amount_total) - new_inv.amount_total,
                        'quantity': 1,
                        'is_rounding_line': True,
                        'sequence': 9999  # always last line
                    })

            new_inv.action_invoice_open()
            self.new_invoices = new_inv

            for inv_line in new_inv.invoice_line_ids.filtered(lambda a:a.is_rounding_line != True):

                invoices = self.env['account.invoice'].sudo().search(
                    [('partner_id', '=', new_inv.partner_id.id), ('company_id', '=', new_inv.company_id.id),
                     ('state', '!=', 'paid')])
                if invoices.mapped('residual'):
                    balance_amount = sum(invoices.mapped('residual'))
                else:
                    balance_amount = sum(invoices.mapped('amount_total'))
                balance_amount += self.env['partner.ledger.customer'].sudo().search(
                    [('partner_id', '=', new_inv.partner_id.id), ('description', '=', 'Opening Balance')]).balance
                Previous_led = self.env['partner.ledger.customer'].sudo().search(
                    [('company_id', '=', new_inv.company_id.id), ('partner_id', '=', new_inv.partner_id.id)])
                if Previous_led:
                    balance_amount = Previous_led[-1].balance + inv_line.price_subtotal_signed + new_inv.amount_tax

                # bal = sum(
                #     self.env['account.move.line'].search([('journal_id', '=', self.account_journal.id)]).mapped('debit'))

                self.env['partner.ledger.customer'].sudo().create({
                    'date': datetime.today().date(),
                    'invoice_id': new_inv.id,
                    'description': inv_line.product_id.name,
                    'partner_id': new_inv.partner_id.id,
                    'product_id': inv_line.product_id.id,
                    'company_id': new_inv.company_id.id,
                    'price_units': new_inv.inv_mc_qty,
                    'uom': inv_line.uom_id.id,
                    'rate': inv_line.price_unit,
                    'estimate_id': self.invoice_id.estimate_id.id,
                    'account_journal': new_inv.journal_id.id,
                    'account_move': new_inv.move_id.id,
                    # 'credit': inv.amount_total_signed,
                    'debit': inv_line.price_subtotal_signed + new_inv.amount_tax,
                    # 'balance': 0,
                    'executive_area': self.invoice_id.estimate_id.executive_areas.id or False,
                    'area': self.invoice_id.estimate_id.area.id or False,
                    'vehicle_id': self.invoice_id.estimate_id.estimate_ids[0].vahicle.id,
                    'balance': balance_amount,
                })
                # self.env['owner.application'].create({
                #     'create_date': self.c_date,
                #     'partner_id': new_inv.partner_id.id,
                #     'product_id': line.product_id.id,
                #     'quantity': new_inv.inv_mc_qty,
                #     'company_id': new_inv.company_id.id,
                #     'type': self.estimtype,
                #     'area': self.invoice_id.estimate_id.area.id or False,
                #     'outstanding_amount': balance_amount,
                #     'sales_executive': self.user_id.partner_id.id
                # })
            self.write({'state':'done'})
    @api.multi
    def action_view_invoices(self):
        action = {
            'name': _('Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.invoice',
            'target': 'current',
        }
        invoice_ids = self.new_invoices.ids
        if len(invoice_ids) == 1:
            invoice = invoice_ids[0]
            action['res_id'] = invoice
            action['view_mode'] = 'form'
            form_view = [(self.env.ref('account.invoice_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
        else:
            action['view_mode'] = 'tree,form'
            action['domain'] = [('id', 'in', invoice_ids)]
        return action



class SalesInvoiceCancelLines(models.Model):
    _name = 'sales.invoice.cancel.lines'

    product_id = fields.Many2one('product.product', string='Product Name')
    return_id = fields.Many2one('sales.invoice.cancel')
    product_uom_qty = fields.Float('Quantity')
    price_unit = fields.Float('Price Unit')
    est_line_id = fields.Many2one('sale.estimate.lines',string='line Name')
    invoice_line_ids = fields.Many2one('account.invoice.line')
    sub_total = fields.Float(string='Subtotal',compute='_compute_sub_total')
    tax_ids = fields.Many2many(
        comodel_name='account.tax',
        string="Taxes",
        help="Taxes that apply on the base amount")


    @api.depends('price_unit','product_uom_qty')
    def _compute_sub_total(self):
       for each in self:
            each.sub_total = each.product_uom_qty * each.price_unit


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'



    def automatic_bill_creation(self):
        if self.picking_ids.state == 'done':

            create_bill = self.env.context.get('create_bill', False)
            account_id = self.env['account.account'].search(
                [('name', '=', 'Purchase Expense'), ('company_id', '=', self.env.user.company_id.id)])
            # override the context to get rid of the default filtering
            po = self
            new_inv = self.env['account.invoice'].create({
                'type': 'in_invoice',
                # 'invoiced_number':po.invoiced_number,
                # 'invoiced_date':po.invoiced_date,
                # 'purchase_date':po.purchase_date,
                # 'vehicle_no':po.vehicle_no,
                'partner_id': po.partner_id.id,
                'purchase_id': po.id,
                'currency_id': po.currency_id.id,
                'company_id': po.company_id.id,
                'origin': po.name,
                # 'tax_line_ids':po_line.taxes_id.ids
            })

            for po_line in self.order_line:
                new_line = self.env['account.invoice.line'].create({
                    'name': po_line.name,
                    'origin': po.name,
                    'account_id': account_id.id,
                    'price_unit': po_line.price_unit,
                    'quantity': po_line.product_uom_qty,
                    'discount': 0.0,
                    'uom_id': po_line.product_id.uom_id.id,
                    'product_id': po_line.product_id.id,
                    'invoice_id': new_inv.id,
                    'invoice_line_tax_ids': [(6, 0, po_line.taxes_id.ids)]})
                po_line.invoice_lines = new_line
            new_inv.compute_taxes()
            if new_inv.amount_total > round(new_inv.amount_total):
                rounding_line = self.env['account.invoice.line'].create({
                    'name': 'Rounding 0.05',
                    'invoice_id': new_inv.id,
                    'account_id': self.env['account.cash.rounding'].search(
                        [('name', '=', 'Rounding 0.05')]).account_id.id,
                    'price_unit': -(new_inv.amount_total - round(new_inv.amount_total)),
                    'quantity': 1,
                    'is_rounding_line': True,
                    'sequence': 9999  # always last line
                })
            else:
                if new_inv.amount_total < round(new_inv.amount_total):
                    rounding_line = self.env['account.invoice.line'].create({
                        'name': 'Rounding 0.05 Up',
                        'invoice_id': new_inv.id,
                        'account_id': self.env['account.cash.rounding'].search(
                            [('name', '=', 'Rounding up 0.05')]).account_id.id,
                        'price_unit': round(new_inv.amount_total) - new_inv.amount_total,
                        'quantity': 1,
                        'is_rounding_line': True,
                        'sequence': 9999  # always last line
                    })

            # new_inv.action_invoice_open()

class ExecutiveCollectionLines(models.Model):
    _inherit = "executive.collection.line"

    reverse = fields.Boolean(string='Reverse')
    ar_amount_total = fields.Char(string="Amount Total")



    @api.onchange('ar_amount_total')
    def onchange_ar_amount_total(self):
        self.amount_total = self.ar_amount_total




class SalesExecutiveCheque(models.Model):
    _inherit = "executive.cheque.collection"

    sum_amount = fields.Float(compute='compute_sum_amount',string='Amount Total')


    def compute_sum_amount(self):
        for e in self:
            e.sum_amount = sum(e.partner_invoices.mapped('amount_total'))





class EstimateOrdersLines(models.Model):
    _inherit = 'estimate.orders.line'



    char_quantity = fields.Char(string='Quantity')
    # quantity = fields.Float(default=0.0, string='Quantity')
    char_price = fields.Char(string='Price')
    # price = fields.Float(default=0.0, string='Price')

    @api.onchange('char_quantity')
    def onchange_char_quantity(self):
        self.quantity = self.char_quantity

    @api.onchange('char_price')
    def onchange_char_price(self):
        self.price = self.char_price



class ExecutiveChequeCollectionLines(models.Model):
    _inherit = "executive.cheque.collection.line"

    char_amount_total = fields.Char(string="Paid Amount")


    @api.onchange('char_amount_total')
    def onchange_char_amount_total(self):
        self.amount_total = self.char_amount_total







