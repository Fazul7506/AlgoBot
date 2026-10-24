import unittest
from apps.brokers.sandbox_harnesses.deriv import identify_ambiguous_contract

class DerivAmbiguousReconciliationTests(unittest.TestCase):
    def test_unique_new_match(self):
        self.assertEqual(identify_ambiguous_contract({'10'}, [{'contract_id':11,'symbol':'R_100','contract_type':'CALL','buy_price':1.0}], [], symbol='R_100', contract_type='CALL', stake=1.0), 11)
    def test_preexisting_and_multiple_matches_are_rejected(self):
        row={'contract_id':11,'symbol':'R_100','contract_type':'CALL','buy_price':1.0}
        self.assertIsNone(identify_ambiguous_contract({'11'}, [row], [], symbol='R_100', contract_type='CALL', stake=1.0))
        self.assertIsNone(identify_ambiguous_contract(set(), [row, {**row,'contract_id':12}], [], symbol='R_100', contract_type='CALL', stake=1.0))
    def test_insufficient_or_mismatched_evidence_is_rejected(self):
        self.assertIsNone(identify_ambiguous_contract(set(), [{'contract_id':11}], [], symbol='R_100', contract_type='CALL', stake=1.0))
        self.assertIsNone(identify_ambiguous_contract(set(), [{'contract_id':11,'symbol':'R_50','contract_type':'CALL','buy_price':1.0}], [], symbol='R_100', contract_type='CALL', stake=1.0))

if __name__ == '__main__': unittest.main()
