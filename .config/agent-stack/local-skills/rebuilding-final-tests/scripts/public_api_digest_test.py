"""Contract tests for public_api_digest.py, run through its CLI on throwaway packages.

Run: uv run --no-project --with pytest pytest scripts/public_api_digest_test.py -q
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("public_api_digest.py")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def digest(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=root, check=False, capture_output=True, text=True, timeout=60
    )


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """`shop` re-exports `Cart` and `price_with_tax`; `shop.payments` is public by name; `shop._ledger` is private."""
    write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "shop"\n[project.entry-points."shop.plugins"]\ncard = "shop.payments:Card"\n',
    )
    write(
        tmp_path / "src/shop/__init__.py",
        '"""Shopping carts."""\nfrom shop.cart import Cart, label, price_with_tax, route\n\n__all__ = ["Cart", "label", "price_with_tax", "route"]\n',
    )
    write(
        tmp_path / "src/shop/cart.py",
        "from dataclasses import dataclass\n\n\n"
        "@dataclass\nclass Cart:\n"
        '    """A cart of priced items."""\n\n'
        "    owner: str\n    items: list[int]\n\n"
        "    def total(self, *, discount: float = 0.0) -> float:\n"
        '        """Sum of item prices minus `discount`."""\n'
        "        if discount < 0:\n"
        '            raise ValueError("discount must not be negative")\n'
        "        return sum(self.items) - discount\n\n"
        "    def _audit(self) -> None:\n        pass\n\n\n"
        "def price_with_tax(price: float, rate: float = 0.2) -> float:\n"
        '    """Price including tax."""\n    return price * (1 + rate)\n\n\n'
        "def helper_not_exported() -> int:\n    return 1\n\n\n"
        'def label(sep: str = ": ", *, prefix: str = "a:b") -> str:  # trailing comment\n'
        "    return prefix + sep\n\n\n"
        'def route(\n    table: dict = {"k": 1},\n    key=lambda x: x,\n):  # comment\n    return table\n',
    )
    write(
        tmp_path / "src/shop/payments.py",
        '"""Payment methods."""\n\n\nclass Card:\n    """A card payment."""\n\n'
        "    def charge(self, amount: int) -> str:\n        return 'ok'\n",
    )
    write(tmp_path / "src/shop/_ledger.py", "def post(entry):\n    return entry\n")
    return tmp_path


def test_public_functions_and_classes_show_signature_docstring_and_fields(package: Path) -> None:
    out = digest(package, "src/shop").stdout

    assert "class Cart" in out and "A cart of priced items." in out
    assert "owner: str" in out
    assert "def total(self, *, discount: float = 0.0) -> float" in out
    assert "def price_with_tax(price: float, rate: float = 0.2) -> float" in out
    assert "Price including tax." in out


def test_raised_errors_with_a_literal_message_are_listed(package: Path) -> None:
    out = digest(package, "src/shop").stdout

    assert "ValueError('discount must not be negative')" in out


def test_function_bodies_never_appear(package: Path) -> None:
    out = digest(package, "src/shop").stdout

    assert "return sum" not in out
    assert "return price * (1 + rate)" not in out


@pytest.mark.parametrize(
    "header",
    [
        pytest.param('def label(sep: str = ": ", *, prefix: str = "a:b") -> str\n```', id="colon-in-string-defaults"),
        pytest.param('def route(\n    table: dict = {"k": 1},\n    key=lambda x: x,\n)\n```', id="dict-and-lambda"),
    ],
)
def test_signature_ends_at_the_colon_that_opens_the_body(package: Path, header: str) -> None:
    """Colons inside defaults, dicts and lambdas, and trailing comments, are part of no header."""
    assert header in digest(package, "src/shop").stdout


@pytest.mark.parametrize(
    "internal",
    [
        pytest.param("def post", id="underscore-module"),
        pytest.param("_audit", id="underscore-method"),
        pytest.param("helper_not_exported", id="name-outside-all"),
    ],
)
def test_internal_code_is_left_out(package: Path, internal: str) -> None:
    """The blind writer must not learn about internals."""
    assert internal not in digest(package, "src/shop").stdout


def test_entry_point_targets_are_public(package: Path) -> None:
    out = digest(package, "src/shop").stdout

    assert "shop.plugins" in out and "shop.payments:Card" in out
    assert "class Card" in out and "def charge(self, amount: int) -> str" in out


def test_names_imported_by_production_code_elsewhere_are_public(package: Path) -> None:
    """With --consumers, only what non-test code outside the project imports becomes public."""
    write(package / "src/shop/_ledger.py", "def post(entry):\n    return entry\n\n\ndef purge():\n    pass\n")
    write(
        package / "src/shop/inventory.py",
        "def restock(n: int) -> int:\n    return n\n\n\ndef audit() -> None:\n    pass\n",
    )
    write(package.parent / "other/app.py", "from shop.inventory import restock\nfrom shop._ledger import post\n")
    write(
        package.parent / "other/tests/test_app.py", "from shop.inventory import audit\nfrom shop._ledger import purge\n"
    )

    out = digest(package, "src/shop", "--consumers", str(package.parent)).stdout

    assert "def restock(n: int) -> int" in out and "def post(entry)" in out
    assert "def audit" not in out and "def purge" not in out, "imports from other packages' tests are not evidence"
    assert "imports by 1 non-test files outside the package" in out


def test_types_named_in_public_signatures_are_listed_even_from_internal_modules(package: Path) -> None:
    """A caller cannot use `Cart.pay(card: Token)` without knowing `Token`, wherever it is defined."""
    write(package / "src/shop/_tokens.py", "class Token:\n    def __init__(self, value: str) -> None:\n        pass\n")
    cart = (package / "src/shop/cart.py").read_text()
    cart = "from shop._tokens import Token\n" + cart.replace(
        "    def _audit(self)", "    def pay(self, card: Token) -> bool:\n        return True\n\n    def _audit(self)"
    )
    write(package / "src/shop/cart.py", cart)

    out = digest(package, "src/shop").stdout

    assert "def pay(self, card: Token) -> bool" in out
    assert "class Token" in out and "def __init__(self, value: str) -> None" in out


@pytest.fixture
def kit(tmp_path: Path) -> Path:
    """`kit` re-exports a module and a function by relative import, and declares a console script."""
    write(tmp_path / "pyproject.toml", '[project]\nname = "kit"\n[project.scripts]\nkit = "kit.cli:main"\n')
    write(
        tmp_path / "src/kit/__init__.py", 'from . import api\nfrom .core import build\n\n__all__ = ["api", "build"]\n'
    )
    write(tmp_path / "src/kit/api.py", "def ping() -> str:\n    return 'pong'\n")
    write(tmp_path / "src/kit/_types.py", "class Token:\n    pass\n\n\nclass Hidden:\n    pass\n")
    write(
        tmp_path / "src/kit/core.py",
        "from ._types import Token\n\n\nclass Builder:\n    def __init__(self, token: Token) -> None:\n        pass\n\n\n"
        "def build(token: Token) -> Builder:\n    return Builder(token)\n",
    )
    write(tmp_path / "src/kit/cli.py", "def main() -> int:\n    return 0\n\n\ndef helper() -> None:\n    pass\n")
    return tmp_path


@pytest.mark.parametrize(
    "public",
    [
        pytest.param("def ping() -> str", id="relative-module-reexport"),
        pytest.param("class Token", id="type-imported-relatively"),
        pytest.param("def main() -> int", id="console-script"),
    ],
)
def test_relative_reexports_and_console_scripts_count_as_evidence(kit: Path, public: str) -> None:
    out = digest(kit, "src/kit").stdout

    assert public in out
    assert "class Hidden" not in out and "def helper" not in out


def test_a_class_returned_by_a_public_factory_hides_its_constructor(kit: Path) -> None:
    """`build()` returns `Builder`: callers never construct it, so its constructor's types stay internal."""
    out = digest(kit, "src/kit").stdout

    assert "class Builder" in out
    assert "def __init__(self, token: Token)" not in out


def test_digest_restricts_to_changed_modules_when_asked(package: Path) -> None:
    result = digest(package, "src/shop", "--only", "src/shop/payments.py")

    assert result.returncode == 0, result.stderr
    assert "class Card" in result.stdout
    assert "class Cart" not in result.stdout


def test_missing_package_is_a_usage_error(tmp_path: Path) -> None:
    result = digest(tmp_path, "src/nope")

    assert result.returncode == 2
    assert "src/nope" in result.stderr
