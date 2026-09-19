"""Live end-to-end verification script for GRIDPOINT.
"""

import requests

def run_verification():
    base = 'http://127.0.0.1:8000'
    checks = [
        ('Static HTML', 'GET', f'{base}/'),
        ('CSS Stylesheet', 'GET', f'{base}/style.css'),
        ('Client Script', 'GET', f'{base}/app.js'),
        ('API Health', 'GET', f'{base}/api/health'),
        ('Demo Data', 'GET', f'{base}/api/demo-data'),
    ]

    for name, method, url in checks:
        r = requests.get(url)
        assert r.status_code == 200, f'{name} failed: {r.status_code}'
        print(f"[PASS] {name}: HTTP {r.status_code} ({len(r.content):,} bytes)")

    # Test optimization solve
    opt_payload = {'session_id': 'default', 'p': 3, 'warehouse_capacity': 4000.0, 'priority_preset': 'cost'}
    r_opt = requests.post(f'{base}/api/optimize', json=opt_payload)
    assert r_opt.status_code == 200, f"Optimize failed: {r_opt.text}"
    opt_data = r_opt.json()
    print(f"[PASS] Optimize CFLP: {opt_data['status']} - {len(opt_data['warehouses'])} warehouses, Delivery Cost: ${opt_data['total_delivery_cost']}, Monthly Savings: ${opt_data['estimated_monthly_savings']}")

    # Test baseline comparison
    r_cmp = requests.get(f'{base}/api/compare?session_id=default')
    assert r_cmp.status_code == 200
    cmp_data = r_cmp.json()
    print(f"[PASS] Baseline Comparison: Delivery Cost Reduction {cmp_data['cost_pct_change']}%, CO2 Reduction {cmp_data['co2_pct_change']}%")

    # Test tradeoff curve
    r_tr = requests.get(f'{base}/api/tradeoff?session_id=default')
    assert r_tr.status_code == 200
    tr_data = r_tr.json()
    print(f"[PASS] Tradeoff Curve: {len(tr_data['points'])} points computed (p=1..5)")

    # Test explainability
    wid = opt_data['warehouses'][0]['warehouse_id']
    r_exp = requests.get(f'{base}/api/explain/{wid}?session_id=default')
    assert r_exp.status_code == 200
    exp_data = r_exp.json()
    print(f"[PASS] Explainability ({wid}): Demand {exp_data['demand_served']} orders ({exp_data['demand_pct_of_total']}%), Burden Eliminated: {exp_data['burden_eliminated_km']} ord-km, Next-Best: {exp_data['next_best_rejected']['name']}")

    # Test scenario lab
    scen_payload = {'session_id': 'default', 'demand_multiplier': 1.5, 'p': 3, 'warehouse_capacity': 6000.0}
    r_scen = requests.post(f'{base}/api/scenario', json=scen_payload)
    assert r_scen.status_code == 200
    scen_data = r_scen.json()
    print(f"[PASS] Scenario Lab (+50% Surge): Cost shift {scen_data['cost_pct_change']}%, Active Warehouses: {scen_data['scenario_warehouses']}")

    # Test conversational agent extract (Clarification)
    r_agent_clarify = requests.post(f'{base}/api/agent/extract', json={
        'message': 'We want 3 warehouses and 25 km radius',
        'history': [],
        'known_params': {}
    })
    assert r_agent_clarify.status_code == 200, f"Agent clarify failed: {r_agent_clarify.text}"
    clarify_data = r_agent_clarify.json()
    assert clarify_data['status'] == 'clarify'
    print(f"[PASS] Agent Extraction (Clarification): status={clarify_data['status']}, missing={clarify_data.get('missing_required_params')}, reply='{clarify_data['reply'][:60]}...'")

    # Test conversational agent extract (Confirmation)
    r_agent_confirm = requests.post(f'{base}/api/agent/extract', json={
        'message': 'Set up 3 warehouses with 4000 orders/day capacity within 25 km, cost priority',
        'history': [],
        'known_params': {}
    })
    assert r_agent_confirm.status_code == 200, f"Agent confirm failed: {r_agent_confirm.text}"
    confirm_data = r_agent_confirm.json()
    assert confirm_data['status'] == 'confirm'
    assert confirm_data['extracted_params']['warehouse_count'] == 3
    assert confirm_data['extracted_params']['warehouse_capacity'] == 4000.0
    assert confirm_data['extracted_params']['max_service_radius_km'] == 25.0
    print(f"[PASS] Agent Extraction (Confirmation): status={confirm_data['status']}, p={confirm_data['extracted_params']['warehouse_count']}, cap={confirm_data['extracted_params']['warehouse_capacity']}, radius={confirm_data['extracted_params']['max_service_radius_km']}")

    print("\nALL 12 LIVE SYSTEM CHECKS PASSED WITH 100% SUCCESS!")

if __name__ == '__main__':
    run_verification()

