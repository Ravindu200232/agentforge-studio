"""Approved journey actions mapped to the application routes a build owns."""
from __future__ import annotations

import re

from prototype_agent import demo, journey_walk
from server_modules import journeys

RECORD = ('build', 'journey-contract.json')
_WRITES = re.compile(r'\b(?:add\w*|adjust\w*|approv\w*|creat\w*|edit\w*|plac\w*|sav\w*|submit\w*|updat\w*|upload\w*)\b', re.I)


def stage(session, doc: dict, rows: list[dict]) -> tuple[list[dict], dict | None]:
    saved = session.read_record('srs', 'user-journeys.json', fallback=None)
    approved = saved if isinstance(saved, dict) and isinstance(saved.get('journeys'), list) else journeys.journey_contract_for(doc)
    planned = journey_walk.normalize_journeys(approved, bounded=False)
    original = {str(step.get('id')): step for flow in approved['journeys'] if isinstance(flow, dict)
                for step in flow.get('steps') or [] if isinstance(step, dict)}
    by_route = {row['route']: row for row in rows}
    role_names = [str(role.get('role_name') or role.get('role_key') or '') for role in doc.get('roles') or [] if isinstance(role, dict)]
    candidates = []
    for flow in planned:
        actor = flow['who']
        for step in flow['steps']:
            declared = original.get(step['id'], {})
            named = next((role for role in role_names if role and re.match(r'^(?:the\s+)?' + re.escape(role) + r'\b', step['step'], re.I)), '')
            actor = str(declared.get('actor') or declared.get('who') or named or actor)
            route = journey_walk.page_route(step['route'], rows) if step['route'] else ''
            step.update(actor=actor, prototype_route=route, prototype_file=by_route.get(route, {}).get('file', ''))
            for key in ('expected_outcome', 'test_data'):
                if declared.get(key):
                    step[key] = declared[key]
        if not all(step['prototype_route'] for step in flow['steps']) or not re.fullmatch(r'UJ-\d{3,}', flow['id']):
            continue
        # Prefer the first mapped write journey with one actor, so the initial check proves persistence cheaply.
        roles = {step['actor'].casefold() for step in flow['steps'] if step['actor']}
        writes = any(_WRITES.search(step['step']) for step in flow['steps'])
        candidates.append((writes, len(roles) <= 1, flow))
    first = max(candidates, key=lambda candidate: candidate[:2])[2] if candidates else None
    if first:
        route_order = dict.fromkeys(step['prototype_route'] for step in first['steps'])
        sign_in = demo.sign_in_route(doc)
        if sign_in in by_route and any(by_route[route].get('signed_in', bool(by_route[route]['roles'])) for route in route_order):
            route_order[sign_in] = None
        if '/' in by_route:
            route_order['/'] = None
        first = {**first, 'routes': list(route_order)}
    session.write_record(*RECORD, data={'journeys': planned, 'first_journey': first})
    return planned, first
