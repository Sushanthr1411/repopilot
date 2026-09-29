"""
Comprehensive parser tests.

All tests operate on in-memory source strings or fixture files.
No database or external services are required.

Fixture files live in tests/fixtures/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parser import (
    ParsedFile,
    ParsedSymbol,
    parse_file,
    parse_repository,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _symbols_by_qname(result: ParsedFile) -> dict[str, ParsedSymbol]:
    return {s.qualified_name: s for s in result.symbols}


def _rels(result: ParsedFile, rel_type: str) -> list[tuple[str, str]]:
    return [
        (r.source_qualified_name, r.target_ref)
        for r in result.relationships
        if r.relationship_type == rel_type
    ]


# ---------------------------------------------------------------------------
# 1. Basic module parsing
# ---------------------------------------------------------------------------

class TestModuleParsing:
    def test_success(self):
        result = parse_file(_read("simple.py"), "simple.py")
        assert result.success is True
        assert result.language == "python"
        assert not result.errors

    def test_module_symbol_present(self):
        result = parse_file(_read("simple.py"), "simple.py")
        syms = _symbols_by_qname(result)
        assert "simple" in syms

    def test_module_symbol_type(self):
        result = parse_file(_read("simple.py"), "simple.py")
        assert _symbols_by_qname(result)["simple"].symbol_type == "module"

    def test_module_symbol_covers_whole_file(self):
        result = parse_file(_read("simple.py"), "simple.py")
        mod = _symbols_by_qname(result)["simple"]
        assert mod.start_line == 1
        assert mod.end_line >= 1

    def test_module_docstring(self):
        result = parse_file(_read("simple.py"), "simple.py")
        mod = _symbols_by_qname(result)["simple"]
        assert mod.docstring is not None
        assert "simple module" in mod.docstring.lower()

    def test_module_name_from_path(self):
        result = parse_file(_read("simple.py"), "simple.py")
        assert result.module_name == "simple"

    def test_module_name_nested_path(self):
        result = parse_file(_read("simple.py"), "services/auth.py")
        assert result.module_name == "services.auth"

    def test_module_name_init(self):
        result = parse_file("", "services/__init__.py")
        assert result.module_name == "services"

    def test_file_path_preserved(self):
        result = parse_file(_read("simple.py"), "my/custom/path.py")
        assert result.file_path == "my/custom/path.py"


# ---------------------------------------------------------------------------
# 2. Import extraction
# ---------------------------------------------------------------------------

class TestImports:
    def _result(self):
        return parse_file(_read("imports_sample.py"), "imports_sample.py")

    def test_plain_import(self):
        result = self._result()
        names = [i.name for i in result.imports]
        assert "os" in names

    def test_plain_import_no_module(self):
        result = self._result()
        imp = next(i for i in result.imports if i.name == "os")
        assert imp.module is None
        assert imp.level == 0
        assert imp.alias is None

    def test_import_alias(self):
        result = self._result()
        imp = next(i for i in result.imports if i.name == "sys")
        assert imp.alias == "system"

    def test_from_import(self):
        result = self._result()
        names = [i.name for i in result.imports]
        assert "Path" in names

    def test_from_import_module(self):
        result = self._result()
        imp = next(i for i in result.imports if i.name == "Path")
        assert imp.module == "pathlib"

    def test_from_import_multiple(self):
        result = self._result()
        names = [i.name for i in result.imports]
        assert "OrderedDict" in names
        assert "defaultdict" in names

    def test_relative_import_level_preserved(self):
        result = self._result()
        imp = next(i for i in result.imports if i.name == "authenticate")
        assert imp.level == 2

    def test_relative_import_module(self):
        result = self._result()
        imp = next(i for i in result.imports if i.name == "authenticate")
        assert imp.module is not None
        assert "services.auth" in imp.module

    def test_relative_import_level_one(self):
        result = self._result()
        imp = next(i for i in result.imports if i.name == "utils")
        assert imp.level == 1

    def test_type_checking_imports_extracted(self):
        result = self._result()
        names = [i.name for i in result.imports]
        assert "Optional" in names

    def test_imports_relationship_emitted(self):
        result = self._result()
        targets = [r.target_ref for r in result.relationships if r.relationship_type == "IMPORTS"]
        assert "os" in targets

    def test_from_imports_relationship_emitted(self):
        result = self._result()
        targets = [r.target_ref for r in result.relationships if r.relationship_type == "IMPORTS"]
        assert any("authenticate" in t for t in targets)

    def test_imports_relationship_confidence(self):
        result = self._result()
        for r in result.relationships:
            if r.relationship_type == "IMPORTS":
                assert r.confidence == 1.0


# ---------------------------------------------------------------------------
# 3. Symbol extraction — classes and functions
# ---------------------------------------------------------------------------

class TestSymbolExtraction:
    def _result(self):
        return parse_file(_read("simple.py"), "simple.py")

    def test_function_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "greet" in syms

    def test_function_type(self):
        syms = _symbols_by_qname(self._result())
        assert syms["greet"].symbol_type == "function"

    def test_second_function_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "add" in syms

    def test_class_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "Calculator" in syms

    def test_class_type(self):
        syms = _symbols_by_qname(self._result())
        assert syms["Calculator"].symbol_type == "class"

    def test_method_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "Calculator.add" in syms

    def test_method_type(self):
        syms = _symbols_by_qname(self._result())
        assert syms["Calculator.add"].symbol_type == "method"

    def test_init_method_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "Calculator.__init__" in syms

    def test_subtract_method_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "Calculator.subtract" in syms


# ---------------------------------------------------------------------------
# 4. Qualified names
# ---------------------------------------------------------------------------

class TestQualifiedNames:
    def test_module_level_function(self):
        result = parse_file(_read("simple.py"), "simple.py")
        syms = _symbols_by_qname(result)
        assert syms["greet"].name == "greet"
        assert syms["greet"].qualified_name == "greet"

    def test_class_qualified_name(self):
        result = parse_file(_read("simple.py"), "simple.py")
        syms = _symbols_by_qname(result)
        assert syms["Calculator"].qualified_name == "Calculator"

    def test_method_qualified_name(self):
        result = parse_file(_read("simple.py"), "simple.py")
        syms = _symbols_by_qname(result)
        assert syms["Calculator.add"].qualified_name == "Calculator.add"

    def test_nested_function_qualified_name(self):
        result = parse_file(_read("nested_sample.py"), "nested_sample.py")
        syms = _symbols_by_qname(result)
        assert "outer.inner" in syms

    def test_nested_class_qualified_name(self):
        result = parse_file(_read("nested_sample.py"), "nested_sample.py")
        syms = _symbols_by_qname(result)
        assert "Outer.Inner" in syms

    def test_nested_class_method_qualified_name(self):
        result = parse_file(_read("nested_sample.py"), "nested_sample.py")
        syms = _symbols_by_qname(result)
        assert "Outer.Inner.method" in syms

    def test_deeply_nested_function(self):
        result = parse_file(_read("nested_sample.py"), "nested_sample.py")
        syms = _symbols_by_qname(result)
        assert "double_nested.middle.deep" in syms


# ---------------------------------------------------------------------------
# 5. Line ranges
# ---------------------------------------------------------------------------

class TestLineRanges:
    def test_function_start_line(self):
        result = parse_file(_read("simple.py"), "simple.py")
        greet = _symbols_by_qname(result)["greet"]
        assert greet.start_line >= 1

    def test_function_end_line_after_start(self):
        result = parse_file(_read("simple.py"), "simple.py")
        greet = _symbols_by_qname(result)["greet"]
        assert greet.end_line >= greet.start_line

    def test_class_end_line_after_start(self):
        result = parse_file(_read("simple.py"), "simple.py")
        calc = _symbols_by_qname(result)["Calculator"]
        assert calc.end_line > calc.start_line

    def test_method_inside_class_lines(self):
        result = parse_file(_read("simple.py"), "simple.py")
        calc = _symbols_by_qname(result)["Calculator"]
        add = _symbols_by_qname(result)["Calculator.add"]
        assert add.start_line > calc.start_line
        assert add.end_line <= calc.end_line


# ---------------------------------------------------------------------------
# 6. Docstrings
# ---------------------------------------------------------------------------

class TestDocstrings:
    def test_function_docstring(self):
        result = parse_file(_read("simple.py"), "simple.py")
        greet = _symbols_by_qname(result)["greet"]
        assert greet.docstring is not None
        assert "Greet" in greet.docstring

    def test_class_docstring(self):
        result = parse_file(_read("simple.py"), "simple.py")
        calc = _symbols_by_qname(result)["Calculator"]
        assert calc.docstring is not None
        assert "calculator" in calc.docstring.lower()

    def test_method_docstring(self):
        result = parse_file(_read("simple.py"), "simple.py")
        add = _symbols_by_qname(result)["Calculator.add"]
        assert add.docstring is not None
        assert "Add" in add.docstring

    def test_no_docstring_is_none(self):
        result = parse_file(_read("simple.py"), "simple.py")
        sub = _symbols_by_qname(result)["Calculator.subtract"]
        assert sub.docstring is None


# ---------------------------------------------------------------------------
# 7. Signatures
# ---------------------------------------------------------------------------

class TestSignatures:
    def _result(self):
        return parse_file(_read("signatures_sample.py"), "signatures_sample.py")

    def test_no_args_signature(self):
        syms = _symbols_by_qname(self._result())
        assert syms["no_args"].signature == "no_args() -> None"

    def test_simple_signature(self):
        syms = _symbols_by_qname(self._result())
        sig = syms["simple"].signature
        assert sig is not None
        assert "simple" in sig
        assert "x" in sig
        assert "y" in sig

    def test_annotated_signature(self):
        syms = _symbols_by_qname(self._result())
        sig = syms["annotated"].signature
        assert "str" in sig
        assert "int" in sig
        assert "18" in sig
        assert "-> str" in sig

    def test_varargs_signature(self):
        syms = _symbols_by_qname(self._result())
        sig = syms["with_varargs"].signature
        assert "*args" in sig
        assert "**kwargs" in sig

    def test_keyword_only_signature(self):
        syms = _symbols_by_qname(self._result())
        sig = syms["keyword_only"].signature
        assert "key" in sig
        assert "'default'" in sig or '"default"' in sig

    def test_positional_only_signature(self):
        syms = _symbols_by_qname(self._result())
        sig = syms["pos_only"].signature
        assert "/" in sig

    def test_method_signature(self):
        syms = _symbols_by_qname(self._result())
        sig = syms["MyClass.method"].signature
        assert "self" in sig
        assert "value" in sig

    def test_return_annotation(self):
        syms = _symbols_by_qname(self._result())
        sig = syms["no_args"].signature
        assert "-> None" in sig

    def test_signature_stored_on_symbol(self):
        result = parse_file(_read("simple.py"), "simple.py")
        greet = _symbols_by_qname(result)["greet"]
        assert greet.signature is not None
        assert "name" in greet.signature
        assert "str" in greet.signature


# ---------------------------------------------------------------------------
# 8. Inheritance
# ---------------------------------------------------------------------------

class TestInheritance:
    def _result(self):
        return parse_file(_read("inheritance_sample.py"), "inheritance_sample.py")

    def test_single_inheritance(self):
        inherits = _rels(self._result(), "INHERITS")
        assert ("Dog", "Animal") in inherits

    def test_chained_inheritance(self):
        inherits = _rels(self._result(), "INHERITS")
        assert ("ServiceDog", "Dog") in inherits

    def test_multiple_inheritance(self):
        inherits = _rels(self._result(), "INHERITS")
        sources = [s for s, _ in inherits]
        assert sources.count("MultiBase") == 2

    def test_multiple_inheritance_both_bases(self):
        inherits = _rels(self._result(), "INHERITS")
        multi = {t for s, t in inherits if s == "MultiBase"}
        assert "Animal" in multi
        assert "Dog" in multi

    def test_no_base_no_inherits(self):
        inherits = _rels(self._result(), "INHERITS")
        animal_inherits = [t for s, t in inherits if s == "Animal"]
        assert len(animal_inherits) == 0

    def test_inherits_confidence(self):
        for r in self._result().relationships:
            if r.relationship_type == "INHERITS":
                assert r.confidence == 1.0


# ---------------------------------------------------------------------------
# 9. Async functions
# ---------------------------------------------------------------------------

class TestAsync:
    def _result(self):
        return parse_file(_read("async_sample.py"), "async_sample.py")

    def test_async_function_type(self):
        syms = _symbols_by_qname(self._result())
        assert syms["fetch_data"].symbol_type == "async_function"

    def test_second_async_function(self):
        syms = _symbols_by_qname(self._result())
        assert syms["process_batch"].symbol_type == "async_function"

    def test_async_method_type_is_method(self):
        syms = _symbols_by_qname(self._result())
        assert syms["AsyncService.process"].symbol_type == "method"

    def test_async_class_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "AsyncService" in syms

    def test_async_signature_preserved(self):
        syms = _symbols_by_qname(self._result())
        sig = syms["fetch_data"].signature
        assert "url" in sig
        assert "dict" in sig


# ---------------------------------------------------------------------------
# 10. Nested symbols
# ---------------------------------------------------------------------------

class TestNested:
    def _result(self):
        return parse_file(_read("nested_sample.py"), "nested_sample.py")

    def test_outer_function_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "outer" in syms

    def test_inner_function_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "outer.inner" in syms

    def test_inner_is_function_not_method(self):
        syms = _symbols_by_qname(self._result())
        assert syms["outer.inner"].symbol_type == "function"

    def test_outer_class_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "Outer" in syms

    def test_inner_class_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "Outer.Inner" in syms

    def test_inner_class_is_class(self):
        syms = _symbols_by_qname(self._result())
        assert syms["Outer.Inner"].symbol_type == "class"

    def test_inner_class_method_extracted(self):
        syms = _symbols_by_qname(self._result())
        assert "Outer.Inner.method" in syms

    def test_inner_class_method_is_method(self):
        syms = _symbols_by_qname(self._result())
        assert syms["Outer.Inner.method"].symbol_type == "method"


# ---------------------------------------------------------------------------
# 11. DEFINES relationships
# ---------------------------------------------------------------------------

class TestDefines:
    def _result(self):
        return parse_file(_read("simple.py"), "simple.py")

    def test_module_defines_function(self):
        defines = _rels(self._result(), "DEFINES")
        sources = [s for s, t in defines if t == "greet"]
        assert any("simple" in s for s in sources)

    def test_module_defines_class(self):
        defines = _rels(self._result(), "DEFINES")
        sources = [s for s, t in defines if t == "Calculator"]
        assert any("simple" in s for s in sources)

    def test_class_defines_method(self):
        defines = _rels(self._result(), "DEFINES")
        assert ("Calculator", "Calculator.add") in defines

    def test_defines_confidence(self):
        for r in self._result().relationships:
            if r.relationship_type == "DEFINES":
                assert r.confidence == 1.0


# ---------------------------------------------------------------------------
# 12. CALLS relationships
# ---------------------------------------------------------------------------

class TestCalls:
    def _result(self):
        return parse_file(_read("calls_sample.py"), "calls_sample.py")

    def test_direct_call_extracted(self):
        calls = _rels(self._result(), "CALLS")
        targets = [t for s, t in calls if s == "UserService.create_user"]
        assert "authenticate" in targets

    def test_second_direct_call(self):
        calls = _rels(self._result(), "CALLS")
        targets = [t for s, t in calls if s == "UserService.create_user"]
        assert "save_user" in targets

    def test_self_method_call_resolved_to_class(self):
        calls = _rels(self._result(), "CALLS")
        targets = [t for s, t in calls if s == "UserService.create_user"]
        assert "UserService.notify" in targets

    def test_direct_call_confidence(self):
        for r in self._result().relationships:
            if r.relationship_type == "CALLS":
                s, t = r.source_qualified_name, r.target_ref
                if s == "UserService.create_user" and t == "authenticate":
                    assert r.confidence == pytest.approx(0.9)

    def test_self_call_confidence_lower_than_direct(self):
        for r in self._result().relationships:
            if r.relationship_type == "CALLS":
                if r.target_ref == "UserService.notify":
                    assert r.confidence < 0.9

    def test_no_calls_at_module_level(self):
        """Calls that occur outside any function should not be emitted."""
        src = "x = len([1, 2, 3])\n"
        result = parse_file(src, "top.py")
        calls = [r for r in result.relationships if r.relationship_type == "CALLS"]
        assert len(calls) == 0

    def test_calls_in_nested_function_attributed_correctly(self):
        src = "def outer():\n    def inner():\n        foo()\n"
        result = parse_file(src, "t.py")
        calls = _rels(result, "CALLS")
        assert any(s == "outer.inner" and t == "foo" for s, t in calls)
        assert not any(s == "outer" and t == "foo" for s, t in calls)


# ---------------------------------------------------------------------------
# 13. Syntax errors
# ---------------------------------------------------------------------------

class TestSyntaxErrors:
    def test_success_false_on_syntax_error(self):
        result = parse_file(_read("syntax_error_input.py"), "syntax_error_input.py")
        assert result.success is False

    def test_error_list_non_empty(self):
        result = parse_file(_read("syntax_error_input.py"), "syntax_error_input.py")
        assert len(result.errors) >= 1

    def test_error_type_is_syntax_error(self):
        result = parse_file(_read("syntax_error_input.py"), "syntax_error_input.py")
        assert result.errors[0].error_type == "SyntaxError"

    def test_error_has_message(self):
        result = parse_file(_read("syntax_error_input.py"), "syntax_error_input.py")
        assert result.errors[0].message

    def test_error_has_line(self):
        result = parse_file(_read("syntax_error_input.py"), "syntax_error_input.py")
        assert result.errors[0].line is not None

    def test_no_symbols_on_syntax_error(self):
        result = parse_file(_read("syntax_error_input.py"), "syntax_error_input.py")
        assert result.symbols == []

    def test_inline_syntax_error(self):
        result = parse_file("def f(: pass", "bad.py")
        assert result.success is False

    def test_language_still_set_on_error(self):
        result = parse_file("???", "bad.py")
        assert result.language == "python"


# ---------------------------------------------------------------------------
# 14. Empty files
# ---------------------------------------------------------------------------

class TestEmptyFiles:
    def test_empty_file_succeeds(self):
        result = parse_file(_read("empty.py"), "empty.py")
        assert result.success is True

    def test_empty_file_has_module_symbol(self):
        result = parse_file(_read("empty.py"), "empty.py")
        assert len(result.symbols) == 1
        assert result.symbols[0].symbol_type == "module"

    def test_empty_file_no_imports(self):
        result = parse_file(_read("empty.py"), "empty.py")
        assert result.imports == []

    def test_empty_file_no_relationships(self):
        result = parse_file(_read("empty.py"), "empty.py")
        assert result.relationships == []

    def test_comments_only_succeeds(self):
        src = "# just a comment\n# another comment\n"
        result = parse_file(src, "comments.py")
        assert result.success is True


# ---------------------------------------------------------------------------
# 15. Repository traversal
# ---------------------------------------------------------------------------

class TestRepositoryTraversal:
    def _results(self) -> dict[str, ParsedFile]:
        results = parse_repository(FIXTURES / "repo")
        return {r.file_path: r for r in results}

    def test_finds_python_files(self):
        results = self._results()
        assert len(results) >= 4  # __init__ x2 + auth.py + user.py

    def test_services_auth_found(self):
        results = self._results()
        paths = list(results.keys())
        assert any("auth.py" in p for p in paths)

    def test_models_user_found(self):
        results = self._results()
        paths = list(results.keys())
        assert any("user.py" in p for p in paths)

    def test_module_names_use_dotted_paths(self):
        results = self._results()
        module_names = {r.module_name for r in results.values()}
        assert "services.auth" in module_names
        assert "models.user" in module_names

    def test_init_module_names(self):
        results = self._results()
        module_names = {r.module_name for r in results.values()}
        assert "services" in module_names
        assert "models" in module_names

    def test_symbols_extracted_from_traversal(self):
        results = self._results()
        auth = next(r for r in results.values() if "auth.py" in r.file_path)
        qnames = {s.qualified_name for s in auth.symbols}
        assert "authenticate" in qnames

    def test_all_files_succeed(self):
        for result in self._results().values():
            assert result.success is True

    def test_ignores_venv(self, tmp_path):
        """Files under .venv must not be parsed."""
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "should_skip.py").write_text("x = 1")
        (tmp_path / "real.py").write_text("y = 2")
        results = parse_repository(tmp_path)
        paths = [r.file_path for r in results]
        assert any("real.py" in p for p in paths)
        assert not any("should_skip.py" in p for p in paths)

    def test_ignores_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "cached.py").write_text("z = 3")
        (tmp_path / "source.py").write_text("w = 4")
        results = parse_repository(tmp_path)
        paths = [r.file_path for r in results]
        assert any("source.py" in p for p in paths)
        assert not any("cached.py" in p for p in paths)

    def test_skips_non_py_files(self, tmp_path):
        (tmp_path / "notes.txt").write_text("hello")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "module.py").write_text("pass")
        results = parse_repository(tmp_path)
        assert len(results) == 1
        assert "module.py" in results[0].file_path
