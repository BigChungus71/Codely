"""Configurable, requirement-aware architecture policy and threshold contracts."""
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re


ALLOWED_STYLES = {
    'layered',
    'modular_monolith',
    'hexagonal',
    'clean',
    'microservices',
    'flat',
    'custom',
}

KNOWN_ROLES = {
    'application_entry_point',
    'router',
    'controller',
    'service',
    'data_access',
    'database_model',
    'frontend_component',
    'authentication',
    'configuration',
    'utility',
    'test',
    'unclassified',
}

RULE_IDS = (
    'CODELY-ARCH-001',
    'CODELY-ARCH-002',
    'CODELY-ARCH-003',
    'CODELY-ARCH-004',
    'CODELY-ARCH-005',
    'CODELY-ARCH-006',
    'CODELY-ARCH-007',
    'CODELY-ARCH-008',
    'CODELY-ARCH-009',
    'CODELY-ARCH-010',
    'CODELY-ARCH-011',
    'CODELY-ARCH-012',
)

DEFAULT_THRESHOLD_VALUES = {
    'max_module_lines': 400,
    'max_module_functions': 15,
    'max_module_classes': 8,
    'max_class_methods': 15,
    'max_function_lines': 60,
    'max_function_parameters': 6,
    'max_fan_in': 8,
    'max_fan_out': 8,
    'max_total_coupling': 12,
    'max_inheritance_depth': 3,
    'max_responsibility_groups_per_module': 3,
}


def _is_int(value) -> bool:
    return type(value) is int


def _valid_token(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value) is not None


@dataclass(frozen=True)
class ArchitectureThresholds:
    max_module_lines: int = 400
    max_module_functions: int = 15
    max_module_classes: int = 8
    max_class_methods: int = 15
    max_function_lines: int = 60
    max_function_parameters: int = 6
    max_fan_in: int = 8
    max_fan_out: int = 8
    max_total_coupling: int = 12
    max_inheritance_depth: int = 3
    max_responsibility_groups_per_module: int = 3
    include_tests_in_heuristics: bool = False

    def validate(self) -> None:
        for name in DEFAULT_THRESHOLD_VALUES:
            value = getattr(self, name)
            if not _is_int(value) or value < 1:
                raise ValueError(f'Threshold {name} must be a positive integer')
        if type(self.include_tests_in_heuristics) is not bool:
            raise ValueError('include_tests_in_heuristics must be a boolean')

    @classmethod
    def from_dict(cls, data: dict) -> 'ArchitectureThresholds':
        if not isinstance(data, dict):
            raise ValueError('thresholds must be an object')
        allowed = set(DEFAULT_THRESHOLD_VALUES) | {'include_tests_in_heuristics'}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f'Unknown threshold fields: {sorted(unknown)}')
        instance = cls(**data)
        instance.validate()
        return instance

    def threshold_source(self, name: str) -> str:
        return 'default' if getattr(self, name) == DEFAULT_THRESHOLD_VALUES.get(name) else 'policy'


@dataclass(frozen=True)
class ProhibitedDependency:
    source: str
    target: str
    reason: str = 'Explicitly prohibited by configured architecture policy'

    def validate(self) -> None:
        if not _valid_token(self.source) or not _valid_token(self.target):
            raise ValueError('Prohibited dependency source and target must be valid role identifiers')
        if self.source not in KNOWN_ROLES or self.target not in KNOWN_ROLES:
            raise ValueError(f'Unknown role in prohibited dependency: {self.source} -> {self.target}')
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError('Prohibited dependency reason must be a non-empty string')

    @classmethod
    def from_dict(cls, data: dict) -> 'ProhibitedDependency':
        if not isinstance(data, dict):
            raise ValueError('prohibited_dependencies entries must be objects')
        unknown = set(data) - {'source', 'target', 'reason'}
        if unknown:
            raise ValueError(f'Unknown prohibited dependency fields: {sorted(unknown)}')
        if 'source' not in data or 'target' not in data:
            raise ValueError('prohibited_dependencies entry requires source and target')
        instance = cls(
            source=data['source'],
            target=data['target'],
            reason=data.get('reason', 'Explicitly prohibited by configured architecture policy'),
        )
        instance.validate()
        return instance


@dataclass(frozen=True)
class LayerPolicy:
    allowed_dependencies: dict[str, tuple[str, ...]] | None = None
    prohibited_dependencies: tuple[ProhibitedDependency, ...] = ()
    prohibit_controller_to_data_access: bool | None = None
    allow_same_layer: bool = True
    include_inferred_roles: bool = True

    def validate(self) -> None:
        if self.allowed_dependencies is not None:
            if not isinstance(self.allowed_dependencies, dict):
                raise ValueError('allowed_dependencies must be a mapping of role to allowed target roles')
            for source_role, targets in self.allowed_dependencies.items():
                if source_role not in KNOWN_ROLES:
                    raise ValueError(f'Unknown source role in allowed_dependencies: {source_role}')
                if not isinstance(targets, (list, tuple)):
                    raise ValueError(f'allowed_dependencies[{source_role}] must be a list of roles')
                for target_role in targets:
                    if target_role not in KNOWN_ROLES:
                        raise ValueError(f'Unknown target role in allowed_dependencies: {target_role}')
        if not isinstance(self.prohibited_dependencies, (list, tuple)):
            raise ValueError('prohibited_dependencies must be a list')
        for item in self.prohibited_dependencies:
            if not isinstance(item, ProhibitedDependency):
                raise ValueError('prohibited_dependencies must contain ProhibitedDependency objects')
            item.validate()
        if self.prohibit_controller_to_data_access is not None and type(self.prohibit_controller_to_data_access) is not bool:
            raise ValueError('prohibit_controller_to_data_access must be a boolean or null')
        if type(self.allow_same_layer) is not bool:
            raise ValueError('allow_same_layer must be a boolean')
        if type(self.include_inferred_roles) is not bool:
            raise ValueError('include_inferred_roles must be a boolean')

    def has_explicit_rules(self) -> bool:
        return bool(
            self.allowed_dependencies is not None
            or self.prohibited_dependencies
            or self.prohibit_controller_to_data_access is True
        )

    @classmethod
    def from_dict(cls, data: dict) -> 'LayerPolicy':
        if not isinstance(data, dict):
            raise ValueError('layers must be an object')
        unknown = set(data) - {
            'allowed_dependencies',
            'prohibited_dependencies',
            'prohibit_controller_to_data_access',
            'allow_same_layer',
            'include_inferred_roles',
        }
        if unknown:
            raise ValueError(f'Unknown layer policy fields: {sorted(unknown)}')
        allowed_raw = data.get('allowed_dependencies')
        allowed = None
        if allowed_raw is not None:
            if not isinstance(allowed_raw, dict):
                raise ValueError('allowed_dependencies must be an object')
            allowed = {
                str(source): tuple(str(target) for target in targets)
                if isinstance(targets, (list, tuple))
                else (_ for _ in ()).throw(ValueError('allowed_dependencies values must be lists'))
                for source, targets in allowed_raw.items()
            }
        prohibited_raw = data.get('prohibited_dependencies', ())
        if not isinstance(prohibited_raw, (list, tuple)):
            raise ValueError('prohibited_dependencies must be a list')
        prohibited = tuple(
            item if isinstance(item, ProhibitedDependency) else ProhibitedDependency.from_dict(item)
            for item in prohibited_raw
        )
        instance = cls(
            allowed_dependencies=allowed,
            prohibited_dependencies=prohibited,
            prohibit_controller_to_data_access=data.get('prohibit_controller_to_data_access'),
            allow_same_layer=data.get('allow_same_layer', True),
            include_inferred_roles=data.get('include_inferred_roles', True),
        )
        instance.validate()
        return instance

    def to_dict(self) -> dict:
        return {
            'allowed_dependencies': (
                {k: list(v) for k, v in sorted(self.allowed_dependencies.items())}
                if self.allowed_dependencies is not None
                else None
            ),
            'prohibited_dependencies': [asdict(item) for item in self.prohibited_dependencies],
            'prohibit_controller_to_data_access': self.prohibit_controller_to_data_access,
            'allow_same_layer': self.allow_same_layer,
            'include_inferred_roles': self.include_inferred_roles,
        }


@dataclass(frozen=True)
class ArchitecturePolicy:
    schema_version: str = '1.0.0'
    architecture_style: str | None = None
    layers: LayerPolicy | None = None
    thresholds: ArchitectureThresholds = field(default_factory=ArchitectureThresholds)
    disabled_rules: tuple[str, ...] = ()
    check_circular_dependencies: bool = True
    check_unresolved_dependencies: bool = True

    def validate(self) -> None:
        if self.schema_version != '1.0.0':
            raise ValueError('Unsupported architecture policy schema_version')
        if self.architecture_style is not None:
            if not isinstance(self.architecture_style, str) or not _valid_token(self.architecture_style):
                raise ValueError('architecture_style must be a valid identifier or null')
        if self.layers is not None:
            if not isinstance(self.layers, LayerPolicy):
                raise ValueError('layers must be a LayerPolicy or null')
            self.layers.validate()
        if not isinstance(self.thresholds, ArchitectureThresholds):
            raise ValueError('thresholds must be ArchitectureThresholds')
        self.thresholds.validate()
        if not isinstance(self.disabled_rules, (list, tuple)):
            raise ValueError('disabled_rules must be a list of rule IDs')
        for rule_id in self.disabled_rules:
            if rule_id not in RULE_IDS:
                raise ValueError(f'Unknown rule_id in disabled_rules: {rule_id}')
        for flag in ('check_circular_dependencies', 'check_unresolved_dependencies'):
            if type(getattr(self, flag)) is not bool:
                raise ValueError(f'{flag} must be a boolean')

    def is_rule_enabled(self, rule_id: str) -> bool:
        if rule_id in self.disabled_rules:
            return False
        if rule_id == 'CODELY-ARCH-001' and not self.check_circular_dependencies:
            return False
        if rule_id == 'CODELY-ARCH-012' and not self.check_unresolved_dependencies:
            return False
        return True

    @classmethod
    def from_dict(cls, data: dict) -> 'ArchitecturePolicy':
        if not isinstance(data, dict):
            raise ValueError('Architecture policy must be a JSON object')
        unknown = set(data) - {
            'schema_version',
            'architecture_style',
            'layers',
            'thresholds',
            'disabled_rules',
            'check_circular_dependencies',
            'check_unresolved_dependencies',
        }
        if unknown:
            raise ValueError(f'Unknown architecture policy fields: {sorted(unknown)}')
        layers_raw = data.get('layers')
        layers = (
            layers_raw
            if isinstance(layers_raw, LayerPolicy) or layers_raw is None
            else LayerPolicy.from_dict(layers_raw)
        )
        thresholds_raw = data.get('thresholds')
        if thresholds_raw is None:
            thresholds = ArchitectureThresholds()
        elif isinstance(thresholds_raw, ArchitectureThresholds):
            thresholds = thresholds_raw
        else:
            thresholds = ArchitectureThresholds.from_dict(thresholds_raw)
        disabled_raw = data.get('disabled_rules', ())
        if not isinstance(disabled_raw, (list, tuple)):
            raise ValueError('disabled_rules must be a list')
        instance = cls(
            schema_version=data.get('schema_version', '1.0.0'),
            architecture_style=data.get('architecture_style'),
            layers=layers,
            thresholds=thresholds,
            disabled_rules=tuple(disabled_raw),
            check_circular_dependencies=data.get('check_circular_dependencies', True),
            check_unresolved_dependencies=data.get('check_unresolved_dependencies', True),
        )
        instance.validate()
        return instance

    def to_dict(self) -> dict:
        return {
            'schema_version': self.schema_version,
            'architecture_style': self.architecture_style,
            'layers': self.layers.to_dict() if self.layers is not None else None,
            'thresholds': asdict(self.thresholds),
            'disabled_rules': list(self.disabled_rules),
            'check_circular_dependencies': self.check_circular_dependencies,
            'check_unresolved_dependencies': self.check_unresolved_dependencies,
        }


def coerce_policy(policy: ArchitecturePolicy | dict | None) -> tuple[ArchitecturePolicy, bool]:
    """Return validated ArchitecturePolicy and whether user-defined policy was supplied."""
    if policy is None:
        return ArchitecturePolicy(), False
    if isinstance(policy, ArchitecturePolicy):
        policy.validate()
        return policy, True
    if isinstance(policy, dict):
        return ArchitecturePolicy.from_dict(policy), True
    raise TypeError('Expected ArchitecturePolicy, policy dict, or None')


def load_policy(path: str | Path) -> ArchitecturePolicy:
    """Load and validate an architecture policy JSON file."""
    target = Path(path)
    raw = json.loads(target.read_text(encoding='utf-8'))
    return ArchitecturePolicy.from_dict(raw)
