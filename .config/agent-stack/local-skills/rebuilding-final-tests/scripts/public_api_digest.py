#!/usr/bin/env python3
"""Write the public API of a Python package as Markdown, for the blind test writer.

    public_api_digest.py <package dir> [--consumers <repo root>] [--public <module>[:<name>] ...]
                         [--only <module.py> ...] [--out <file>]

Reads source with `ast` only and never imports the package. A name is public when there is evidence
that callers use it:

- the package `__init__.py` re-exports it (only the names in `__all__` when it defines one),
- a `pyproject.toml` entry point names it,
- with --consumers, production code outside the package's project imports it (`from pkg.mod import
  name`; a whole module counts when it is imported as a module). Test files and test directories are
  not callers: other packages' tests often reach into internals. The header lists the modules only
  tests import, so the coordinator can add real test helpers with --public,
- --public names it explicitly (a whole module, or `module:name`),
- a public signature, field or base class refers to it (a caller needs it to call the public API).

Without any of that evidence, the digest falls back to every non-underscore name in non-underscore
modules and says so in its header. Classes list their public fields and methods. Functions and
methods show their signature as written, the docstring verbatim and the exceptions they raise with
a literal message. Bodies never appear. Anything not listed is internal: the writer must not import it.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10, the system python3 on the clusters
    tomllib = None

WHOLE_MODULE = "*"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "mutants", ".tox", "build", "dist"}
DUNDER_METHODS = {"__init__", "__call__", "__iter__", "__len__", "__enter__", "__exit__"}


def module_name(package: Path, path: Path) -> str:
    parts = [package.name, *path.relative_to(package).with_suffix("").parts]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def project_root(package: Path) -> Path:
    return next((d for d in package.parents if (d / "pyproject.toml").exists()), package.parent)


def declared_all(tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets) and node.value is not None:
            try:
                return [str(name) for name in ast.literal_eval(node.value)]
            except ValueError:
                return None
    return None


def absolute(package: Path, current: str, node: ast.ImportFrom) -> str | None:
    """The absolute module an `ImportFrom` in module `current` names, relative imports resolved."""
    if node.level == 0:
        return node.module
    is_package = (package / Path(*current.split(".")[1:]) / "__init__.py").exists() or current == package.name
    base = current.split(".")
    base = base if is_package else base[:-1]
    if node.level > 1:
        base = base[: -(node.level - 1)]
    return ".".join([*base, node.module] if node.module else base) or None


def is_module(package: Path, dotted: str) -> bool:
    rest = Path(*dotted.split(".")[1:]) if "." in dotted else Path()
    return (package / rest).with_suffix(".py").is_file() or (package / rest / "__init__.py").is_file()


def add(public: dict[str, set[str]], module: str, name: str) -> None:
    public.setdefault(module, set()).add(name)


def reexports(package: Path, public: dict[str, set[str]]) -> list[str]:
    init = package / "__init__.py"
    if not init.exists():
        return []
    tree = ast.parse(init.read_text())
    exported = declared_all(tree)
    names = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            source = absolute(package, package.name, node)
            if source is None:
                continue
            for alias in node.names:
                name = alias.asname or alias.name
                if not name.startswith("_") and (exported is None or name in exported):
                    if is_module(package, f"{source}.{alias.name}"):
                        add(public, f"{source}.{alias.name}", WHOLE_MODULE)
                    else:
                        add(public, source, alias.name)
                    names.append(name)
    return names


def entry_points(package: Path, public: dict[str, set[str]]) -> list[str]:
    pyproject = project_root(package) / "pyproject.toml"
    if not pyproject.exists():
        return []
    if tomllib is None:
        sys.stderr.write(
            f"public_api_digest: Python {sys.version_info[0]}.{sys.version_info[1]} cannot read {pyproject}; "
            "entry points are not used as evidence (run with Python 3.11+)\n"
        )
        return []
    project = tomllib.loads(pyproject.read_text()).get("project", {})
    groups = {**project.get("entry-points", {})}
    for table in ("scripts", "gui-scripts"):
        if project.get(table):
            groups[f"[project.{table}]"] = project[table]
    lines = []
    for group, items in groups.items():
        for name, target in items.items():
            module, _, attr = target.partition(":")
            if module == package.name or module.startswith(package.name + "."):
                add(public, module, attr.split(".")[0] if attr else WHOLE_MODULE)
            lines.append(f"`{group}`: `{name} = {target}`")
    return lines


def is_test_file(path: Path) -> bool:
    return (
        bool({"tests", "test", "tests_private", "testing"} & set(path.parts))
        or path.name.startswith("test_")
        or (path.name.endswith("_test.py") or path.name == "conftest.py")
    )


def consumer_imports(package: Path, root: Path, public: dict[str, set[str]], tests_only: set[str]) -> int:
    """Record what production code outside the package's project imports; return how many files do.

    Modules imported only by test files go to `tests_only` instead, as a hint.
    """
    own = project_root(package)
    pattern = re.compile(rf"\b{re.escape(package.name)}\b")
    files = 0
    for path in root.rglob("*.py"):
        if SKIP_DIRS & set(path.parts) or own in path.parents:
            continue
        in_tests = is_test_file(path.relative_to(root))
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if not pattern.search(text):
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        before = sum(len(v) for v in public.values())
        target: dict[str, set[str]] = {} if in_tests else public
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if node.module == package.name or node.module.startswith(package.name + "."):
                    for alias in node.names:
                        submodule = f"{node.module}.{alias.name}"
                        if alias.name == "*":
                            add(target, node.module, WHOLE_MODULE)
                        elif (package / Path(*submodule.split(".")[1:])).with_suffix(".py").exists() or (
                            package / Path(*submodule.split(".")[1:]) / "__init__.py"
                        ).exists():
                            add(target, submodule, WHOLE_MODULE)
                        else:
                            add(target, node.module, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(package.name + "."):
                        add(target, alias.name, WHOLE_MODULE)
        if in_tests:
            tests_only.update(target)
        else:
            files += sum(len(v) for v in public.values()) > before
    return files


def source_lines(text: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The decorators and `def` header as written, up to the colon that opens the body; no comments, no body.

    The header ends at the first `:` token outside brackets after `def`, found with `tokenize`, so colons in
    annotations, default dicts, lambdas and strings are never mistaken for it.
    """
    lines = text.splitlines(keepends=True)
    first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
    chunk = "".join(lines[node.lineno - 1 : node.body[0].lineno])
    depth, end = 0, None
    try:
        for token in tokenize.generate_tokens(io.StringIO(chunk).readline):
            if token.type == tokenize.OP and token.string in "([{":
                depth += 1
            elif token.type == tokenize.OP and token.string in ")]}":
                depth -= 1
            elif token.type == tokenize.OP and token.string == ":" and depth == 0:
                end = token.start
                break
    except (tokenize.TokenError, IndentationError):
        end = None
    if end is None:
        return ast.unparse(node).split("\n")[0].rstrip(":")
    row, col = end
    header = [*lines[first - 1 : node.lineno - 1], *chunk.splitlines(keepends=True)[: row - 1]]
    header.append(chunk.splitlines(keepends=True)[row - 1][:col])
    header = [line.rstrip("\n") for line in header]
    indent = len(header[0]) - len(header[0].lstrip())
    return "\n".join(line[indent:] for line in header).rstrip()


def raised(node: ast.AST) -> list[str]:
    found = []
    for child in ast.walk(node):
        is_call = isinstance(child, ast.Raise) and isinstance(child.exc, ast.Call) and child.exc.args
        if is_call and isinstance(child.exc.args[0], (ast.Constant, ast.JoinedStr)):
            found.append(ast.unparse(child.exc))
    return list(dict.fromkeys(found))


def describe_function(text: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    lines = ["```python", source_lines(text, node), "```"]
    doc = ast.get_docstring(node)
    if doc:
        lines += [f"> {line}" if line else ">" for line in doc.splitlines()]
    errors = raised(node)
    if errors:
        lines.append("Raises: " + "; ".join(f"`{e}`" for e in errors))
    return [*lines, ""]


def factory_built(tree_by_module: dict[str, ast.Module], public: dict[str, set[str]]) -> set[str]:
    """Names of public classes some public function or method returns: callers get them from a factory."""
    built = set()
    for mod, wanted in public.items():
        tree = tree_by_module.get(mod)
        for name, node in top_level(tree) if tree else []:
            if WHOLE_MODULE not in wanted and name not in wanted:
                continue
            functions = [node] if not isinstance(node, ast.ClassDef) else node.body
            for item in functions:
                is_public = isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_")
                if is_public and item.returns is not None:
                    built |= {ref.id for ref in ast.walk(item.returns) if isinstance(ref, ast.Name)}
    return built


FACTORY_BUILT: set[str] = set()


def shown_dunders(node: ast.ClassDef | ast.AST) -> set[str]:
    """Dunder methods the digest shows for a class. A class callers get from a factory hides its `__init__`:
    showing it would pull its internal state types into the public surface."""
    name = getattr(node, "name", None)
    return DUNDER_METHODS - {"__init__"} if name in FACTORY_BUILT else DUNDER_METHODS


def describe_class(text: str, node: ast.ClassDef) -> list[str]:
    bases = f"({', '.join(ast.unparse(b) for b in node.bases)})" if node.bases else ""
    decorators = "".join(f"@{ast.unparse(d)} " for d in node.decorator_list)
    lines = [f"### `{decorators}class {node.name}{bases}`", ""]
    doc = ast.get_docstring(node)
    if doc:
        lines += [*(f"> {line}" if line else ">" for line in doc.splitlines()), ""]
    fields = [
        f"- `{ast.unparse(item)}`"
        for item in node.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and not item.target.id.startswith("_")
    ]
    if fields:
        lines += ["Fields:", "", *fields, ""]
    for item in node.body:
        is_function = isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        if is_function and (not item.name.startswith("_") or item.name in shown_dunders(node)):
            lines += describe_function(text, item)
    return lines


def top_level(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    found = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append((node.name, node))
        elif isinstance(node, ast.Assign):
            found += [(t.id, node) for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.append((node.target.id, node))
    return [(name, node) for name, node in found if not name.startswith("_")]


def referenced_types(package: Path, public: dict[str, set[str]]) -> None:
    """Add package-defined names used in public signatures, fields and bases, until nothing new appears."""
    modules = {module_name(package, p): ast.parse(p.read_text()) for p in package.rglob("*.py")}
    defined = {name: mod for mod, tree in modules.items() for name, _ in top_level(tree)}
    imported: dict[str, dict[str, str]] = {}
    for mod, tree in modules.items():
        for node in tree.body:
            source = absolute(package, mod, node) if isinstance(node, ast.ImportFrom) else None
            if source and (source == package.name or source.startswith(package.name + ".")):
                for alias in node.names:
                    imported.setdefault(mod, {})[alias.asname or alias.name] = source
    changed = True
    while changed:
        changed = False
        for mod, wanted in list(public.items()):
            tree = modules.get(mod)
            if tree is None:
                continue
            for name, node in top_level(tree):
                if WHOLE_MODULE not in wanted and name not in wanted:
                    continue
                parts = [node] if not isinstance(node, ast.ClassDef) else [*node.bases, *node.body]
                for part in parts:
                    # Every signature the digest shows must be usable: the types of every shown method count.
                    is_function = isinstance(part, (ast.FunctionDef, ast.AsyncFunctionDef))
                    if is_function and part.name.startswith("_") and part.name not in shown_dunders(node):
                        continue
                    if is_function:
                        roots = [part.args, part.returns]
                    elif isinstance(part, ast.ClassDef):
                        roots = []
                    else:
                        roots = [part]
                    for root in filter(None, roots):
                        for ref in ast.walk(root):
                            if not isinstance(ref, ast.Name):
                                continue
                            source = imported.get(mod, {}).get(ref.id) or (
                                mod if ref.id in dict(top_level(tree)) else None
                            )
                            source = source if source in modules else defined.get(ref.id) if source else None
                            if source and ref.id not in public.get(source, set()) and ref.id in defined:
                                add(public, source, ref.id)
                                changed = True


def digest(package: Path, consumers: Path | None, declared: list[str], only: list[Path]) -> str:
    public: dict[str, set[str]] = {}
    exported = reexports(package, public)
    points = entry_points(package, public)
    tests_only: set[str] = set()
    consumer_files = consumer_imports(package, consumers, public, tests_only) if consumers else 0
    for item in declared:
        module, _, name = item.partition(":")
        add(public, module, name or WHOLE_MODULE)
    fallback = not public
    if not fallback:
        trees = {module_name(package, p): ast.parse(p.read_text()) for p in package.rglob("*.py")}
        FACTORY_BUILT.clear()
        FACTORY_BUILT.update(factory_built(trees, public))
        referenced_types(package, public)
    out = [f"# Public API of `{package.name}`", ""]
    if fallback:
        out += [
            (
                "No export evidence (no `__init__` re-exports, entry points or outside imports): this lists every "
                "non-underscore name of every non-underscore module. Ask before relying on a module that looks internal."
            ),
            "",
        ]
    else:
        evidence = [f"`{package.name}` re-exports" * bool(exported), "entry points" * bool(points)]
        evidence.append(f"imports by {consumer_files} non-test files outside the package" * bool(consumer_files))
        evidence.append("declared with --public" * bool(declared))
        out += [
            "Public means used by callers: " + ", ".join(e for e in evidence if e) + ". Anything not listed "
            "here is internal: do not import it, even if its name has no underscore.",
            "",
        ]
    hint = sorted(tests_only - set(public))
    if hint:
        sys.stderr.write(
            "public_api_digest: imported only by tests elsewhere, left out (add with --public if they are test "
            f"helpers): {', '.join(hint)}\n"
        )
    if exported:
        out += [f"Import these from `{package.name}`: " + ", ".join(f"`{n}`" for n in sorted(exported)), ""]
    if points:
        out += ["Entry points:", "", *(f"- {p}" for p in points), ""]
    only_names = {module_name(package, p.resolve()) for p in only}
    for path in sorted(package.rglob("*.py")):
        name = module_name(package, path)
        if (only_names and name not in only_names) or SKIP_DIRS & set(path.parts):
            continue
        text = path.read_text()
        tree = ast.parse(text)
        if fallback:
            if any(part.startswith("_") for part in name.split(".")[1:]):
                continue
            own_all = declared_all(tree)
            nodes = [(n, node) for n, node in top_level(tree) if own_all is None or n in own_all]
        else:
            wanted = public.get(name, set())
            nodes = [(n, node) for n, node in top_level(tree) if WHOLE_MODULE in wanted or n in wanted]
        if not nodes:
            continue
        out += [f"## `{name}`", ""]
        doc = ast.get_docstring(tree)
        if doc:
            out += [*(f"> {line}" if line else ">" for line in doc.splitlines()), ""]
        constants = [f"- `{ast.unparse(node)}`" for _, node in nodes if isinstance(node, (ast.Assign, ast.AnnAssign))]
        if constants:
            out += ["Constants:", "", *dict.fromkeys(constants), ""]
        for n, node in nodes:
            if isinstance(node, ast.ClassDef):
                out += describe_class(text, node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out += [f"### `{n}`", "", *describe_function(text, node)]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", type=Path, help="the package directory, e.g. src/mypkg")
    parser.add_argument("--consumers", type=Path, help="repo root to scan for imports of the package by other code")
    parser.add_argument("--public", nargs="*", default=[], help="extra public surface: module or module:name")
    parser.add_argument("--only", nargs="*", type=Path, default=[], help="limit to these module files (changed code)")
    parser.add_argument("--out", type=Path, help="write here instead of stdout")
    args = parser.parse_args(argv)
    package = args.package.resolve()
    if not (package.is_dir() and any(package.glob("*.py"))):
        print(f"public_api_digest: {args.package} is not a Python package directory", file=sys.stderr)
        return 2
    text = digest(package, args.consumers.resolve() if args.consumers else None, args.public, args.only)
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
