"""Conservative local value tracing shared by all language adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import posixpath
import re
from urllib.parse import urljoin

from .config import Configuration
from .model import Binding, Call, Expr, Function, Location, Unit, Value, merge_evidence

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "request", "send"}
PY_MODULES = {"requests", "httpx", "aiohttp", "urllib.parse", "os"}
TS_MODULES = {"axios", "http", "https", "node:http", "node:https"}
MAX_DEPTH = 3
MAX_CONTEXTS = 100


def dotted(expr: Expr) -> str:
    if expr.kind == "ref":
        return expr.value
    if expr.kind == "member":
        return dotted(expr.args[0]) + "." + expr.value
    return ""


def concatenate(values: list[Value]) -> Value:
    return Value("text", "".join(v.text for v in values),
                 reasons=tuple(dict.fromkeys(r for v in values for r in v.reasons)),
                 evidence=merge_evidence(*values))


@dataclass
class Context:
    unit: Unit
    scope: str = ""
    env: dict[str, Value] | None = None
    depth: int = 0
    seen: frozenset[tuple] = frozenset()


class Resolver:
    def __init__(self, units: list[Unit], config: Configuration):
        self.units = {unit.path: unit for unit in units}
        self.config = config
        self.functions = {unit.path + "|" + fn.scope: (unit, fn) for unit in units for fn in unit.functions}
        self.diagnostics: list[dict] = []
        self._callers: dict[str, list[tuple[Unit, Call]]] | None = None
        self._contexts: dict[tuple, list[Context]] = {}
        self._steps = 0

    def begin_trace(self) -> None:
        self._steps = 0

    def candidate(self, call: Call, unit: Unit) -> bool:
        """Avoid expanding caller contexts for calls unrelated to supported HTTP APIs."""
        callee = call.expr.args[0]
        if callee.kind == "member":
            name = callee.value.lower().split("<", 1)[0]
            return name in HTTP_METHODS or name in {"fetch", "getasync", "getstringasync", "getbytearrayasync",
                "getstreamasync", "postasync", "putasync", "patchasync", "deleteasync", "sendasync",
                "getfromjsonasync", "postasjsonasync", "putasjsonasync", "patchasjsonasync"}
        if callee.kind == "ref":
            if unit.language == "typescript" and callee.value in {"fetch", "axios"}:
                return True
            if any(i.local == callee.value and (i.module == "axios" or i.module in {"requests", "httpx", "aiohttp"}
                                                and i.member in HTTP_METHODS) for i in unit.imports):
                return True
            # A local alias of an imported HTTP function or a callable Axios instance.
            if any(b.name == callee.value for b in unit.bindings):
                value = self.evaluate(callee, Context(unit, call.scope))
                return value.kind == "client" or value.kind == "symbol" and (
                    value.text in {"fetch", "axios"} or value.text.split(".")[0] in {"requests", "httpx", "aiohttp"})
        return False

    def module_path(self, unit: Unit, module: str) -> str | None:
        if unit.language == "python":
            dots = len(module) - len(module.lstrip("."))
            suffix = module[dots:].replace(".", "/")
            base = str(PurePosixPath(unit.path).parent) if dots else ""
            for _ in range(max(0, dots - 1)):
                base = posixpath.dirname(base)
            path = posixpath.normpath(posixpath.join(base, suffix))
            candidates = [path + ".py", path + "/__init__.py", "src/" + path + ".py", "src/" + path + "/__init__.py"]
        else:
            if not module.startswith("."):
                return None
            path = posixpath.normpath(posixpath.join(str(PurePosixPath(unit.path).parent), module))
            if path.endswith((".js", ".mjs")):
                path = path.rsplit(".", 1)[0]
            candidates = [path, path + ".ts", path + ".tsx", path + "/index.ts", path + "/index.tsx"]
        matches = [p for p in candidates if p in self.units]
        return matches[0] if len(matches) == 1 else None

    def parent_scopes(self, unit: Unit, scope: str):
        while True:
            yield scope
            if not scope:
                break
            scope = unit.parents.get(scope, "")

    def bindings(self, name: str, context: Context, loc: Location) -> list[Binding]:
        for scope in self.parent_scopes(context.unit, context.scope):
            found = [b for b in context.unit.bindings if b.name == name and b.scope == scope]
            # Forward references at module/class level are valid in deferred function bodies.
            if scope == context.scope:
                found = [b for b in found if b.expr.loc.line <= loc.line or b.expr.kind == "unknown"]
            if found:
                return found
        return []

    def reference(self, name: str, context: Context, loc: Location) -> Value:
        key = (context.unit.path, context.scope, name)
        if key in context.seen:
            return Value.unknown(name, "Cyclic value reference", loc)
        if context.env and name in context.env:
            value = context.env[name]
            typed = any(b.name == name and b.scope == context.scope and b.type_name in {"HttpClient", "IHttpClientFactory"}
                        for b in context.unit.bindings)
            if value.kind != "unknown" or not typed:
                return value
        function = next((f for f in context.unit.functions if f.scope == context.scope), None)
        if function and name in function.params and not any(b.name == name and b.scope == context.scope and b.type_name for b in context.unit.bindings):
            return Value.unknown(name, "Function parameter has no known caller value", loc)
        bindings = self.bindings(name, context, loc)
        if bindings:
            values = []
            for binding in bindings:
                child = Context(context.unit, binding.scope, context.env, context.depth, context.seen | {key})
                if binding.type_name.rstrip("?").split(".")[-1] in {"HttpClient", "IHttpClientFactory", "IConfiguration"} and binding.expr.kind == "unknown":
                    type_name = binding.type_name.rstrip("?").split(".")[-1]
                    value = Value("client" if type_name == "HttpClient" else "symbol",
                                  "csharp.HttpClient" if type_name == "HttpClient" else type_name,
                                  evidence=[binding.expr.loc.evidence(f"Declared {type_name}")])
                elif binding.expr.kind == "function":
                    fn = next((f for f in context.unit.functions if f.name == name and f.parent == binding.scope), None)
                    value = Value("function", context.unit.path + "|" + fn.scope) if fn else Value.unknown(name, "Unsupported function binding", loc)
                else:
                    value = self.evaluate(binding.expr, child)
                value = Value(value.kind, value.text, dict(value.props), value.reasons,
                              [*value.evidence, binding.expr.loc.evidence(f"Binding {name}")])
                values.append(value)
            signatures = {(v.kind, v.text, repr(v.props)) for v in values}
            if len(signatures) > 1:
                return Value.unknown(name, "Multiple assignments or branches produce ambiguous values", loc)
            value = values[0]
            if value.kind == "client":
                for suffix in ("BaseAddress", "defaults.baseURL"):
                    bases = self.bindings(name + "." + suffix, context, loc)
                    if len(bases) == 1:
                        value.props["base"] = self.evaluate(bases[0].expr, Context(context.unit, bases[0].scope, context.env,
                                                                                 context.depth, context.seen | {key}))
                    elif len(bases) > 1:
                        value.props["base"] = Value.unknown("base", "Multiple base URL assignments", loc)
            return value
        if any(b.name == name and b.scope == context.scope for b in context.unit.bindings):
            return Value.unknown(name, "Local binding has no preceding value", loc)
        for scope in self.parent_scopes(context.unit, context.scope):
            fns = [f for f in context.unit.functions if f.name == name and f.parent == scope]
            if len(fns) == 1:
                return Value("function", context.unit.path + "|" + fns[0].scope)
            if len(fns) > 1:
                return Value.unknown(name, "Overloaded function is ambiguous", loc)
        imports = []
        for scope in self.parent_scopes(context.unit, context.scope):
            imports = [i for i in context.unit.imports if i.local == name and i.scope == scope]
            if imports:
                break
        if len({(i.module, i.member) for i in imports}) > 1:
            return Value.unknown(name, "Multiple import bindings are ambiguous", loc)
        for imp in imports:
            path = self.module_path(context.unit, imp.module)
            if path:
                if imp.member and imp.member != "default":
                    return self.reference(imp.member, Context(self.units[path], seen=context.seen | {key}),
                                          Location(path, 2**31))
                if imp.member == "default":
                    # A default export is indexed by the adapter as a binding named default.
                    return self.reference("default", Context(self.units[path], seen=context.seen | {key}), Location(path, 2**31))
                return Value("module", path)
            qualified = imp.module + ("." + imp.member if imp.member and imp.member != "default" else "")
            return Value("symbol", qualified, evidence=[loc.evidence(f"Imported {qualified}")])
        if context.unit.language == "typescript" and name in {"fetch", "globalThis", "process", "require", "URL"}:
            return Value("symbol", name)
        if context.unit.language == "csharp":
            short = name.split(".")[-1]
            if short in {"HttpClient", "HttpRequestMessage", "HttpMethod", "Uri", "Environment", "IHttpClientFactory", "System"}:
                # Locally declared classes with these names shadow the framework type.
                if any(s == short or s.endswith("/" + short) for s in context.unit.parents):
                    return Value.unknown(name, "Locally declared type shadows a framework HTTP type", loc)
                return Value("symbol", short)
            if name in {"config", "configuration", "Configuration"}:
                return Value("symbol", "IConfiguration")
            # Unique project-local static class members (e.g. Endpoints.Orders).
            if any(name in u.parents for u in self.units.values()):
                return Value("class", name)
        return Value.unknown(name if re.fullmatch(r"[\w.]+", name) else "value", "No local value or supported client binding", loc)

    def evaluate(self, expr: Expr, context: Context) -> Value:
        self._steps += 1
        if self._steps > 5000:
            if self._steps == 5001:
                self.diagnostics.append({"code": "value_limit", "file": expr.loc.file, "line": expr.loc.line,
                                         "message": "Value expansion exceeded 5,000 steps; this trace is incomplete."})
            return Value.unknown("value", "Value expansion limit reached", expr.loc)
        if len(context.seen) > 100:
            return Value.unknown("value", "Value tracing limit reached", expr.loc)
        kind = expr.kind
        if kind == "text":
            return Value("text", expr.value, evidence=[expr.loc.evidence("Literal value")])
        if kind == "ref":
            return self.reference(expr.value, context, expr.loc)
        if kind == "unknown":
            return Value.unknown(expr.value, "Unsupported or dynamic expression", expr.loc)
        if kind == "concat":
            return concatenate([self.evaluate(arg, context) for arg in expr.args])
        if kind == "object":
            return Value("object", props={key: self.evaluate(value, context) for key, value in expr.props.items()})
        if kind in {"member", "index"}:
            obj = self.evaluate(expr.args[0], context)
            key = expr.value if kind == "member" else self.evaluate(expr.args[1], context).text
            if obj.kind == "object":
                return obj.props.get(key, Value.unknown(key, "Object property is unavailable", expr.loc))
            if obj.kind == "module":
                return self.reference(key, Context(self.units[obj.text], seen=context.seen), Location(obj.text, 2**31))
            if obj.kind == "class":
                matches = [(unit, b) for unit in self.units.values() for b in unit.bindings
                           if b.name == key and b.scope == obj.text]
                if len(matches) == 1:
                    unit, binding = matches[0]
                    token = (unit.path, binding.scope, key)
                    if token in context.seen:
                        return Value.unknown(key, "Cyclic value reference", expr.loc)
                    return self.evaluate(binding.expr, Context(unit, binding.scope, seen=context.seen | {token}))
                fns = [(unit, f) for unit in self.units.values() for f in unit.functions if f.parent == obj.text and f.name == key]
                if len(fns) == 1:
                    return Value("function", fns[0][0].path + "|" + fns[0][1].scope)
            if obj.kind == "symbol":
                if obj.text == "os.environ" and key == "get":
                    return Value("symbol", "os.environ.get", evidence=obj.evidence)
                if obj.text == "IConfiguration" and key.startswith("GetValue"):
                    return Value("symbol", "IConfiguration." + key, evidence=obj.evidence)
                if obj.text in {"process.env", "os.environ", "IConfiguration"}:
                    return self.config.get(key, expr.loc)
                if obj.text == "HttpMethod":
                    return Value("text", key.upper())
                return Value("symbol", obj.text + "." + key, evidence=obj.evidence)
            if obj.kind == "client" and key in {"BaseAddress", "base_url"}:
                return obj.props.get("base", Value.unknown("base", "Client base address is unavailable", expr.loc))
            name = dotted(expr)
            if name and self.bindings(name, context, expr.loc):
                return self.reference(name, context, expr.loc)
            if name in {"builder.Configuration", "this.Configuration"}:
                return Value("symbol", "IConfiguration")
            return Value.unknown(key, "Member cannot be resolved locally", expr.loc)
        if kind == "call":
            return self.evaluate_call(expr, context)
        return Value.unknown("value", "Unsupported expression", expr.loc)

    def evaluate_call(self, expr: Expr, context: Context) -> Value:
        callee = self.evaluate(expr.args[0], context)
        args = [self.evaluate(arg, context) for arg in expr.args[1:]]
        props = {key: self.evaluate(value, context) for key, value in expr.props.items()}
        name = callee.text if callee.kind == "symbol" else ""
        if callee.kind == "function":
            if context.depth >= MAX_DEPTH:
                return Value.unknown("return", "Three-function tracing limit reached", expr.loc)
            unit, fn = self.functions[callee.text]
            token = (unit.path, fn.scope, "call")
            if token in context.seen:
                return Value.unknown(fn.name, "Recursive function call", expr.loc)
            env = self.arguments(fn, args, props, context)
            child = Context(unit, fn.scope, env, context.depth + 1, context.seen | {token})
            values = [self.evaluate(ret, child) for ret in fn.returns]
            if not values:
                return Value.unknown(fn.name, "Function has no supported return expression", expr.loc)
            if len({(v.kind, v.text, repr(v.props)) for v in values}) > 1:
                return Value.unknown(fn.name, "Multiple return paths are ambiguous", expr.loc)
            value = values[0]
            return Value(value.kind, value.text, value.props, value.reasons,
                         [*value.evidence, expr.loc.evidence(f"Return from {fn.name}")])
        if name in {"os.getenv", "os.environ.get", "Environment.GetEnvironmentVariable", "IConfiguration.GetValue", "IConfiguration.GetValue<string>"}:
            if args and args[0].kind == "text":
                value = self.config.get(args[0].text, expr.loc)
                return (args[1] if len(args) > 1 else props.get("default", value)) if value.kind == "unknown" else value
        if name == "require" and args and args[0].kind == "text":
            path = self.module_path(context.unit, args[0].text)
            return Value("module", path) if path else Value("symbol", args[0].text)
        if name in {"Uri", "System.Uri", "URL"} and args:
            if len(args) == 2:
                return self.join(args[1], args[0], "url") if name == "URL" else self.join(args[0], args[1], "url")
            return args[0]
        if name in {"urllib.parse.urljoin"} and len(args) > 1:
            return self.join(args[0], args[1], "url")
        constructors = {"requests.Session": "python.requests", "httpx.Client": "python.httpx", "httpx.AsyncClient": "python.httpx",
                        "aiohttp.ClientSession": "python.aiohttp", "axios.create": "typescript.axios",
                        "HttpClient": "csharp.HttpClient", "System.Net.Http.HttpClient": "csharp.HttpClient"}
        if name in constructors:
            if args and args[0].kind == "object":
                props = {**args[0].props, **props}
            base = next((props[k] for k in ("base_url", "baseURL", "BaseAddress") if k in props), None)
            if name == "aiohttp.ClientSession" and args and args[0].kind == "text":
                base = args[0]
            return Value("client", constructors[name], {"base": base} if base else {},
                         evidence=[expr.loc.evidence(f"HTTP client {name}")])
        if name in {"HttpRequestMessage", "System.Net.Http.HttpRequestMessage"}:
            return Value("object", props={"method": args[0] if args else Value("text", "UNKNOWN"),
                                           "url": args[1] if len(args) > 1 else Value.unknown("url", "Missing request URL", expr.loc)})
        if expr.args[0].kind == "member" and expr.args[0].value == "CreateClient":
            receiver = self.evaluate(expr.args[0].args[0], context)
            if receiver.text == "IHttpClientFactory" and args:
                matches = [(u, b) for u in self.units.values() for b in u.bindings if b.name == "$httpclient:" + args[0].text]
                if len(matches) == 1:
                    unit, binding = matches[0]
                    base = self.evaluate(binding.expr, Context(unit, binding.scope))
                else:
                    base = Value.unknown("base", "Named client registration is missing or ambiguous", expr.loc)
                return Value("client", "csharp.HttpClient", {"base": base}, evidence=[expr.loc.evidence("Named HttpClient")])
        return Value.unknown("return", "Return value is not supported by local tracing", expr.loc)

    def arguments(self, fn: Function, args: list[Value], props: dict[str, Value], context: Context) -> dict[str, Value]:
        result = {}
        for index, param in enumerate(fn.params):
            if param in props:
                result[param] = props[param]
            elif index < len(args):
                result[param] = args[index]
            elif param in fn.defaults:
                result[param] = self.evaluate(fn.defaults[param], context)
        return result

    def contexts(self, unit: Unit, scope: str, seen: frozenset[str] = frozenset(), depth: int = 0) -> list[Context]:
        target = unit.path + "|" + scope
        if target not in self.functions:
            return [Context(unit, scope)]
        if target in seen or depth >= MAX_DEPTH:
            fn = self.functions[target][1]
            reason = "Recursive caller chain" if target in seen else "Three-function tracing limit reached"
            return [Context(unit, scope, {p: Value.unknown(p, reason, fn.loc) for p in fn.params})]
        fn = self.functions[target][1]
        cache_key = (target, seen, depth)
        if cache_key in self._contexts:
            return self._contexts[cache_key]
        if self._callers is None:
            self._callers = {}
            for caller_unit in self.units.values():
                for call in caller_unit.calls:
                    self.begin_trace()
                    resolved = self.evaluate(call.expr.args[0], Context(caller_unit, call.scope))
                    if resolved.kind == "function":
                        self._callers.setdefault(resolved.text, []).append((caller_unit, call))
        result = []
        for caller_unit, call in self._callers.get(target, []):
            for parent in self.contexts(caller_unit, call.scope, seen | {target}, depth + 1):
                self.begin_trace()
                args = [self.evaluate(arg, parent) for arg in call.expr.args[1:]]
                props = {k: self.evaluate(v, parent) for k, v in call.expr.props.items()}
                env = self.arguments(fn, args, props, Context(unit, fn.parent))
                env = {k: Value(v.kind, v.text, dict(v.props), v.reasons,
                                [*v.evidence, call.expr.loc.evidence(f"Argument passed to {fn.name}")]) for k, v in env.items()}
                result.append(Context(unit, scope, env))
                if len(result) >= MAX_CONTEXTS:
                    self.diagnostics.append({"code": "context_limit", "file": unit.path, "line": fn.loc.line,
                                             "message": "Stopped after 100 caller contexts; findings may be incomplete."})
                    self._contexts[cache_key] = result
                    return result
        if result:
            self._contexts[cache_key] = result
            return result
        defaults = self.arguments(fn, [], {}, Context(unit, fn.parent))
        result = [Context(unit, scope, defaults)]
        self._contexts[cache_key] = result
        return result

    def join(self, base: Value, path: Value, client: str) -> Value:
        if re.match(r"^https?://", path.text, re.I):
            return path
        reasons = tuple(dict.fromkeys((*base.reasons, *path.reasons)))
        if client in {"typescript.axios", "python.httpx"}:
            text = base.text.rstrip("/") + "/" + path.text.lstrip("/")
        elif re.match(r"^https?://[^{}]+", base.text, re.I):
            text = urljoin(base.text, path.text)
        else:
            text = base.text.rstrip("/") + "/" + path.text.lstrip("/")
        return Value("text", text, reasons=reasons, evidence=merge_evidence(base, path))

    def http_call(self, call: Call, context: Context) -> tuple[str, Value, str] | None:
        expr, callee_expr = call.expr, call.expr.args[0]
        callee = self.evaluate(callee_expr, context)
        receiver = self.evaluate(callee_expr.args[0], context) if callee_expr.kind == "member" else None
        method_name = callee_expr.value.lower() if callee_expr.kind == "member" else ""
        client, method = "", "UNKNOWN"
        offset = 0
        symbol = callee.text if callee.kind == "symbol" else ""
        if receiver and receiver.kind == "client":
            client = receiver.text
        elif callee.kind == "client" and callee.text == "typescript.axios":
            receiver, client, method_name = callee, callee.text, "request"
        elif symbol in {"fetch", "globalThis.fetch"}:
            client, method = "typescript.fetch", "GET"
        elif symbol == "axios":
            client = "typescript.axios"
            method_name = "request"
        elif symbol.startswith("axios.") and symbol.split(".")[-1] in HTTP_METHODS:
            client = "typescript.axios"
            method_name = symbol.split(".")[-1]
        elif symbol.count(".") == 1 and symbol.split(".")[0] in {"requests", "httpx", "aiohttp"} and symbol.split(".")[-1] in HTTP_METHODS:
            client = "python." + symbol.split(".")[0]
            method_name = symbol.split(".")[-1]
        elif any(symbol.startswith(mod + ".") for mod in ("http", "https", "node:http", "node:https")) and symbol.split(".")[-1] in {"get", "request"}:
            client = "typescript." + symbol.rsplit(".", 1)[0]
            method_name = symbol.rsplit(".", 1)[1]
        if not client:
            return None
        if client == "csharp.HttpClient":
            methods = {"getasync": "GET", "getstringasync": "GET", "getbytearrayasync": "GET", "getstreamasync": "GET",
                       "postasync": "POST", "putasync": "PUT", "patchasync": "PATCH", "deleteasync": "DELETE",
                       "sendasync": "UNKNOWN", "send": "UNKNOWN", "getfromjsonasync": "GET", "postasjsonasync": "POST",
                       "putasjsonasync": "PUT", "patchasjsonasync": "PATCH"}
            method_name = method_name.split("<")[0]
            if method_name not in methods:
                return None
            method = methods[method_name]
        elif client != "typescript.fetch":
            if method_name not in HTTP_METHODS:
                return None
            method = method_name.upper() if method_name not in {"request", "send"} else "GET"
        args = [self.evaluate(a, context) for a in expr.args[1:]]
        keywords = {k: self.evaluate(v, context) for k, v in expr.props.items()}
        if client.startswith("python.") and method_name == "request":
            method = keywords.get("method", args[0] if args else Value("text", "UNKNOWN")).text.upper()
            offset = 1
        url = keywords.get("url", args[offset] if len(args) > offset else Value.unknown("url", "Missing or dynamic URL", expr.loc))
        options: dict[str, Value] = {}
        if url.kind == "object":
            options = url.props
            url = options.get("url", Value.unknown("url", "URL is absent from request options", expr.loc))
        else:
            option_index = 2 if client == "typescript.axios" and method_name in {"post", "put", "patch"} else offset + 1
            if len(args) > option_index and args[option_index].kind == "object" and client in {
                "typescript.fetch", "typescript.axios", "typescript.http", "typescript.https", "typescript.node:http", "typescript.node:https"}:
                options = args[option_index].props
        method = options.get("method", Value("text", method)).text.upper()
        if client in {"typescript.http", "typescript.https", "typescript.node:http", "typescript.node:https"} and options:
            host = options.get("hostname", options.get("host"))
            if host:
                protocol = options.get("protocol", Value("text", "https:" if client.endswith("https") else "http:"))
                port = options.get("port")
                path = options.get("path", Value("text", "/"))
                url = concatenate([protocol, Value("text", "//"), host,
                                   *([Value("text", ":"), port] if port else []), path])
        base = options.get("baseURL") or (receiver.props.get("base") if receiver and receiver.kind == "client" else None)
        if base:
            url = self.join(base, url, client)
        url = Value(url.kind, url.text, dict(url.props), url.reasons, list(url.evidence))
        if not re.match(r"^https?://", url.text, re.I) and not url.reasons:
            url.reasons = ("Relative URL has no resolved HTTP(S) base",)
        url.evidence = [expr.loc.evidence(f"{client} {method} call"), *url.evidence]
        return method, url, client
