"""Deterministic tests for Phase 7 architecture rules and optimization engine."""
from copy import deepcopy
import json

import jsonschema
import pytest

from backend.app.analyzers.architecture_graph import build_architecture_graph
from backend.app.analyzers.architecture_policy import (
    ArchitecturePolicy,
    ArchitectureThresholds,
    LayerPolicy,
    ProhibitedDependency,
    load_policy,
)
from backend.app.analyzers.architecture_rules import (
    ArchitectureEvaluationOptions,
    evaluate_architecture,
)
from backend.app.analyzers.architecture_rules_cli import main as rules_cli_main
from backend.app.analyzers.semgrep_adapter import ROOT
from backend.app.analyzers.structure_analyzer import analyze_repository


def write_repo(root, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')


def run_pipeline(root, policy=None, *, options=None):
    structure = analyze_repository(str(root))
    architecture = build_architecture_graph(structure)
    result = evaluate_architecture(structure, architecture, policy=policy, options=options)
    return structure, architecture, result


def rule_ids(result) -> list[str]:
    return [obs['rule_id'] for obs in result.observations]


def test_circular_dependencies_multi_module_and_self_import(tmp_path):
    write_repo(
        tmp_path,
        {
            'alpha.py': 'import beta\n',
            'beta.py': 'import alpha\n',
            'solo.py': 'import solo\n',
        },
    )
    _s, _g, result = run_pipeline(tmp_path)
    cycles = [obs for obs in result.observations if obs['rule_id'] == 'CODELY-ARCH-001']
    assert len(cycles) == 2
    multi = next(obs for obs in cycles if len(obs['affected_modules']) == 2)
    self_loop = next(obs for obs in cycles if len(obs['affected_modules']) == 1)
    assert multi['priority'] == 'HIGH'
    assert multi['evidence_classification'] == 'confirmed_structural'
    assert multi['confidence'] == 'confirmed'
    assert len(multi['supporting_graph_evidence']['dependency_paths']) == 1
    assert self_loop['priority'] == 'MEDIUM'
    assert self_loop['observed_metric']['details']['is_self_import'] is True


def test_conditional_cycle_has_medium_priority_and_caveat(tmp_path):
    write_repo(
        tmp_path,
        {
            'a.py': 'def run():\n    import b\n    return b\n',
            'b.py': 'def helper():\n    import a\n    return a\n',
        },
    )
    _s, _g, result = run_pipeline(tmp_path)
    cycle = next(obs for obs in result.observations if obs['rule_id'] == 'CODELY-ARCH-001')
    assert cycle['priority'] == 'MEDIUM'
    assert cycle['observed_metric']['details']['all_witness_imports_conditional'] is True
    assert 'conditional' in cycle['explanation'].lower()


def test_configurable_coupling_thresholds_and_role_nuance(tmp_path):
    write_repo(
        tmp_path,
        {
            'utils.py': 'VALUE = 1\n',
            'hub_service.py': 'import dep_a\nimport dep_b\nimport dep_c\nimport utils\n',
            'dep_a.py': 'import utils\n',
            'dep_b.py': 'import utils\n',
            'dep_c.py': 'import utils\n',
            'caller_one.py': 'import hub_service\n',
            'caller_two.py': 'import hub_service\n',
            'main.py': 'import caller_one\nimport caller_two\nimport dep_a\nimport dep_b\n',
        },
    )
    # Default thresholds (max_fan_in=8, max_fan_out=8, max_total_coupling=12) should not flag these.
    _s, _g, default_res = run_pipeline(tmp_path)
    assert not any(r in {'CODELY-ARCH-004', 'CODELY-ARCH-005', 'CODELY-ARCH-006'} for r in rule_ids(default_res))

    strict_policy = ArchitecturePolicy(
        thresholds=ArchitectureThresholds(max_fan_in=3, max_fan_out=3, max_total_coupling=5),
    )
    _s, _g, strict_res = run_pipeline(tmp_path, policy=strict_policy)
    fan_in_obs = [o for o in strict_res.observations if o['rule_id'] == 'CODELY-ARCH-005']
    fan_out_obs = [o for o in strict_res.observations if o['rule_id'] == 'CODELY-ARCH-006']
    total_obs = [o for o in strict_res.observations if o['rule_id'] == 'CODELY-ARCH-004']

    assert [o['affected_modules'][0]['file'] for o in fan_in_obs] == ['utils.py']
    assert fan_in_obs[0]['priority'] == 'LOW'  # shared utility foundation nuance
    assert {o['affected_modules'][0]['file'] for o in fan_out_obs} == {'hub_service.py', 'main.py'}
    main_fan_out = next(o for o in fan_out_obs if o['affected_modules'][0]['file'] == 'main.py')
    hub_fan_out = next(o for o in fan_out_obs if o['affected_modules'][0]['file'] == 'hub_service.py')
    assert main_fan_out['priority'] == 'LOW'
    assert hub_fan_out['priority'] == 'MEDIUM'
    assert [o['affected_modules'][0]['file'] for o in total_obs] == ['hub_service.py']
    assert total_obs[0]['configured_threshold']['source'] == 'policy'


def test_valid_and_invalid_layer_relationships_and_missing_policy(tmp_path):
    write_repo(
        tmp_path,
        {
            'api.py': (
                'from fastapi import APIRouter\n'
                'from services import UserService\n'
                'router = APIRouter()\n'
                '@router.get("/users")\n'
                'def get_users():\n'
                '    return UserService().list()\n'
            ),
            'direct_ctrl.py': (
                'from flask import Blueprint\n'
                'from repo import UserRepo\n'
                'bp = Blueprint("u", __name__)\n'
                '@bp.route("/u")\n'
                'def users():\n'
                '    return UserRepo().all()\n'
            ),
            'services.py': 'from repo import UserRepo\nclass UserService:\n    def list(self):\n        return UserRepo().all()\n',
            'repo.py': (
                'import sqlite3\n'
                'class UserRepo:\n'
                '    def all(self):\n'
                '        return sqlite3.connect("x.db")\n'
            ),
            'tests/test_direct.py': 'import direct_ctrl\nimport repo\n',
        },
    )
    # Without policy, layer violations must NOT be assumed or emitted.
    _s, _g, no_policy_res = run_pipeline(tmp_path, policy=None)
    assert no_policy_res.policy['policy_configured'] is False
    assert no_policy_res.policy['layer_rules_active'] is False
    assert 'CODELY-ARCH-002' not in rule_ids(no_policy_res)
    assert 'CODELY-ARCH-003' not in rule_ids(no_policy_res)

    # With layered policy, direct_ctrl -> repo triggers CODELY-ARCH-003 (confirmed), while api -> services -> repo is valid,
    # and tests/test_direct.py is excluded from layer violations.
    layered_policy = load_policy(ROOT / 'contracts/examples/architecture-policy-v1.json')
    _s, _g, layered_res = run_pipeline(tmp_path, policy=layered_policy)
    assert layered_res.status == 'complete'
    layer_obs = [o for o in layered_res.observations if o['rule_id'] in {'CODELY-ARCH-002', 'CODELY-ARCH-003'}]
    assert len(layer_obs) == 1
    assert layer_obs[0]['rule_id'] == 'CODELY-ARCH-003'
    assert layer_obs[0]['confidence'] == 'confirmed'
    assert layer_obs[0]['evidence_classification'] == 'confirmed_structural'
    assert layer_obs[0]['priority'] == 'HIGH'
    assert [m['file'] for m in layer_obs[0]['affected_modules']] == ['direct_ctrl.py', 'repo.py']


def test_prohibited_dependency_and_inferred_vs_confirmed_layers(tmp_path):
    write_repo(
        tmp_path,
        {
            'database.py': 'import services\nVALUE = 1\n',
            'services.py': 'def run():\n    return 1\n',
            'other_service.py': 'import services\n',
        },
    )
    policy = ArchitecturePolicy(
        architecture_style='layered',
        layers=LayerPolicy(
            allowed_dependencies={'service': ('data_access',), 'data_access': ('utility',)},
            prohibited_dependencies=(
                ProhibitedDependency(source='data_access', target='service', reason='Data layer cannot import service'),
            ),
            allow_same_layer=False,
        ),
    )
    _s, _g, result = run_pipeline(tmp_path, policy=policy)
    layer_obs = [o for o in result.observations if o['rule_id'] == 'CODELY-ARCH-002']
    # Both database.py -> services.py (prohibited) and other_service.py -> services.py (allow_same_layer=False)
    assert len(layer_obs) == 2
    assert all(o['confidence'] == 'inferred' for o in layer_obs)
    assert all(o['evidence_classification'] == 'heuristic_maintainability' for o in layer_obs)

    # Disabling inferred roles suppresses heuristic layer violations
    confirmed_only = ArchitecturePolicy(
        architecture_style='layered',
        layers=LayerPolicy(
            allowed_dependencies={'service': ('data_access',)},
            include_inferred_roles=False,
        ),
    )
    _s, _g, confirmed_res = run_pipeline(tmp_path, policy=confirmed_only)
    assert 'CODELY-ARCH-002' not in rule_ids(confirmed_res)


def test_oversized_functions_modules_and_parameters(tmp_path):
    long_body = '\n'.join(f'    x_{i} = {i}' for i in range(15))
    write_repo(
        tmp_path,
        {
            'big_module.py': (
                f'def long_fn(a, b, c):\n{long_body}\n    return a\n\n'
                'def many_params(p1, p2, p3, p4, p5):\n    return p1\n\n'
                'class Worker:\n'
                '    def ok_method(self, p1, p2, p3, p4):\n'
                '        return p1\n'
                '    @staticmethod\n'
                '    def static_many(p1, p2, p3, p4, p5):\n'
                '        return p1\n'
            )
        },
    )
    policy = ArchitecturePolicy(
        thresholds=ArchitectureThresholds(
            max_module_lines=20,
            max_function_lines=10,
            max_function_parameters=4,
        )
    )
    _s, _g, result = run_pipeline(tmp_path, policy=policy)
    assert 'CODELY-ARCH-007' in rule_ids(result)
    assert 'CODELY-ARCH-008' in rule_ids(result)
    param_obs = [o for o in result.observations if o['rule_id'] == 'CODELY-ARCH-009']
    flagged_names = {o['affected_symbols'][0]['qualified_name'] for o in param_obs}
    # ok_method has self + 4 = 4 effective params (<= 4, must NOT be flagged)
    assert flagged_names == {'many_params', 'Worker.static_many'}


def test_deep_inheritance_cross_module_and_safe_orm_model(tmp_path):
    write_repo(
        tmp_path,
        {
            'base.py': 'class RootBase:\n    pass\n',
            'mid.py': 'from base import RootBase\nclass MidA(RootBase):\n    pass\nclass MidB(MidA):\n    pass\n',
            'leaf.py': 'from mid import MidB\nclass Leaf(MidB):\n    pass\n',
            'models.py': 'from django.db import models\nclass UserModel(models.Model):\n    pass\n',
        },
    )
    _s, _g, result = run_pipeline(tmp_path)
    inh = [o for o in result.observations if o['rule_id'] == 'CODELY-ARCH-010']
    assert len(inh) == 1
    assert inh[0]['affected_symbols'][0]['qualified_name'] == 'Leaf'
    assert inh[0]['observed_metric']['value'] == 4
    assert inh[0]['evidence_classification'] == 'confirmed_structural'
    assert inh[0]['observed_metric']['details']['chain'] == ['Leaf', 'MidB', 'MidA', 'RootBase']


def test_responsibility_concentration_without_false_positive_on_router_app(tmp_path):
    methods = '\n'.join(f'    def m{i}(self):\n        return {i}\n' for i in range(6))
    write_repo(
        tmp_path,
        {
            'clean_app.py': (
                'from fastapi import FastAPI\n'
                'app = FastAPI()\n'
                '@app.get("/health")\n'
                'def health():\n'
                '    return {"ok": True}\n'
            ),
            'monolith.py': (
                'import os\n'
                'import sqlite3\n'
                'from fastapi import APIRouter\n'
                'from fastapi.security import OAuth2PasswordBearer\n'
                'router = APIRouter()\n'
                '@router.get("/items")\n'
                'def get_items():\n'
                '    key = os.getenv("KEY")\n'
                '    conn = sqlite3.connect("db.sqlite")\n'
                '    return (key, conn, OAuth2PasswordBearer)\n'
                f'class MegaHandler:\n{methods}\n'
            ),
        },
    )
    policy = ArchitecturePolicy(
        thresholds=ArchitectureThresholds(max_class_methods=5, max_responsibility_groups_per_module=3)
    )
    _s, _g, result = run_pipeline(tmp_path, policy=policy)
    resp_obs = [o for o in result.observations if o['rule_id'] == 'CODELY-ARCH-011']
    assert len(resp_obs) == 2
    assert all(o['affected_modules'][0]['file'] == 'monolith.py' for o in resp_obs)
    assert all('clean_app.py' not in [m['file'] for m in o['affected_modules']] for o in resp_obs)


def test_partial_coverage_and_unresolved_internal_vs_external(tmp_path):
    write_repo(
        tmp_path,
        {
            'broken_syntax.py': 'def invalid(:\n',
            'bad_imports.py': (
                'from .missing_local import Thing\n'
                'import some_unknown_third_party_pkg\n'
            ),
        },
    )
    _s, _g, result = run_pipeline(tmp_path)
    assert result.status == 'partial'
    assert result.coverage['unparsed_modules'] == 1
    assert result.coverage['unresolved_internal_imports'] == 1
    assert result.coverage['unclassified_external_imports'] == 1
    unresolved_obs = [o for o in result.observations if o['rule_id'] == 'CODELY-ARCH-012']
    assert len(unresolved_obs) == 1
    assert unresolved_obs[0]['observed_metric']['value'] == 1
    assert unresolved_obs[0]['affected_modules'][0]['file'] == 'bad_imports.py'


def test_empty_repository_and_mismatch_fail_closed(tmp_path):
    empty_dir = tmp_path / 'empty'
    empty_dir.mkdir()
    structure = analyze_repository(str(empty_dir))
    architecture = build_architecture_graph(structure)
    result = evaluate_architecture(structure, architecture)
    assert result.status == 'error'
    assert result.observations == []
    assert result.summary['evaluated_modules'] == 0

    # Mismatch between structure and graph fails closed
    repo_dir = tmp_path / 'repo'
    write_repo(repo_dir, {'a.py': 'x = 1\n'})
    s1 = analyze_repository(str(repo_dir))
    g1 = build_architecture_graph(s1)
    s2 = deepcopy(s1)
    s2.modules[0]['file'] = 'changed.py'
    mismatch = evaluate_architecture(s2, g1)
    assert mismatch.status == 'error'
    assert any(d['code'] == 'graph_structure_mismatch' for d in mismatch.diagnostics)
    assert mismatch.observations == []


def test_determinism_disabled_rules_and_policy_validation(tmp_path):
    write_repo(
        tmp_path,
        {
            'a.py': 'import b\n',
            'b.py': 'import a\n',
            'isolated.py': 'def ok():\n    return 1\n',
        },
    )
    structure = analyze_repository(str(tmp_path))
    architecture = build_architecture_graph(structure)
    r1 = evaluate_architecture(structure, architecture)
    r2 = evaluate_architecture(structure, architecture)
    assert r1.to_dict() == r2.to_dict()
    assert r1.gemini_evidence_package() == r2.gemini_evidence_package()

    # Isolated module is never flagged
    assert all('isolated.py' not in [m['file'] for m in o['affected_modules']] for o in r1.observations)

    # Disabling rule suppresses it
    disabled = ArchitecturePolicy(disabled_rules=('CODELY-ARCH-001',))
    r3 = evaluate_architecture(structure, architecture, policy=disabled)
    assert 'CODELY-ARCH-001' not in rule_ids(r3)

    # Validation rejects boolean-as-int, negative thresholds, unknown keys/roles
    with pytest.raises(ValueError):
        ArchitecturePolicy.from_dict({'thresholds': {'max_fan_in': True}})
    with pytest.raises(ValueError):
        ArchitecturePolicy.from_dict({'thresholds': {'max_fan_in': 0}})
    with pytest.raises(ValueError):
        ArchitecturePolicy.from_dict({'unknown_key': 1})
    with pytest.raises(ValueError):
        ArchitecturePolicy.from_dict({'layers': {'allowed_dependencies': {'invented_role': ['service']}}})


def test_observation_truncation_and_gemini_package_privacy(tmp_path):
    write_repo(
        tmp_path,
        {
            'a.py': 'SECRET_TOKEN = "do-not-leak-literal"\nimport b\n',
            'b.py': 'import a\n',
            'c.py': 'from .missing import X\n',
        },
    )
    _s, _g, result = run_pipeline(
        tmp_path,
        options=ArchitectureEvaluationOptions(max_observations=1),
    )
    assert result.status == 'partial'
    assert result.coverage['observations_truncated'] is True
    assert len(result.observations) == 1
    assert any(d['code'] == 'max_observations' for d in result.diagnostics)

    pkg = result.gemini_evidence_package()
    serialized = json.dumps(pkg)
    assert 'do-not-leak-literal' not in serialized
    assert 'quality_score' not in serialized
    assert 'exploitability_probability' not in serialized
    assert 'architecture_score' not in serialized
    assert pkg['scope'] == {'type': 'repository', 'observation_id': None}
    assert len(pkg['relevant_modules']) >= 1
    assert len(pkg['dependency_paths']) >= 1

    single_id = result.observations[0]['id']
    single_pkg = result.gemini_evidence_package(single_id)
    assert single_pkg['scope'] == {'type': 'observation', 'observation_id': single_id}
    assert len(single_pkg['observations']) == 1

    with pytest.raises(KeyError):
        result.gemini_evidence_package('arch_obs_missing')


def test_contracts_schemas_examples_and_cli(capsys):
    policy_schema = json.loads((ROOT / 'contracts/architecture-policy-v1.schema.json').read_text(encoding='utf-8'))
    eval_schema = json.loads((ROOT / 'contracts/architecture-evaluation-v1.schema.json').read_text(encoding='utf-8'))
    example_policy = json.loads((ROOT / 'contracts/examples/architecture-policy-v1.json').read_text(encoding='utf-8'))
    example_eval = json.loads((ROOT / 'contracts/examples/architecture-evaluation-v1.json').read_text(encoding='utf-8'))

    jsonschema.Draft202012Validator(policy_schema).validate(example_policy)
    jsonschema.Draft202012Validator(eval_schema).validate(example_eval)

    policy = load_policy(ROOT / 'contracts/examples/architecture-policy-v1.json')
    structure = analyze_repository(str(ROOT / 'fixtures/architecture_rules_demo'))
    architecture = build_architecture_graph(structure)
    result = evaluate_architecture(structure, architecture, policy=policy)
    assert result.to_dict() == example_eval

    # Clean repository returns exit 0 from CLI
    exit_code = rules_cli_main(
        [
            str(ROOT / 'fixtures/architecture_rules_demo'),
            '--policy',
            str(ROOT / 'contracts/examples/architecture-policy-v1.json'),
        ]
    )
    assert exit_code == 2  # partial because broken_imports.py has an unresolved internal import
    captured = json.loads(capsys.readouterr().out)
    assert captured == example_eval

    exit_gemini = rules_cli_main([str(ROOT / 'fixtures/impact_demo'), '--gemini-package'])
    assert exit_gemini == 0
    gemini_out = json.loads(capsys.readouterr().out)
    assert gemini_out['scope']['type'] == 'repository'
    assert any(o['rule_id'] == 'CODELY-ARCH-001' for o in gemini_out['observations'])


def test_real_structure_demo_partial_and_clean_layered_repo(tmp_path):
    structure = analyze_repository(str(ROOT / 'fixtures/structure_demo'))
    architecture = build_architecture_graph(structure)
    result = evaluate_architecture(structure, architecture)
    assert result.status == 'partial'
    assert any(o['rule_id'] == 'CODELY-ARCH-012' for o in result.observations)

    # Clean layered repo with matching policy produces complete status and 0 observations
    write_repo(
        tmp_path,
        {
            'routes.py': 'from fastapi import APIRouter\nfrom service import Service\nrouter = APIRouter()\n@router.get("/ok")\ndef ok():\n    return Service().run()\n',
            'service.py': 'from repo import Repo\nclass Service:\n    def run(self):\n        return Repo().get()\n',
            'repo.py': 'import sqlite3\nclass Repo:\n    def get(self):\n        return sqlite3.connect("app.db")\n',
        },
    )
    policy = load_policy(ROOT / 'contracts/examples/architecture-policy-v1.json')
    _s, _g, clean = run_pipeline(tmp_path, policy=policy)
    assert clean.status == 'complete'
    assert clean.observations == []
    assert clean.summary['total_observations'] == 0
