"""Deterministic, stdlib-only acceptance checks for the MiraFlores case packet.
Run: python3 -m unittest discover -s tests -v
These tests deliberately use the packet's own stated rules, not external tax law.
"""
import json
import pathlib
import unittest

P = json.loads((pathlib.Path(__file__).resolve().parents[1]/'packet.json').read_text())
V = P['return_versions'][-1]
EV = {(e['document_id'],e['field']):e['value'] for e in P['extracted_values']}
LINES = {r['key']:r for r in V['lines']}

class PacketChecks(unittest.TestCase):
    def test_packet_is_complete(self):
        self.assertEqual((len(P['documents']),len(P['extracted_values']),len(P['return_versions'])),(74,3012,3))
        self.assertEqual(V['version'],'v3')
        self.assertEqual(len(LINES),627)

    def test_estimated_payment_wrong_year(self):
        account=P['tax_agency_records']['ftb_account']
        correct=sum(x['amount'] for x in account['tax_year_2025_payments'])
        wrong=sum(x['amount'] for x in account['tax_year_2024_payments_after_filing'])
        reported=LINES['F540NR.72']['value']
        self.assertEqual((reported,correct,wrong),(14000,10500,3500))
        self.assertEqual(reported-correct,wrong)

    def test_gross_receipts_duplicated(self):
        books=EV['D14','Sales - client projects']+EV['D14','Sales - print and licensing']
        form1099k=EV['D21','box1a']
        returned=LINES['SchC.1']['value']
        self.assertEqual(books,151300)
        self.assertEqual(form1099k,12400)
        self.assertEqual(returned-books,form1099k)
        detail=next(d for d in P['documents'] if d['id']=='D15')['pages'][2]['printed_content']
        self.assertIn('12,400.00',detail)
        self.assertIn('Sales - client projects',detail)

    def test_dependent_id_conflict(self):
        theo=next(p for p in P['household']['people'] if p['id']=='theo')
        source=EV['D71','ssn']
        self.assertNotEqual(theo['ssn'],source)
        self.assertEqual(theo['ssn'][-4:],'3309')
        self.assertEqual(source[-4:],'3390')
        self.assertNotIn('D71',V['documents_used'])

    def test_california_income_sourcing_is_suspect(self):
        self.assertEqual(LINES['SchCA540NR.1.E']['value'],218400)
        self.assertEqual(P['household']['residency'][1]['from'],'2025-07-15')
        paystub=next(d for d in P['documents'] if d['id']=='D73')['pages'][0]['printed_content']
        self.assertIn('Austin, TX effective 07/15/2025',paystub)

    def test_broker_and_cryptocurrency_diagnostics(self):
        codes={x['code'] for x in V['diagnostics']}
        self.assertIn('BROKER_SUMMARY_DETAIL_MISMATCH',codes)
        self.assertIn('DIGITAL_ASSET_BASIS_MISSING',codes)
        self.assertIn('CA_AMT_NOT_COMPUTED',codes)

    def test_all_extraction_refs_are_resolvable(self):
        ev_ids={e['id'] for e in P['extracted_values']}
        dangling={s for ln in V['lines'] for s in ln.get('sources',[]) if s.startswith('ev-') and s not in ev_ids}
        self.assertFalse(dangling, f'Broken extracted_value refs: {sorted(dangling)[:5]}')

    def test_engine_what_if_is_provided_not_generated(self):
        choices=P['what_if']['alternatives']
        self.assertEqual(len(choices),5)
        self.assertEqual(next(x for x in choices if x['id']=='equipment_section179')['california']['total_tax_change'],-1050)

if __name__=='__main__':unittest.main()
