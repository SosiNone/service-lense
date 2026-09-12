"""Tree-sitter adapters normalize syntax without executing analyzed source."""
from __future__ import annotations

import ast
import re

from tree_sitter import Language, Node, Parser

from .model import Binding, Call, Expr, Function, Import, Location, Unit

CALLS = {"call", "call_expression", "invocation_expression", "object_creation_expression", "new_expression"}
FUNCTIONS = {"function_definition", "function_declaration", "method_declaration", "local_function_statement",
             "arrow_function", "function_expression", "method_definition", "constructor_declaration"}
MEMBERS = {"attribute", "member_expression", "member_access_expression", "qualified_name"}


def field(node: Node, *names: str) -> Node | None:
    for name in names:
        value = node.child_by_field_name(name)
        if value is not None:
            return value
    return None


def walk(node: Node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


class TreeAdapter:
    def __init__(self, language: str, tsx: bool = False):
        self.language = language
        if language == "python":
            import tree_sitter_python
            grammar = tree_sitter_python.language()
        elif language == "typescript":
            import tree_sitter_typescript
            grammar = tree_sitter_typescript.language_tsx() if tsx else tree_sitter_typescript.language_typescript()
        else:
            import tree_sitter_c_sharp
            grammar = tree_sitter_c_sharp.language()
        self.parser = Parser(Language(grammar))

    def text(self, node: Node | None) -> str:
        return self.source[node.start_byte:node.end_byte].decode("utf-8", errors="replace") if node else ""

    def loc(self, node: Node) -> Location:
        return Location(self.unit.path, node.start_point.row + 1, node.start_point.column + 1)

    def parse(self, path: str, source: bytes) -> Unit:
        self.source = source
        self.unit = Unit(path, self.language)
        self._expression_cache: dict[int, Expr] = {}
        root = self.parser.parse(source).root_node
        errors = [n for n in walk(root) if n.type == "ERROR" or n.is_missing]
        for node in errors[:20]:
            self.unit.diagnostics.append({"code": "parse_error", "file": path, "line": node.start_point.row + 1,
                                          "message": "Syntax could not be parsed; findings may be incomplete."})
        self.visit(root, "")
        return self.unit

    def expression(self, node: Node | None) -> Expr:
        if node is None:
            return Expr("unknown", "value")
        if node.id not in self._expression_cache:
            self._expression_cache[node.id] = self._expression(node)
        return self._expression_cache[node.id]

    def _expression(self, node: Node) -> Expr:
        kind, text, loc = node.type, self.text(node), self.loc(node)
        children = node.named_children
        if kind in {"identifier", "property_identifier", "dotted_name", "implicit_parameter", "this", "this_expression"}:
            return Expr("ref", text, loc=loc)
        if kind == "generic_name":
            return Expr("ref", text, loc=loc)
        if kind in {"string", "string_literal", "verbatim_string_literal", "raw_string_literal", "template_string",
                    "interpolated_string_expression", "concatenated_string"}:
            substitutions = [c for c in children if c.type in {"interpolation", "template_substitution"}]
            if substitutions:
                parts = []
                for child in children:
                    if child.type in {"string_content", "string_fragment", "string_literal_content"}:
                        parts.append(Expr("text", self.text(child), loc=self.loc(child)))
                    elif child.type in {"interpolation", "template_substitution"}:
                        inner = field(child, "expression") or next((c for c in child.named_children if c.type not in {
                            "interpolation_brace", "format_clause", "interpolation_alignment_clause"}), None)
                        parts.append(self.expression(inner))
                return Expr("concat", args=parts, loc=loc)
            if kind == "concatenated_string":
                return Expr("concat", args=[self.expression(c) for c in children], loc=loc)
            try:
                if self.language == "python":
                    value = ast.literal_eval(text)
                    return Expr("text", str(value), loc=loc)
            except (ValueError, SyntaxError):
                pass
            if text.startswith('@"'):
                value = text[2:-1].replace('""', '"')
            elif text.startswith('"""'):
                value = text.strip('"').strip("\r\n")
            else:
                value = re.sub(r"^[fFrRbBuU$]*(['\"`])", "", text)
                value = value[:-1]
                value = re.sub(r"\\(['\"`\\/])", r"\1", value)
                value = value.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
            return Expr("text", value, loc=loc)
        if kind in {"integer", "integer_literal", "number", "real_literal", "true", "false"}:
            return Expr("text", text, loc=loc)
        if kind in MEMBERS:
            obj = field(node, "object", "expression", "qualifier")
            member = field(node, "attribute", "property", "name")
            return Expr("member", self.text(member), [self.expression(obj)], loc=loc)
        if kind in {"subscript", "subscript_expression", "element_access_expression"}:
            obj = field(node, "value", "object", "expression")
            index = field(node, "subscript", "index")
            if index and index.type == "bracketed_argument_list":
                index = index.named_children[0] if index.named_children else None
            return Expr("index", args=[self.expression(obj), self.expression(index)], loc=loc)
        if kind in CALLS:
            fn = field(node, "function", "constructor", "type")
            arguments = field(node, "arguments")
            positional, keywords = [], {}
            for arg in arguments.named_children if arguments else []:
                if arg.type == "keyword_argument":
                    keywords[self.text(field(arg, "name"))] = self.expression(field(arg, "value"))
                elif arg.type == "argument" and field(arg, "name"):
                    keywords[self.text(field(arg, "name"))] = self.expression(arg.named_children[-1])
                else:
                    positional.append(self.expression(arg))
            initializer = field(node, "initializer")
            if initializer:
                for assignment in initializer.named_children:
                    if assignment.type == "assignment_expression":
                        keywords[self.text(field(assignment, "left"))] = self.expression(field(assignment, "right"))
            return Expr("call", args=[self.expression(fn), *positional], props=keywords, loc=loc)
        if kind in {"binary_expression", "binary_operator"}:
            left, right = field(node, "left"), field(node, "right")
            operator = self.source[left.end_byte:right.start_byte].decode().strip() if left and right else ""
            if operator == "+":
                return Expr("concat", args=[self.expression(left), self.expression(right)], loc=loc)
            return Expr("unknown", "expression", loc=loc)
        if kind in {"object", "dictionary", "initializer_expression"}:
            props = {}
            for child in children:
                if child.type in {"pair", "assignment_expression"}:
                    key = field(child, "key", "left")
                    props[self.text(key).strip("'\"")] = self.expression(field(child, "value", "right"))
                elif child.type == "shorthand_property_identifier":
                    props[self.text(child)] = Expr("ref", self.text(child), loc=self.loc(child))
            return Expr("object", props=props, loc=loc)
        if kind in {"argument", "await_expression", "await", "parenthesized_expression", "as_expression",
                    "non_null_expression", "arrow_expression_clause", "as_pattern_target"} and children:
            return self.expression(children[0] if kind != "argument" else children[-1])
        if kind in FUNCTIONS:
            return Expr("function", f"lambda@{loc.line}:{loc.column}", loc=loc)
        return Expr("unknown", "expression", loc=loc)

    def visit(self, node: Node, scope: str) -> None:
        kind = node.type
        if kind in {"comment", "string", "string_literal", "template_string", "interpolated_string_expression"}:
            # Calls inside substitutions still matter, plain string contents do not.
            for child in node.named_children:
                if child.type in {"interpolation", "template_substitution"}:
                    self.visit(child, scope)
            return
        if kind in {"import_statement", "import_from_statement", "using_directive"}:
            self.read_import(node, scope)
            return
        if kind == "export_statement" and re.match(r"export\s+default\b", self.text(node)):
            declaration = field(node, "declaration", "value")
            if declaration:
                name = field(declaration, "name")
                exported = Expr("ref", self.text(name), loc=self.loc(node)) if name else self.expression(declaration)
                self.unit.bindings.append(Binding("default", exported, scope))
        if kind in {"class_declaration", "class_definition", "namespace_declaration", "file_scoped_namespace_declaration"}:
            name = self.text(field(node, "name"))
            new_scope = f"{scope}/{name}" if scope else name
            self.unit.parents[new_scope] = scope
            for child in node.named_children:
                if child != field(node, "name"):
                    self.visit(child, new_scope)
            return
        if kind in FUNCTIONS:
            self.read_function(node, scope)
            return
        if kind in {"assignment", "assignment_expression", "variable_declarator"}:
            name_node = field(node, "left", "name")
            value_node = field(node, "right", "value")
            if value_node is None and kind == "variable_declarator":
                value_node = next((c for c in node.named_children if c != name_node), None)
            name = self.text(name_node)
            if name and re.fullmatch(r"[\w.]+", name):
                type_node = field(node.parent, "type") if node.parent else None
                target_scope = self.unit.parents.get(scope, scope) if name.startswith(("self.", "this.")) else scope
                self.unit.bindings.append(Binding(name, self.expression(value_node), target_scope, self.text(type_node)))
        if kind == "as_pattern":
            alias = field(node, "alias")
            if alias and node.named_children:
                self.unit.bindings.append(Binding(self.text(alias), self.expression(node.named_children[0]), scope))
        if kind in CALLS:
            expr = self.expression(node)
            self.unit.calls.append(Call(expr, scope))
            if self.language == "csharp":
                self.read_registration(node, expr, scope)
        if kind == "return_statement":
            fn = next((f for f in self.unit.functions if f.scope == scope), None)
            if fn and node.named_children:
                fn.returns.append(self.expression(node.named_children[0]))
        for child in node.named_children:
            self.visit(child, scope)

    def read_function(self, node: Node, parent: str) -> None:
        name_node = field(node, "name")
        if name_node is None and node.parent and node.parent.type == "variable_declarator":
            name_node = field(node.parent, "name")
        name = self.text(name_node) or f"lambda@{self.loc(node).line}:{self.loc(node).column}"
        if name_node is None and node.parent and node.parent.type == "export_statement" and re.match(r"export\s+default\b", self.text(node.parent)):
            name = "default"
        scope = f"{parent}/{name}@{node.start_byte}"
        params, defaults = [], {}
        parameters = field(node, "parameters", "parameter")
        for param in (parameters.named_children if parameters and parameters.type not in {"identifier", "implicit_parameter"}
                      else [parameters] if parameters else []):
            name_part = field(param, "name", "pattern")
            if name_part is None and param.type in {"identifier", "implicit_parameter"}:
                name_part = param
            if name_part is None and param.named_children:
                name_part = param.named_children[0]
            param_name = self.text(name_part)
            if param_name:
                params.append(param_name)
                default = field(param, "value")
                if default:
                    defaults[param_name] = self.expression(default)
                type_node = field(param, "type")
                if type_node:
                    self.unit.bindings.append(Binding(param_name, Expr("unknown", param_name, loc=self.loc(param)), scope,
                                                     self.text(type_node)))
        fn = Function(name, scope, parent, params, defaults, [], self.loc(node))
        self.unit.functions.append(fn)
        self.unit.parents[scope] = parent
        body = field(node, "body")
        if body:
            if body.type not in {"block", "statement_block"}:
                fn.returns.append(self.expression(body))
            self.visit(body, scope)

    def read_import(self, node: Node, scope: str) -> None:
        if self.language == "python":
            module = self.text(field(node, "module_name"))
            for child in node.named_children:
                if child == field(node, "module_name"):
                    continue
                if child.type not in {"dotted_name", "aliased_import"}:
                    continue
                name = self.text(field(child, "name")) if child.type == "aliased_import" else self.text(child)
                alias = self.text(field(child, "alias")) or (name if module else name.split(".")[0])
                self.unit.imports.append(Import(alias, module or name, name if module else "", scope))
        elif self.language == "typescript":
            source = field(node, "source")
            module = self.text(source).strip("'\"")
            for child in walk(node):
                if child.type == "import_specifier":
                    name = self.text(field(child, "name"))
                    self.unit.imports.append(Import(self.text(field(child, "alias")) or name, module, name, scope))
                elif child.type == "namespace_import":
                    self.unit.imports.append(Import(self.text(child.named_children[-1]), module, scope=scope))
                elif child.type == "import_clause":
                    for identifier in child.named_children:
                        if identifier.type == "identifier":
                            self.unit.imports.append(Import(self.text(identifier), module, "default", scope))
        else:
            text = self.text(node).removeprefix("global ").removeprefix("using ").rstrip(";").strip()
            if "=" in text:
                alias, module = map(str.strip, text.split("=", 1))
                self.unit.imports.append(Import(alias, module, scope=scope))
            else:
                self.unit.imports.append(Import("*", text, scope=scope))

    def read_registration(self, node: Node, expr: Expr, scope: str) -> None:
        if not expr.args or expr.args[0].kind != "member" or expr.args[0].value != "AddHttpClient":
            return
        if len(expr.args) < 2 or expr.args[1].kind != "text":
            self.unit.diagnostics.append({"code": "unsupported_registration", "file": self.unit.path,
                                          "line": expr.loc.line, "message": "Only named, literal AddHttpClient registrations are resolved."})
            return
        name = expr.args[1].value
        bases = [n for n in walk(node) if n.type == "assignment_expression"
                 and self.text(field(n, "left")).endswith(".BaseAddress")]
        for assignment in bases:
            self.unit.bindings.append(Binding("$httpclient:" + name, self.expression(field(assignment, "right")), scope))


def adapters() -> dict[str, TreeAdapter]:
    return {".py": TreeAdapter("python"), ".ts": TreeAdapter("typescript"),
            ".tsx": TreeAdapter("typescript", tsx=True), ".cs": TreeAdapter("csharp")}
