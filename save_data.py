from src.reconciliation.reconcile import reconcile
from src.decision.decision_mapping import build_evidence_trace, map_variant_to_actions

result = reconcile("ENST00000003084:c.1521_1523delCTT")  # real VEP call
trace = build_evidence_trace(result.rule_result)
decision = map_variant_to_actions(result)

print(trace.explain())
print(decision.explain())