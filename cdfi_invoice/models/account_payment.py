# -*- coding: utf-8 -*-

import base64
import json
import requests
from lxml import etree
from odoo import api, fields, models, _
from odoo.exceptions import UserError, Warning
from . import amount_to_text_es_MX
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.units import mm
from datetime import datetime
import pytz
from .tzlocal import get_localzone
import os
import logging
_logger = logging.getLogger(__name__)

class AccountRegisterPayment(models.TransientModel):
    _inherit = 'account.payment.register'
    
    def validate_complete_payment(self):
        for rec in self:
            rec.action_create_payments()
            return {
               'name': _('Payments'),
               'view_type': 'form',
               'view_mode': 'form',
               'res_model': 'account.payment',
               'view_id': False,
               'type': 'ir.actions.act_window',
               'res_id': rec.id,
           }

    def _create_payment_vals_from_wizard(self):
        res = super(AccountRegisterPayment, self)._create_payment_vals_from_wizard()
        res.update({'fecha_pago': self.payment_date})
        return res


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    forma_pago = fields.Selection(selection=[('01', '01 - Efectivo'), 
                   ('02', '02 - Cheque nominativo'), 
                   ('03', '03 - Transferencia electrónica de fondos'),
                   ('04', '04 - Tarjeta de Crédito'), 
                   ('05', '05 - Monedero electrónico'),
                   ('06', '06 - Dinero electrónico'), 
                   ('08', '08 - Vales de despensa'), 
                   ('12', '12 - Dación en pago'), 
                   ('13', '13 - Pago por subrogación'), 
                   ('14', '14 - Pago por consignación'), 
                   ('15', '15 - Condonación'), 
                   ('17', '17 - Compensación'), 
                   ('23', '23 - Novación'), 
                   ('24', '24 - Confusión'), 
                   ('25', '25 - Remisión de deuda'), 
                   ('26', '26 - Prescripción o caducidad'), 
                   ('27', '27 - A satisfacción del acreedor'), 
                   ('28', '28 - Tarjeta de débito'), 
                   ('29', '29 - Tarjeta de servicios'), 
                   ('30', '30 - Aplicación de anticipos'),
                   ('31', '31 - Intermediario pagos'), ],
                                string=_('Forma de pago'), 
                            )
    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),
                   ('PPD', _('Pago en parcialidades o diferido')),],
        string=_('Método de pago'), 
    )
#    no_de_pago = fields.Integer("No. de pago", readonly=True)
    saldo_pendiente = fields.Float("Saldo pendiente", readonly=True)
    monto_pagar = fields.Float("Monto a pagar", compute='_compute_monto_pagar')
    saldo_restante = fields.Float("Saldo restante", readonly=True)
    fecha_pago = fields.Datetime("Fecha de pago")
    cuenta_emisor = fields.Many2one('res.partner.bank', string=_('Cuenta del emisor'))
    banco_emisor = fields.Char("Banco del emisor", related='cuenta_emisor.bank_name', readonly=True)
    rfc_banco_emisor = fields.Char(_("RFC banco emisor"), related='cuenta_emisor.bank_bic', readonly=True)
    numero_operacion = fields.Char(_("Número de operación"))
    banco_receptor = fields.Char(_("Banco receptor"), compute='_compute_banco_receptor')
    cuenta_beneficiario = fields.Char(_("Cuenta beneficiario"), compute='_compute_banco_receptor')
    rfc_banco_receptor = fields.Char(_("RFC banco receptor"), compute='_compute_banco_receptor')
    estado_pago = fields.Selection(
        selection=[('pago_no_enviado', 'REP no generado'), ('pago_correcto', 'REP correcto'), 
                   ('problemas_factura', 'Problemas con el pago'), ('solicitud_cancelar', 'Cancelación en proceso'),
                   ('cancelar_rechazo', 'Cancelación rechazada'), ('factura_cancelada', 'REP cancelado'), ],
        string=_('Estado CFDI'),
        default='pago_no_enviado',
        readonly=True
    )
    tipo_relacion = fields.Selection(
        selection=[('04', 'Sustitución de los CFDI previos'),],
        string=_('Tipo relación'),
    )
    uuid_relacionado = fields.Char(string=_('CFDI Relacionado'))
    confirmacion = fields.Char(string=_('Confirmación'))
    folio_fiscal = fields.Char(string=_('Folio Fiscal'), readonly=True)
    numero_cetificado = fields.Char(string=_('Numero de certificado'))
    cetificaso_sat = fields.Char(string=_('Cetificado SAT'))
    fecha_certificacion = fields.Char(string=_('Fecha y Hora Certificación'))
    cadena_origenal = fields.Char(string=_('Cadena Original del Complemento digital de SAT'))
    selo_digital_cdfi = fields.Char(string=_('Sello Digital del CDFI'))
    selo_sat = fields.Char(string=_('Sello del SAT'))
 #   moneda = fields.Char(string=_('Moneda'))
    monedap = fields.Char(string=_('Moneda'))
#    tipocambio = fields.Char(string=_('TipoCambio'))
    tipocambiop = fields.Char(string=_('TipoCambio'))
    folio = fields.Char(string=_('Folio'))
    version = fields.Char(string=_('Version'))
    number_folio = fields.Char(string=_('Folio'), compute='_get_number_folio')
    amount_to_text = fields.Char('Amount to Text', compute='_get_amount_to_text',
                                 size=256, 
                                 help='Amount of the invoice in letter')
    qr_value = fields.Char(string=_('QR Code Value'))
    qrcode_image = fields.Binary("QRCode")
    rfc_emisor = fields.Char(string=_('RFC'))
    name_emisor = fields.Char(string=_('Name'))
    xml_payment_link = fields.Char(string=_('XML link'), readonly=True)
    payment_mail_ids = fields.One2many('account.payment.mail', 'payment_id', string='Payment Mails')
    iddocumento = fields.Char(string=_('iddocumento'))
    fecha_emision = fields.Char(string=_('Fecha y Hora Certificación'))
    docto_relacionados = fields.Text("Docto relacionados",default='[]')
    cep_sello = fields.Char(string=_('cep_sello'))
    cep_numeroCertificado = fields.Char(string=_('cep_numeroCertificado'))
    cep_cadenaCDA = fields.Char(string=_('cep_cadenaCDA'))
    cep_claveSPEI = fields.Char(string=_('cep_claveSPEI'))
    
    @api.depends('name')
    def _get_number_folio(self):
        for record in self:
            if record.number:
                record.number_folio = record.name.replace('CUST.IN','').replace('/','')

    @api.model
    def get_docto_relacionados(self,payment):
        try:
            data = json.loads(payment.docto_relacionados)
        except Exception:
            data = []
        return data
    
    
    def importar_incluir_cep(self):
        ctx = {'default_payment_id':self.id}
        return {
            'name': _('Importar factura de compra'),
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('cdfi_invoice.view_import_xml_payment_in_payment_form_view').id,
            'res_model': 'import.account.payment.from.xml',
            'context': ctx,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
        
    @api.onchange('journal_id')
    def _onchange_journal(self):
        if self.journal_id:
            self.currency_id = self.journal_id.currency_id or self.company_id.currency_id
            # Set default payment method (we consider the first to be the default one)
            payment_methods = self.payment_type == 'inbound' and self.journal_id.inbound_payment_method_ids or self.journal_id.outbound_payment_method_ids
            self.payment_method_id = payment_methods and payment_methods[0] or False
            # Set payment method domain (restrict to methods enabled for the journal and to selected payment type)
            payment_type = self.payment_type in ('outbound', 'transfer') and 'outbound' or 'inbound'
            self.forma_pago = self.journal_id.forma_pago
            return {'domain': {'payment_method_id': [('payment_type', '=', payment_type), ('id', 'in', payment_methods.ids)]}}
        return {}
    
#     @api.onchange('payment_date')
#     def _onchange_payment_date(self):
#         if self.payment_date:
#             self.fecha_pago = datetime.combine((self.payment_date), datetime.max.time())

    
    def add_resitual_amounts(self):
        if self.reconciled_invoice_ids and self.docto_relacionados != '[]':
            for invoice in self.reconciled_invoice_ids:
                data = json.loads(self.docto_relacionados) or []
                for line in data:
                    if invoice.folio_fiscal == line.get('iddocumento',False):
                        monto_restante = invoice.amount_residual
                        monto_pagar_docto = float(line.get('saldo_pendiente',False)) - monto_restante
                        line['monto_pagar'] = monto_pagar_docto
                        line['saldo_restante'] = monto_restante
                        self.write({'docto_relacionados': json.dumps(data)})
        elif self.reconciled_invoice_ids and self.docto_relacionados == '[]':
           # _logger.info('entra2 01')
           # if self.docto_relacionados == '[]': #si está vacio
               docto_relacionados = []
               monto_pagado_asignar = round(self.monto_pagar,2)
               for invoice in self.reconciled_invoice_ids:
                    if invoice.factura_cfdi:
                        #revisa la cantidad que se va a pagar en el docuemnto
                        if self.currency_id.name != invoice.moneda:
                            if self.currency_id.name == 'MXN':
                                tipocambiop = round(invoice.currency_id.with_context(date=self.date).rate,6) + 0.000001
                            else:
                                tipocambiop = float(invoice.tipocambio)/float(self.currency_id.rate)
                        else:
                            tipocambiop = invoice.tipocambio

                        payment_dict = json.loads(invoice.invoice_payments_widget)
                        payment_content = payment_dict['content']
                        monto_pagado = 0
                        for invoice_payments in payment_content:
                            if invoice_payments['account_payment_id'] == self.id:
                                _logger.info('contenido %s cuantos hay %s', payment_content, len(payment_content))
                                monto_pagado = invoice_payments['amount']
                        docto_relacionados.append({
                              'moneda': invoice.moneda,
                              'tipodecambio': tipocambiop,
                              'methodo_pago': invoice.methodo_pago,
                              'iddocumento': invoice.folio_fiscal,
                              'folio_facura': invoice.number_folio,
                              'no_de_pago': len(payment_content), 
                              'saldo_pendiente': round(invoice.amount_residual + monto_pagado,2),
                              'monto_pagar': monto_pagado,
                              'saldo_restante': invoice.amount_residual,
                        })
               saldo_pendiente_total = sum(inv.amount_residual for inv in self.reconciled_invoice_ids)
               self.write({'docto_relacionados': json.dumps(docto_relacionados),
                           'saldo_pendiente': saldo_pendiente_total, 'saldo_restante':saldo_pendiente_total - monto_pagado_asignar})


    @api.model
    def create(self, vals):
        res = super(AccountPayment, self).create(vals)
        if res.reconciled_invoice_ids:
            docto_relacionados = []
            monto_pagado_asignar = round(res.monto_pagar,2)
            for invoice in res.reconciled_invoice_ids:
                if invoice.factura_cfdi:
                    #revisa la cantidad que se va a pagar en el docuemnto
                    if res.currency_id.name != invoice.moneda:
                        if res.currency_id.name == 'MXN':
                            tipocambiop = round(invoice.currency_id.with_context(date=res.date).rate,6) + 0.000001
                        else:
                            tipocambiop = float(invoice.tipocambio)/float(res.currency_id.with_context(date=res.date).rate)
                    else:
                        tipocambiop = invoice.tipocambio
                    nbr_payment = 0
                    pay_term_line_ids = invoice.line_ids.filtered(lambda line: line.account_id.user_type_id.type in ('receivable', 'payable'))
                    partials = pay_term_line_ids.mapped('matched_debit_ids') + pay_term_line_ids.mapped('matched_credit_ids')
                    for partial in partials:
                        counterpart_lines = partial.debit_move_id + partial.credit_move_id
                        counterpart_line = counterpart_lines.filtered(lambda line: line not in invoice.line_ids)
                        if counterpart_line:
                            nbr_payment += 1
                        
                    docto_relacionados.append({
                          'moneda': invoice.moneda,
                          'tipodecambio': tipocambiop,
                          'methodo_pago': invoice.methodo_pago,
                          'iddocumento': invoice.folio_fiscal,
                          'folio_facura': invoice.number_folio,
                          'no_de_pago': nbr_payment+1, #len(invoice.payment_id.filtered(lambda x: x.state!='cancel')), 
                          'saldo_pendiente': round(invoice.amount_residual,2),
                          'monto_pagar': 0,
                          'saldo_restante': 0,
                    })
            saldo_pendiente_total = sum(inv.amount_residual for inv in res.reconciled_invoice_ids)
            res.write({'docto_relacionados': json.dumps(docto_relacionados),
                       'saldo_pendiente': saldo_pendiente_total, 'saldo_restante':saldo_pendiente_total - monto_pagado_asignar})
        return res
    
    def post(self):
        res = super(AccountPayment, self).post()
        for rec in self:
            rec.add_resitual_amounts()
            #rec._onchange_payment_date()
            rec._onchange_journal()
        return res

    @api.depends('amount')
    def _compute_monto_pagar(self):
        for record in self:
            if record.amount:
                record.monto_pagar = record.amount
            else:
                record.monto_pagar = 0

    @api.depends('journal_id')
    def _compute_banco_receptor(self):
        for record in self:
            if record.journal_id and record.journal_id.bank_id:
                record.banco_receptor = record.journal_id.bank_id.name
                record.rfc_banco_receptor = record.journal_id.bank_id.bic
            else:
                record.banco_receptor = ''
                record.rfc_banco_receptor = ''
                record.cuenta_beneficiario = ''
            if record.journal_id:
                record.cuenta_beneficiario = record.journal_id.bank_acc_number
            else:
                record.banco_receptor = ''
                record.rfc_banco_receptor = ''
                record.cuenta_beneficiario = ''

    @api.depends('amount', 'currency_id')
    def _get_amount_to_text(self):
        for record in self:
            record.amount_to_text = amount_to_text_es_MX.get_amount_to_text(record, record.amount_total, 'es_cheque', record.currency_id.name)
        
    @api.model
    def _get_amount_2_text(self, amount_total):
        return amount_to_text_es_MX.get_amount_to_text(self, amount_total, 'es_cheque', self.currency_id.name)
            
    @api.model
    def to_json(self):
        if not self.company_id.archivo_cer:
            raise UserError(_('Archivo .cer path is missing.'))
        if not self.company_id.archivo_key:
            raise UserError(_('Archivo .key path is missing.'))
        archivo_cer = self.company_id.archivo_cer
        archivo_key = self.company_id.archivo_key
        self.monedap = self.currency_id.name
        if self.currency_id.name == 'MXN':
            self.tipocambiop = '1'
        else:
            self.tipocambiop = self.currency_id.with_context(date=self.date).rate

        timezone = self._context.get('tz')
        if not timezone:
            timezone = self.env.user.partner_id.tz or 'America/Mexico_City'
        #timezone = tools.ustr(timezone).encode('utf-8')

        if not self.fecha_pago:
            raise Warning("Falta configurar fecha de pago en la sección de CFDI del documento.")
        else:
            local = pytz.timezone(timezone)
            naive_from = self.fecha_pago
            local_dt_from = naive_from.replace(tzinfo=pytz.UTC).astimezone(local)
            date_from = local_dt_from.strftime ("%Y-%m-%d %H:%M:%S")
        self.add_resitual_amounts()

        #corregir hora
        local2 = pytz.timezone(timezone)
        naive_from2 = datetime.now() 
        local_dt_from2 = naive_from2.replace(tzinfo=pytz.UTC).astimezone(local2)
        date_payment = local_dt_from2.strftime ("%Y-%m-%d %H:%M:%S")

        if self.reconciled_invoice_ids:
            request_params = { 
                'company': {
                      'rfc': self.company_id.vat,
                      'api_key': self.company_id.proveedor_timbrado,
                      'modo_prueba': self.company_id.modo_prueba,
                      'regimen_fiscal': self.company_id.regimen_fiscal,
                      'postalcode': self.company_id.zip,
                      'nombre_fiscal': self.company_id.nombre_fiscal,
                      'telefono_sms': self.company_id.telefono_sms,
                },
                'customer': {
                      'name': self.partner_id.name,
                      'rfc': self.partner_id.vat,
                      'uso_cfdi': 'P01',
                },
                'invoice': {
                      'tipo_comprobante': 'P',
                      'folio_complemento': self.name.replace('CUST.IN','').replace('/',''),
                      'serie_complemento': self.company_id.serie_complemento,
                      'fecha_factura': date_payment,
                },
                'concept': {
                      'claveprodserv': '84111506',
                      'calveunidad': 'ACT',
                      'cantidad': 1,
                      'descripcion': 'Pago',
                },
                'payment': {
                      'moneda': self.monedap,
                      'tipocambio': self.tipocambiop,
                      'forma_pago': self.forma_pago,
                      'numero_operacion': self.numero_operacion,
                      'banco_emisor': self.banco_emisor,
                      'cuenta_emisor': self.cuenta_emisor and self.cuenta_emisor.acc_number or '',
                      'rfc_banco_emisor': False, #self.rfc_banco_emisor,
                      'banco_receptor': False, #self.banco_receptor,
                      'cuenta_beneficiario': False, #self.cuenta_beneficiario,
                      'rfc_banco_receptor': False, #self.rfc_banco_receptor,
                      'fecha_pago': date_from,
                      'monto_factura':  self.amount
                },

                'docto_relacionado': json.loads(self.docto_relacionados),
                'adicional': {
                      'tipo_relacion': self.tipo_relacion,
                      'uuid_relacionado': self.uuid_relacionado,
                      'confirmacion': self.confirmacion,
                },
                'certificados': {
                      'archivo_cer': archivo_cer.decode("utf-8"),
                      'archivo_key': archivo_key.decode("utf-8"),
                      'contrasena': self.company_id.contrasena,
                },
                'version': {
                      'cfdi': '3.3',
                      'sistema': 'odoo11',
                      'version': '6',
                },
            }
        else:
            raise Warning("No tiene ninguna factura ligada al documento de pago, debe al menos tener una factura ligada. \n Desde la factura crea el pago para que se asocie la factura al pago.")
        return request_params
    
    
    def complete_payment(self):
        for p in self:
            if p.folio_fiscal:
                 p.write({'estado_pago': 'pago_correcto'})
                 return True

            values = p.to_json()
            if self.company_id.proveedor_timbrado == 'multifactura':
                url = '%s' % ('http://facturacion.itadmin.com.mx/api/payment')
            elif self.company_id.proveedor_timbrado == 'multifactura2':
                url = '%s' % ('http://facturacion2.itadmin.com.mx/api/payment')
            elif self.company_id.proveedor_timbrado == 'multifactura3':
                url = '%s' % ('http://facturacion3.itadmin.com.mx/api/payment')
            elif self.company_id.proveedor_timbrado == 'gecoerp':
                if self.company_id.modo_prueba:
                    #url = '%s' % ('https://ws.gecoerp.com/itadmin/pruebas/payment/?handler=OdooHandler33')
                    url = '%s' % ('https://itadmin.gecoerp.com/payment2/?handler=OdooHandler33')
                else:
                    url = '%s' % ('https://itadmin.gecoerp.com/payment2/?handler=OdooHandler33')
            try:
                response = requests.post(url , 
                                     auth=None,verify=False, data=json.dumps(values), 
                                     headers={"Content-type": "application/json"})
            except Exception as e:
                error = str(e)
                if "Name or service not known" in error or "Failed to establish a new connection" in error:
                     raise Warning("Servidor fuera de servicio, favor de intentar mas tarde")
                else:
                     raise Warning(error)

            #print 'Response: ', response.status_code
            json_response = response.json()
            xml_file_link = False
            estado_pago = json_response['estado_pago']
            if estado_pago == 'problemas_pago':
                raise UserError(_(json_response['problemas_message']))
            # Receive and stroe XML 
            if json_response.get('pago_xml'):
                p._set_data_from_xml(base64.b64decode(json_response['pago_xml']))

                xml_file_name = p.name.replace('.','').replace('/', '_') + '.xml'
                self.env['ir.attachment'].sudo().create(
                                            {
                                                'name': xml_file_name,
                                                'datas': json_response['pago_xml'],
                                                #'datas_fname': xml_file_name,
                                                'res_model': self._name,
                                                'res_id': p.id,
                                                'type': 'binary'
                                            })  
                report = self.env['ir.actions.report']._get_report_from_name('cdfi_invoice.report_payment')
                report_data = report._render_qweb_pdf([p.id])[0]
                pdf_file_name = p.name.replace('/', '_') + '.pdf'
                self.env['ir.attachment'].sudo().create(
                                            {
                                                'name': pdf_file_name,
                                                'datas': base64.b64encode(report_data),
                                           #     'datas_fname': pdf_file_name,
                                                'res_model': self._name,
                                                'res_id': p.id,
                                                'type': 'binary'
                                            })

            p.write({'estado_pago': estado_pago,
                    'xml_payment_link': xml_file_link})
            p.message_post(body="CFDI emitido")
            
    
#     def validate_complete_payment(self):
#         for rec in self:
#            rec.post()
#            return {
#                'name': _('Payments'),
#                'view_type': 'form',
#                'view_mode': 'form',
#                'res_model': 'account.payment',
#                'view_id': False,
#                'type': 'ir.actions.act_window',
#                'res_id': rec.id,
#            }

    
    def _set_data_from_xml(self, xml_payment):
        if not xml_payment:
            return None
        NSMAP = {
                 'xsi':'http://www.w3.org/2001/XMLSchema-instance',
                 'cfdi':'http://www.sat.gob.mx/cfd/3', 
                 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
                 'pago10': 'http://www.sat.gob.mx/Pagos',
                 }
        xml_data = etree.fromstring(xml_payment)
        Emisor = xml_data.find('cfdi:Emisor', NSMAP)
        RegimenFiscal = Emisor.find('cfdi:RegimenFiscal', NSMAP)
        Complemento = xml_data.find('cfdi:Complemento', NSMAP)
        TimbreFiscalDigital = Complemento.find('tfd:TimbreFiscalDigital', NSMAP)
        Pagos = Complemento.find('pago10:Pagos', NSMAP)
        Pago = Pagos.find('pago10:Pago', NSMAP)
        DoctoRelacionado = Pago.find('pago10:DoctoRelacionado', NSMAP)
        self.rfc_emisor = Emisor.attrib['Rfc']
        self.name_emisor = Emisor.attrib['Nombre']
#        if self.invoice_ids:
#           self.methodo_pago = DoctoRelacionado.attrib['MetodoDePagoDR']
#           self.moneda = DoctoRelacionado.attrib['MonedaDR']
#           self.monedap = Pago.attrib['MonedaP']
#           if self.monedap != 'MXN':		   
#               self.tipocambiop = Pago.attrib['TipoCambioP']	   
#           if self.moneda != self.monedap:
#                 self.tipocambio = DoctoRelacionado.attrib['TipoCambioDR']
#           self.iddocumento = DoctoRelacionado.attrib['IdDocumento']
        self.numero_cetificado = xml_data.attrib['NoCertificado']
        self.fecha_emision = xml_data.attrib['Fecha']
        self.cetificaso_sat = TimbreFiscalDigital.attrib['NoCertificadoSAT']
        self.fecha_certificacion = TimbreFiscalDigital.attrib['FechaTimbrado']
        self.selo_digital_cdfi = TimbreFiscalDigital.attrib['SelloCFD']
        self.selo_sat = TimbreFiscalDigital.attrib['SelloSAT']
        self.folio_fiscal = TimbreFiscalDigital.attrib['UUID']
        self.folio = xml_data.attrib['Folio']     
        self.invoice_datetime = xml_data.attrib['Fecha']
        self.version = TimbreFiscalDigital.attrib['Version']
        self.cadena_origenal = '||%s|%s|%s|%s|%s||' % (self.version, self.folio_fiscal, self.fecha_certificacion, 
                                                         self.selo_digital_cdfi, self.cetificaso_sat)
        
        options = {'width': 275 * mm, 'height': 275 * mm}
        amount_str = str(self.amount).split('.')
        qr_value = 'https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?&id=%s&re=%s&rr=%s&tt=%s.%s&fe=%s' % (self.folio_fiscal,
                                                 self.company_id.vat, 
                                                 self.partner_id.vat,
                                                 amount_str[0].zfill(10),
                                                 amount_str[1].ljust(6, '0'),
                                                 self.selo_digital_cdfi[-8:],
                                                 )
        self.qr_value = qr_value
        ret_val = createBarcodeDrawing('QR', value=qr_value, **options)
        self.qrcode_image = base64.encodebytes(ret_val.asString('jpg'))
        self.folio_fiscal = TimbreFiscalDigital.attrib['UUID']
        
    
    def send_payment(self):
        self.ensure_one()
        template = self.env.ref('cdfi_invoice.email_template_payment', False)
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
            
        ctx = dict()
        ctx.update({
            'default_model': 'account.payment',
            'default_res_id': self.id,
            'default_use_template': bool(template),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
        })
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    
    def action_cfdi_cancel(self):
        for p in self:
            #if invoice.factura_cfdi:
                if p.estado_pago == 'factura_cancelada':
                    pass
                    # raise UserError(_('La factura ya fue cancelada, no puede volver a cancelarse.'))
                if not p.company_id.archivo_cer:
                    raise UserError(_('Falta la ruta del archivo .cer'))
                if not p.company_id.archivo_key:
                    raise UserError(_('Falta la ruta del archivo .key'))
                archivo_cer = p.company_id.archivo_cer.decode("utf-8")
                archivo_key = p.company_id.archivo_key.decode("utf-8")

                domain = [
                     ('res_id', '=', p.id),
                     ('res_model', '=', p._name),
                     ('name', '=', p.name.replace('/', '_') + '.xml')]
                xml_file = self.env['ir.attachment'].search(domain)[0]

                values = {
                          'rfc': p.company_id.vat,
                          'api_key': p.company_id.proveedor_timbrado,
                          'uuid': p.folio_fiscal,
                          'folio': p.folio,
                          'serie_factura': p.company_id.serie_complemento,
                          'modo_prueba': p.company_id.modo_prueba,
                            'certificados': {
                                  'archivo_cer': archivo_cer,
                                  'archivo_key': archivo_key,
                                  'contrasena': p.company_id.contrasena,
                            },
                          'xml': xml_file.datas.decode("utf-8"),
                          'motivo': self.env.context.get('motivo_cancelacion',False),
                          'foliosustitucion': self.env.context.get('foliosustitucion',''),
                          }
                if p.company_id.proveedor_timbrado == 'multifactura':
                    url = '%s' % ('http://facturacion.itadmin.com.mx/api/refund')
                elif p.company_id.proveedor_timbrado == 'multifactura2':
                    url = '%s' % ('http://facturacion2.itadmin.com.mx/api/refund')
                elif p.company_id.proveedor_timbrado == 'multifactura3':
                    url = '%s' % ('http://facturacion3.itadmin.com.mx/api/refund')
                elif p.company_id.proveedor_timbrado == 'gecoerp':
                    if p.company_id.modo_prueba:
                         #url = '%s' % ('https://ws.gecoerp.com/itadmin/pruebas/refund/?handler=OdooHandler33')
                        url = '%s' % ('https://itadmin.gecoerp.com/refund/?handler=OdooHandler33')
                    else:
                        url = '%s' % ('https://itadmin.gecoerp.com/refund/?handler=OdooHandler33')
                response = requests.post(url , 
                                         auth=None,verify=False, data=json.dumps(values), 
                                         headers={"Content-type": "application/json"})

                json_response = response.json()
                
                if json_response['estado_factura'] == 'problemas_factura':
                    raise UserError(_(json_response['problemas_message']))
                elif json_response.get('factura_xml', False):
                    file_name = 'CANCEL_' + p.name.replace('/', '_') + '.xml'
                    self.env['ir.attachment'].sudo().create(
                                                {
                                                    'name': file_name,
                                                    'datas': json_response['factura_xml'],
                                                    #'datas_fname': file_name,
                                                    'res_model': self._name,
                                                    'res_id': p.id,
                                                    'type': 'binary'
                                                })
                p.write({'estado_pago': json_response['estado_factura']})
                p.message_post(body="CFDI Cancelado")

class AccountPaymentMail(models.Model):
    _name = "account.payment.mail"
    _inherit = ['mail.thread']
    _description = "Payment Mail"
    
    payment_id = fields.Many2one('account.payment', string='Payment')
    name = fields.Char(related='payment_id.name')
    xml_payment_link = fields.Char(related='payment_id.xml_payment_link')
    partner_id = fields.Many2one(related='payment_id.partner_id')
    company_id = fields.Many2one(related='payment_id.company_id')
    
class MailTemplate(models.Model):
    "Templates for sending email"
    _inherit = 'mail.template'
    
    @api.model
    def _get_file(self, url):
        url = url.encode('utf8')
        filename, headers = urllib.urlretrieve(url)
        fn, file_extension = os.path.splitext(filename)
        return  filename, file_extension.replace('.', '')

    
    def generate_email(self, res_ids, fields=None):
        results = super(MailTemplate, self).generate_email(res_ids, fields=fields)
        
        if isinstance(res_ids, (int)):
            res_ids = [res_ids]

        # templates: res_id -> template; template -> res_ids
        
        template_id = self.env.ref('cdfi_invoice.email_template_payment')
        for lang, (template, template_res_ids) in self._classify_per_lang(res_ids).items():
            if template.id  == template_id.id:
                for res_id in template_res_ids:
                    payment = self.env[template.model].browse(res_id)
                    if payment.estado_pago != 'pago_no_enviado':
                        attachments =  results[res_id]['attachments'] or []
                        domain = [
                            ('res_id', '=', payment.id),
                            ('res_model', '=', payment._name),
                            ('name', '=', payment.name.replace('.','').replace('/', '_') + '.xml')]
                        xml_file = self.env['ir.attachment'].search(domain, limit=1)
                        if xml_file:
                           attachments.append((payment.name.replace('.','').replace('/', '_') + '.xml', xml_file.datas))
                        results[res_id]['attachments'] = attachments
        return results

class AccountPaymentTerm(models.Model):
    "Terminos de pago"
    _inherit = "account.payment.term"

    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),
                   ('PPD', _('Pago en parcialidades o diferido')),],
        string=_('Método de pago'), 
    )

    forma_pago = fields.Selection(
        selection=[('01', '01 - Efectivo'), 
                   ('02', '02 - Cheque nominativo'), 
                   ('03', '03 - Transferencia electrónica de fondos'),
                   ('04', '04 - Tarjeta de Crédito'), 
                   ('05', '05 - Monedero electrónico'),
                   ('06', '06 - Dinero electrónico'), 
                   ('08', '08 - Vales de despensa'), 
                   ('12', '12 - Dación en pago'), 
                   ('13', '13 - Pago por subrogación'), 
                   ('14', '14 - Pago por consignación'), 
                   ('15', '15 - Condonación'), 
                   ('17', '17 - Compensación'), 
                   ('23', '23 - Novación'), 
                   ('24', '24 - Confusión'), 
                   ('25', '25 - Remisión de deuda'), 
                   ('26', '26 - Prescripción o caducidad'), 
                   ('27', '27 - A satisfacción del acreedor'), 
                   ('28', '28 - Tarjeta de débito'), 
                   ('29', '29 - Tarjeta de servicios'), 
                   ('30', '30 - Aplicación de anticipos'),
                   ('31', '31 - Intermediario pagos'),
                   ('99', '99 - Por definir'),],
        string=_('Forma de pago'),
    )
