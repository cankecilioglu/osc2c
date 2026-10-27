"""Parse-tree to typed-AST transformation (Aşama 1).

Pure syntax: every rule produces an AST node or a plain Python value
(str for names, numbers for SI exponents). No symbol resolution here.
"""

from __future__ import annotations

import re

from antlr4 import ParserRuleContext

from osc2c.frontend import ast
from osc2c.frontend.ast import Span
from osc2c.frontend.generated.openscenario2Visitor import openscenario2Visitor
from osc2c.frontend.generated import openscenario2Parser as parser

_P = parser.openscenario2Parser


_PHYSICAL_RE = re.compile(
    r"(?P<number>[+-]?(?:\d*\.\d+(?:[eE][+-]?\d+)?|\d+(?:[eE][+-]?\d+)?|[+-]?inf|[+-]?nan))"
    r"(?P<unit>.+)",
    re.IGNORECASE,
)

_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "\\": "\\",
    '"': '"',
    "'": "'",
}


def _unescape(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        char = raw[i]
        if char == "\\" and i + 1 < len(raw):
            out.append(_ESCAPES.get(raw[i + 1], "\\" + raw[i + 1]))
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


class AstTransformer(openscenario2Visitor):
    def __init__(self, source: str = "<string>") -> None:
        self.source = source

    # ------------------------------------------------------------- utilities

    def _span(self, ctx: ParserRuleContext) -> Span:
        start = ctx.start
        stop = ctx.stop or start
        text = stop.text or ""
        return Span(
            source=self.source,
            line=start.line,
            column=start.column,
            end_line=stop.line,
            end_column=stop.column + len(text),
        )

    def _visit_all(self, contexts) -> list:
        result = []
        for ctx in contexts or []:
            node = self.visit(ctx)
            if isinstance(node, list):
                result.extend(node)
            elif node is not None:
                result.append(node)
        return result

    def _children_of(self, ctx: ParserRuleContext, *classes) -> list:
        """Visit children in source order, keeping only the given rule classes."""
        result = []
        for child in ctx.children or []:
            if isinstance(child, classes):
                node = self.visit(child)
                if isinstance(node, list):
                    result.extend(node)
                elif node is not None:
                    result.append(node)
        return result

    def _inherits(self, ctx) -> ast.InheritsSpec | None:
        """Second name occurrence in the rule is the inherited type, if present."""
        target = None
        for accessor in ("struct_name", "actor_name", "qualified_behavior_name"):
            if not hasattr(ctx, accessor):
                continue
            names = getattr(ctx, accessor)()
            if names and len(names) > 1:
                target = names[1]
            break
        if target is None:
            return None
        field = None
        condition = None
        if ctx.field_name() is not None:
            field = ctx.field_name().getText()
        if ctx.enum_value_reference() is not None:
            condition = self.visit(ctx.enum_value_reference())
        elif ctx.bool_literal() is not None:
            condition = self.visit(ctx.bool_literal())
        return ast.InheritsSpec(self._span(target), target.getText(), field, condition)

    # ---------------------------------------------------------------- prelude

    def visitOsc_file(self, ctx: parser.Osc_fileContext):
        imports: list[ast.ImportDecl] = []
        uses: list[ast.UseDecl] = []
        for prelude in ctx.prelude_statement():
            node = self.visit(prelude)
            if isinstance(node, ast.ImportDecl):
                imports.append(node)
            elif isinstance(node, ast.UseDecl):
                uses.append(node)
        declarations = self._visit_all(ctx.main_statement())
        return ast.CompilationUnit(self._span(ctx), imports, uses, declarations)

    def visitPrelude_statement(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitMain_statement(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitOsc_declaration(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitImport_statement(self, ctx: parser.Import_statementContext):
        reference_ctx = ctx.import_reference()
        if reference_ctx.string_literal() is not None:
            literal = self.visit(reference_ctx.string_literal())
            return ast.ImportDecl(self._span(ctx), literal.value, is_path=True)
        return ast.ImportDecl(
            self._span(ctx), reference_ctx.structured_identifier().getText(), is_path=False
        )

    def visitImport_reference(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitUse_statement(self, ctx: parser.Use_statementContext):
        namespaces = [item.getText() for item in ctx.structured_identifier()]
        return ast.UseDecl(self._span(ctx), namespaces)

    def visitStructured_identifier(self, ctx: parser.Structured_identifierContext) -> str:
        return ctx.getText()

    def visitNamespace_statement(self, ctx: parser.Namespace_statementContext):
        name = ctx.namespace_name().getText()
        uses = self.visit(ctx.namespace_list()) if ctx.namespace_list() else []
        return ast.NamespaceDecl(self._span(ctx), name, uses)

    def visitNamespace_list(self, ctx: parser.Namespace_listContext) -> list[str]:
        return [item.getText() for item in ctx.namespace_name()]

    def visitNamespace_name(self, ctx) -> str:
        return ctx.getText()

    def visitGlobal_namespace_name(self, ctx) -> str:
        return ctx.getText()

    def visitExport_statement(self, ctx: parser.Export_statementContext):
        return ast.ExportDecl(self._span(ctx), self._visit_all(ctx.export_specification()))

    def visitExport_specification(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitExport_wildcard_specification(self, ctx: parser.Export_wildcard_specificationContext):
        name = ctx.namespace_name().getText() if ctx.namespace_name() else ""
        return ast.ExportSpec(self._span(ctx), name, wildcard=True)

    # ------------------------------------------------------------------ types

    def visitType_declarator(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitNon_aggregate_type_declarator(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitAggregate_type_declarator(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitList_type_declarator(self, ctx: parser.List_type_declaratorContext):
        child = ctx.non_aggregate_type_declarator() or ctx.range_type_declarator()
        return ast.ListType(self._span(ctx), self.visit(child))

    def visitRange_type_declarator(self, ctx: parser.Range_type_declaratorContext):
        return ast.RangeType(self._span(ctx), self.visit(ctx.numeric_type_declarator()))

    def visitNumeric_type_declarator(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitPrimitive_numeric_type(self, ctx: parser.Primitive_numeric_typeContext):
        return ast.PrimitiveType(self._span(ctx), ctx.getText())

    def visitPrimitive_type(self, ctx: parser.Primitive_typeContext):
        return ast.PrimitiveType(self._span(ctx), ctx.getText())

    def visitDeclared_type_name(self, ctx: parser.Declared_type_nameContext):
        return ast.NamedType(self._span(ctx), ctx.getText())

    # ------------------------------------------------------------------ units

    def visitSi_base_unit_name(self, ctx) -> str:
        return ctx.getText()

    def visitSi_base_specifier(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitUnit_specifier(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitSi_base_exponent(self, ctx: parser.Si_base_exponentContext):
        return ast.SiExponent(
            self._span(ctx),
            ctx.si_base_unit_name().getText(),
            self.visit(ctx.integer_literal()).value,
        )

    def visitSi_base_exponent_list(self, ctx: parser.Si_base_exponent_listContext):
        return self._visit_all(ctx.si_base_exponent())

    def visitSi_base_unit_specifier(self, ctx: parser.Si_base_unit_specifierContext):
        return ast.SiBaseSpec(self._span(ctx), self.visit(ctx.si_base_exponent_list()))

    def visitSi_factor(self, ctx: parser.Si_factorContext):
        return self._number(ctx)

    def visitSi_offset(self, ctx: parser.Si_offsetContext):
        return self._number(ctx)

    def _number(self, ctx) -> float:
        if ctx.integer_literal() is not None:
            return self.visit(ctx.integer_literal()).value
        return self.visit(ctx.float_literal()).value

    def visitSi_unit_specifier(self, ctx: parser.Si_unit_specifierContext):
        factor = float(self.visit(ctx.si_factor())) if ctx.si_factor() is not None else None
        offset = float(self.visit(ctx.si_offset())) if ctx.si_offset() is not None else None
        return ast.SiUnitSpec(self._span(ctx), self.visit(ctx.si_base_exponent_list()), factor, offset)

    def visitPhysical_type_declaration(self, ctx: parser.Physical_type_declarationContext):
        name = ctx.declared_type_name().getText()
        return ast.PhysicalTypeDecl(self._span(ctx), name, self.visit(ctx.base_unit_specifier()))

    def visitUnit_declaration(self, ctx: parser.Unit_declarationContext):
        return ast.UnitDecl(
            self._span(ctx),
            ctx.unit_name().getText(),
            ctx.declared_type_name().getText(),
            self.visit(ctx.unit_specifier()),
        )

    # ------------------------------------------------------------------ enums

    def visitEnum_member_decl(self, ctx: parser.Enum_member_declContext):
        value = None
        if ctx.enum_member_value() is not None:
            value = self.visit(ctx.enum_member_value())
        return ast.EnumMember(self._span(ctx), ctx.enum_member_name().getText(), value)

    def visitEnum_member_value(self, ctx):
        if ctx.enum_value_reference() is not None:
            return self.visit(ctx.enum_value_reference())
        return int(ctx.getText(), 0)

    def visitEnum_value_reference(self, ctx: parser.Enum_value_referenceContext):
        enum_name = ctx.enum_name().getText() if ctx.enum_name() is not None else None
        return ast.EnumValueRef(self._span(ctx), enum_name, ctx.enum_member_name().getText())

    def visitEnum_declaration(self, ctx: parser.Enum_declarationContext):
        return ast.EnumDecl(
            self._span(ctx),
            ctx.enum_name().getText(),
            self._visit_all(ctx.enum_member_decl()),
        )

    def visitEnum_type_extension(self, ctx: parser.Enum_type_extensionContext):
        return ast.EnumExtensionDecl(
            self._span(ctx),
            ctx.enum_name().getText(),
            self._visit_all(ctx.enum_member_decl()),
        )

    # ------------------------------------------------------------- structures

    def visitStruct_member_decl(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitStruct_declaration(self, ctx: parser.Struct_declarationContext):
        return ast.StructDecl(
            self._span(ctx),
            ctx.struct_name(0).getText(),
            self._inherits(ctx),
            self._visit_all(ctx.struct_member_decl()),
        )

    def visitActor_member_decl(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitActor_declaration(self, ctx: parser.Actor_declarationContext):
        return ast.ActorDecl(
            self._span(ctx),
            ctx.actor_name(0).getText(),
            self._inherits(ctx),
            self._visit_all(ctx.actor_member_decl()),
        )

    def visitScenario_member_decl(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitScenario_declaration(self, ctx: parser.Scenario_declarationContext):
        return ast.ScenarioDecl(
            self._span(ctx),
            ctx.qualified_behavior_name(0).getText(),
            self._inherits(ctx),
            self._children_of(
                ctx, _P.Scenario_member_declContext, _P.Behavior_specificationContext
            ),
        )

    def visitAction_declaration(self, ctx: parser.Action_declarationContext):
        return ast.ActionDecl(
            self._span(ctx),
            ctx.qualified_behavior_name(0).getText(),
            self._inherits(ctx),
            self._children_of(
                ctx, _P.Scenario_member_declContext, _P.Behavior_specificationContext
            ),
        )

    def visitModifier_declaration(self, ctx: parser.Modifier_declarationContext):
        actor_ctx = ctx.actor_name()
        actor = actor_ctx.getText() if actor_ctx is not None else None
        of = ctx.qualified_behavior_name().getText() if ctx.qualified_behavior_name() is not None else None
        return ast.ModifierDecl(
            self._span(ctx),
            actor,
            ctx.modifier_name().getText(),
            of,
            self._children_of(
                ctx, _P.Scenario_member_declContext, _P.On_directiveContext
            ),
        )

    def visitGlobal_parameter_declaration(self, ctx: parser.Global_parameter_declarationContext):
        return self.visit(ctx.parameter_declaration())

    def visitType_extension(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitExtension_member_decl(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitStructured_type_extension(self, ctx: parser.Structured_type_extensionContext):
        return ast.StructuredExtensionDecl(
            self._span(ctx),
            ctx.extendable_type_name().getText(),
            self._visit_all(ctx.extension_member_decl()),
        )

    def visitPrimitive_type_extension(self, ctx: parser.Primitive_type_extensionContext):
        return ast.PrimitiveExtensionDecl(
            self._span(ctx),
            ctx.primitive_type().getText(),
            self._visit_all(ctx.method_declaration()),
        )

    # ----------------------------------------------------------------- events

    def visitEvent_declaration(self, ctx: parser.Event_declarationContext):
        parameters = (
            self.visit(ctx.argument_list_specification())
            if ctx.argument_list_specification() is not None
            else None
        )
        specification = (
            self.visit(ctx.event_specification()) if ctx.event_specification() is not None else None
        )
        return ast.EventDecl(
            self._span(ctx), ctx.event_name().getText(), parameters, specification
        )

    def visitArgument_specification(self, ctx: parser.Argument_specificationContext):
        default = self.visit(ctx.default_value()) if ctx.default_value() is not None else None
        return ast.ArgSpec(
            self._span(ctx),
            ctx.argument_name().getText(),
            self.visit(ctx.type_declarator()),
            default,
        )

    def visitArgument_list_specification(self, ctx: parser.Argument_list_specificationContext):
        return self._visit_all(ctx.argument_specification())

    def visitEvent_specification(self, ctx: parser.Event_specificationContext):
        if ctx.event_reference() is not None:
            reference = self.visit(ctx.event_reference())
            field = (
                self.visit(ctx.event_field_decl()) if ctx.event_field_decl() is not None else None
            )
            condition = (
                self.visit(ctx.event_condition()) if ctx.event_condition() is not None else None
            )
            return ast.EventSpec(self._span(ctx), reference, field, condition)
        return ast.EventSpec(
            self._span(ctx), None, None, self.visit(ctx.event_condition())
        )

    def visitEvent_reference(self, ctx: parser.Event_referenceContext):
        path = ctx.event_path()
        target = self.visit(path.expression()) if path.expression() is not None else None
        return ast.EventReference(self._span(ctx), target, path.event_name().getText())

    def visitEvent_field_decl(self, ctx: parser.Event_field_declContext) -> str:
        return ctx.event_field_name().getText()

    def visitEvent_condition(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitBool_expression(self, ctx: parser.Bool_expressionContext):
        return ast.BoolCond(self._span(ctx), self.visit(ctx.expression()))

    def visitDuration_expression(self, ctx: parser.Duration_expressionContext):
        return self.visit(ctx.expression())

    def visitRise_expression(self, ctx: parser.Rise_expressionContext):
        return ast.RiseCond(self._span(ctx), self.visit(ctx.bool_expression()).expr)

    def visitFall_expression(self, ctx: parser.Fall_expressionContext):
        return ast.FallCond(self._span(ctx), self.visit(ctx.bool_expression()).expr)

    def visitElapsed_expression(self, ctx: parser.Elapsed_expressionContext):
        return ast.ElapsedCond(self._span(ctx), self.visit(ctx.duration_expression()))

    def visitEvery_expression(self, ctx: parser.Every_expressionContext):
        offset = (
            self.visit(ctx.duration_expression(1)) if ctx.duration_expression(1) is not None else None
        )
        return ast.EveryCond(
            self._span(ctx), self.visit(ctx.duration_expression(0)), offset
        )

    # ---------------------------------------------------------------- members

    def visitField_declaration(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitParameter_declaration(self, ctx: parser.Parameter_declarationContext):
        names = [item.getText() for item in ctx.field_name()]
        default = self.visit(ctx.default_value()) if ctx.default_value() is not None else None
        constraints = (
            self.visit(ctx.parameter_with_declaration())
            if ctx.parameter_with_declaration() is not None
            else []
        )
        return ast.ParameterDecl(
            self._span(ctx), names, self.visit(ctx.type_declarator()), default, constraints
        )

    def visitVariable_declaration(self, ctx: parser.Variable_declarationContext):
        sample = self.visit(ctx.sample_expression()) if ctx.sample_expression() is not None else None
        value = None if sample is not None else (
            self.visit(ctx.default_value()) if ctx.default_value() is not None else None
        )
        return ast.VariableDecl(
            self._span(ctx),
            [item.getText() for item in ctx.field_name()],
            self.visit(ctx.type_declarator()),
            value,
            sample,
        )

    def visitSample_expression(self, ctx: parser.Sample_expressionContext):
        default = self.visit(ctx.default_value()) if ctx.default_value() is not None else None
        return ast.SampleExpr(
            self._span(ctx),
            self.visit(ctx.expression()),
            self.visit(ctx.event_specification()),
            default,
        )

    def visitParameter_with_declaration(self, ctx):
        return self._visit_all(ctx.parameter_with_member())

    def visitParameter_with_member(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitConstraint_declaration(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitKeep_constraint_declaration(self, ctx: parser.Keep_constraint_declarationContext):
        qualifier = ctx.constraint_qualifier().getText() if ctx.constraint_qualifier() else None
        return ast.KeepConstraint(self._span(ctx), qualifier, self.visit(ctx.constraint_expression()))

    def visitRemove_default_declaration(self, ctx: parser.Remove_default_declarationContext):
        return ast.RemoveDefault(self._span(ctx), self.visit(ctx.parameter_reference()))

    def visitParameter_reference(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitMethod_declaration(self, ctx: parser.Method_declarationContext):
        parameters = (
            self.visit(ctx.argument_list_specification())
            if ctx.argument_list_specification() is not None
            else None
        )
        return_type = self.visit(ctx.return_type()) if ctx.return_type() is not None else None
        return ast.MethodDecl(
            self._span(ctx),
            ctx.method_name().getText(),
            parameters,
            return_type,
            self.visit(ctx.method_implementation()),
        )

    def visitMethod_implementation(self, ctx: parser.Method_implementationContext):
        if ctx.expression() is not None:
            return ast.MethodImpl(self._span(ctx), "expression", self.visit(ctx.expression()), None, None)
        if ctx.structured_identifier() is not None:
            args = self.visit(ctx.argument_list()) if ctx.argument_list() is not None else None
            return ast.MethodImpl(
                self._span(ctx), "external", None, ctx.structured_identifier().getText(), args
            )
        return ast.MethodImpl(self._span(ctx), "undefined", None, None, None)

    def visitCoverage_declaration(self, ctx: parser.Coverage_declarationContext):
        return ast.CoverageDecl(
            self._span(ctx), ctx.getChild(0).getText(), self.visit(ctx.argument_list())
        )

    def visitModifier_application(self, ctx: parser.Modifier_applicationContext):
        target = self.visit(ctx.actor_expression()) if ctx.actor_expression() is not None else None
        args = self.visit(ctx.argument_list()) if ctx.argument_list() is not None else []
        return ast.ModifierApplication(self._span(ctx), target, ctx.modifier_name().getText(), args)

    def visitActor_expression(self, ctx):
        return self.visit(ctx.expression())

    # -------------------------------------------------------------- behaviors

    def visitBehavior_specification(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitOn_directive(self, ctx: parser.On_directiveContext):
        return ast.OnDirective(
            self._span(ctx),
            self.visit(ctx.event_specification()),
            self._visit_all(ctx.on_member()),
        )

    def visitOn_member(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitDo_directive(self, ctx: parser.Do_directiveContext):
        return ast.DoDirective(self._span(ctx), self.visit(ctx.do_member()))

    def visitDo_member(self, ctx: parser.Do_memberContext):
        statement = None
        for accessor in (
            "composition",
            "behavior_invocation",
            "wait_directive",
            "emit_directive",
            "call_directive",
        ):
            child = getattr(ctx, accessor)()
            if child is not None:
                statement = self.visit(child)
                break
        if statement is None:
            raise ValueError(f"empty do_member at line {ctx.start.line}")
        if ctx.label_name() is not None:
            return ast.LabeledStatement(
                self._span(ctx), ctx.label_name().getText(), statement
            )
        return statement

    def visitComposition(self, ctx: parser.CompositionContext):
        args = self.visit(ctx.unqualified_argument_list()) if ctx.unqualified_argument_list() else []
        with_clause = (
            self.visit(ctx.behavior_with_declaration())
            if ctx.behavior_with_declaration() is not None
            else None
        )
        return ast.Composition(
            self._span(ctx),
            ctx.composition_operator().getText(),
            args,
            self._visit_all(ctx.do_member()),
            with_clause,
        )

    def visitComposition_operator(self, ctx) -> str:
        return ctx.getText()

    def visitUnqualified_argument_list(self, ctx: parser.Unqualified_argument_listContext):
        result = []
        for child in ctx.children:
            if isinstance(child, _P.Positional_argumentContext):
                result.append(self.visit(child))
            elif isinstance(child, _P.Unqualified_named_argumentContext):
                result.append(self.visit(child))
        return result

    def visitUnqualified_argument_name(self, ctx) -> str:
        return ctx.getText()

    def visitUnqualified_named_argument(self, ctx: parser.Unqualified_named_argumentContext):
        return ast.NamedArg(
            self._span(ctx),
            ctx.unqualified_argument_name().getText(),
            self.visit(ctx.expression()),
        )

    def visitPositional_argument(self, ctx: parser.Positional_argumentContext):
        return ast.PositionalArg(self._span(ctx), self.visit(ctx.expression()))

    def visitBehavior_invocation(self, ctx: parser.Behavior_invocationContext):
        target = self.visit(ctx.actor_expression()) if ctx.actor_expression() is not None else None
        args = self.visit(ctx.argument_list()) if ctx.argument_list() is not None else []
        with_clause = (
            self.visit(ctx.behavior_with_declaration())
            if ctx.behavior_with_declaration() is not None
            else None
        )
        return ast.BehaviorInvocation(
            self._span(ctx), target, ctx.behavior_name().getText(), args, with_clause
        )

    def visitBehavior_with_declaration(self, ctx):
        return ast.BehaviorWith(
            self._span(ctx),
            self._visit_all(ctx.behavior_with_member()),
        )

    def visitBehavior_with_member(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitWait_directive(self, ctx: parser.Wait_directiveContext):
        return ast.WaitDirective(self._span(ctx), self.visit(ctx.event_specification()))

    def visitEmit_directive(self, ctx: parser.Emit_directiveContext):
        args = self.visit(ctx.argument_list()) if ctx.argument_list() is not None else None
        return ast.EmitDirective(self._span(ctx), ctx.event_name().getText(), args)

    def visitCall_directive(self, ctx: parser.Call_directiveContext):
        return ast.CallDirective(self._span(ctx), self.visit(ctx.method_invocation()))

    def visitMethod_invocation(self, ctx: parser.Method_invocationContext):
        args = self.visit(ctx.argument_list()) if ctx.argument_list() is not None else []
        return ast.Call(self._span(ctx), self.visit(ctx.postfix_exp()), args)

    def visitUntil_directive(self, ctx: parser.Until_directiveContext):
        return ast.UntilDirective(self._span(ctx), self.visit(ctx.event_specification()))

    # ------------------------------------------------------------------- args

    def visitArgument_list(self, ctx: parser.Argument_listContext):
        result = []
        for child in ctx.children:
            if isinstance(child, _P.Positional_argumentContext):
                result.append(self.visit(child))
            elif isinstance(child, _P.Named_argumentContext):
                result.append(self.visit(child))
        return result

    def visitNamed_argument(self, ctx: parser.Named_argumentContext):
        return ast.NamedArg(
            self._span(ctx), ctx.argument_name().getText(), self.visit(ctx.expression())
        )

    # ------------------------------------------------------------ expressions

    def visitExpression(self, ctx: parser.ExpressionContext):
        return self.visit(ctx.getChild(0))

    def visitTernary_op_exp(self, ctx: parser.Ternary_op_expContext):
        return ast.TernaryOp(
            self._span(ctx),
            self.visit(ctx.implication()),
            self.visit(ctx.expression(0)),
            self.visit(ctx.expression(1)),
        )

    def visitImplication(self, ctx: parser.ImplicationContext):
        items = ctx.disjunction()
        if len(items) == 1:
            return self.visit(items[0])
        return self._fold(ctx, "=>", [self.visit(item) for item in items])

    def visitDisjunction(self, ctx: parser.DisjunctionContext):
        items = ctx.conjunction()
        if len(items) == 1:
            return self.visit(items[0])
        return self._fold(ctx, "or", [self.visit(item) for item in items])

    def visitConjunction(self, ctx: parser.ConjunctionContext):
        items = ctx.inversion()
        if len(items) == 1:
            return self.visit(items[0])
        return self._fold(ctx, "and", [self.visit(item) for item in items])

    def _fold(self, ctx, op: str, operands: list) -> ast.Expr:
        node = operands[0]
        for right in operands[1:]:
            node = ast.BinaryOp(self._span(ctx), op, node, right)
        return node

    def visitInversion(self, ctx: parser.InversionContext):
        if ctx.inversion() is not None:
            return ast.UnaryOp(self._span(ctx), "not", self.visit(ctx.inversion()))
        return self.visit(ctx.relation())

    def visitRelation(self, ctx: parser.RelationContext):
        if ctx.relational_op() is not None:
            return ast.BinaryOp(
                self._span(ctx),
                ctx.relational_op().getText(),
                self.visit(ctx.relation()),
                self.visit(ctx.sum_exp()),
            )
        return self.visit(ctx.sum_exp())

    def visitRelational_op(self, ctx) -> str:
        return ctx.getText()

    def visitSum_exp(self, ctx: parser.Sum_expContext):
        if ctx.sum_exp() is not None:
            return ast.BinaryOp(
                self._span(ctx),
                ctx.additive_op().getText(),
                self.visit(ctx.sum_exp()),
                self.visit(ctx.term()),
            )
        return self.visit(ctx.term())

    def visitAdditive_op(self, ctx) -> str:
        return ctx.getText()

    def visitTerm(self, ctx: parser.TermContext):
        if ctx.term() is not None:
            return ast.BinaryOp(
                self._span(ctx),
                ctx.multiplicative_op().getText(),
                self.visit(ctx.term()),
                self.visit(ctx.factor()),
            )
        return self.visit(ctx.factor())

    def visitMultiplicative_op(self, ctx) -> str:
        return ctx.getText()

    def visitFactor(self, ctx: parser.FactorContext):
        if ctx.postfix_exp() is not None:
            return self.visit(ctx.postfix_exp())
        return ast.UnaryOp(self._span(ctx), "-", self.visit(ctx.factor()))

    def visitPrimary_exp_pe(self, ctx: parser.Primary_exp_peContext):
        return self.visit(ctx.primary_exp())

    def visitCast_exp_pe(self, ctx: parser.Cast_exp_peContext):
        return ast.Cast(
            self._span(ctx), self.visit(ctx.postfix_exp()), self.visit(ctx.type_declarator())
        )

    def visitType_test_exp_pe(self, ctx: parser.Type_test_exp_peContext):
        return ast.TypeTest(
            self._span(ctx), self.visit(ctx.postfix_exp()), self.visit(ctx.type_declarator())
        )

    def visitElement_access_pe(self, ctx: parser.Element_access_peContext):
        return ast.ElementAccess(
            self._span(ctx), self.visit(ctx.postfix_exp()), self.visit(ctx.expression())
        )

    def visitFunction_application_pe(self, ctx: parser.Function_application_peContext):
        args = self.visit(ctx.argument_list()) if ctx.argument_list() is not None else []
        return ast.Call(self._span(ctx), self.visit(ctx.postfix_exp()), args)

    def visitField_access_pe(self, ctx: parser.Field_access_peContext):
        return ast.FieldAccess(
            self._span(ctx), self.visit(ctx.postfix_exp()), ctx.field_name().getText()
        )

    def visitField_access(self, ctx: parser.Field_accessContext):
        return ast.FieldAccess(
            self._span(ctx), self.visit(ctx.postfix_exp()), ctx.field_name().getText()
        )

    def visitPrimary_exp(self, ctx: parser.Primary_expContext):
        if ctx.value_exp() is not None:
            value = self.visit(ctx.value_exp())
            if isinstance(value, ast.EnumValueRef) and value.enum is None:
                # Bare `red` is syntactically identical to an identifier; the
                # middle-end decides whether it names a field or an enum member.
                return ast.Identifier(value.span, value.member.split("."))
            return value
        if ctx.qualified_identifier() is not None:
            return ast.Identifier(
                self._span(ctx), ctx.qualified_identifier().getText().split(".")
            )
        if ctx.expression() is not None:
            return self.visit(ctx.expression())
        return ast.ItExpr(self._span(ctx))

    def visitValue_exp(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitInteger_literal(self, ctx: parser.Integer_literalContext):
        return ast.IntLiteral(self._span(ctx), int(ctx.getText(), 0))

    def visitFloat_literal(self, ctx: parser.Float_literalContext):
        return ast.FloatLiteral(self._span(ctx), float(ctx.getText()))

    def visitPhysical_literal(self, ctx: parser.Physical_literalContext):
        match = _PHYSICAL_RE.fullmatch(ctx.getText())
        if match is None:
            raise ValueError(f"cannot split physical literal {ctx.getText()!r}")
        return ast.PhysicalLiteral(self._span(ctx), float(match.group("number")), match.group("unit"))

    def visitBool_literal(self, ctx: parser.Bool_literalContext):
        return ast.BoolLiteral(self._span(ctx), ctx.getText() == "true")

    def visitString_literal(self, ctx: parser.String_literalContext):
        raw = ctx.getText()
        quote = raw[:3] if raw.startswith(('"""', "'''")) else raw[:1]
        return ast.StringLiteral(self._span(ctx), _unescape(raw[len(quote):-len(quote)]))

    def visitList_constructor(self, ctx: parser.List_constructorContext):
        return ast.ListLiteral(self._span(ctx), self._visit_all(ctx.expression()))

    def visitRange_constructor(self, ctx: parser.Range_constructorContext):
        expressions = ctx.expression()
        return ast.RangeLiteral(
            self._span(ctx), self.visit(expressions[0]), self.visit(expressions[1])
        )

    def visitQualified_identifier(self, ctx) -> str:
        return ctx.getText()

    def visitPrefixed_identifier(self, ctx) -> str:
        return ctx.getText()
