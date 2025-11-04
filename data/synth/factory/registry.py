"""Registry of document archetypes (card, form, screen, invoice, etc.)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .dsl import (
    Badge,
    Choice,
    Columns,
    Flow,
    FormGrid,
    Heading,
    KVList,
    Page,
    Paragraph,
    Rand,
    Sample,
    Table,
    Top,
    Bottom,
)


@dataclass
class Archetype:
    """Document archetype definition."""

    name: str
    weight: float
    builder: Callable[[Dict[str, str]], Page]  # Takes schema dict, returns Page
    description: str = ""


def build_generic_card(schema: Dict[str, str]) -> Page:
    """Build a card/ID-like document (compact, title, KV, badge)."""
    from .fakerx import generate_pairs_for_schema

    pairs = generate_pairs_for_schema(schema, coverage=0.7)
    kv_pairs = [(name, label, val) for name, label, val in pairs]

    # Find enum field for badge
    enum_field = None
    for name, desc in schema.items():
        if any(word in name.lower() or word in desc.lower() for word in ["situacao", "status", "categoria"]):
            enum_field = name
            break

    widgets = [
        Heading(flow="main", level=Choice(1, 2), text=Sample("doc_title")),
        KVList(flow="main", pairs=kv_pairs, mode=Choice("right_of", "below"), gap=Rand(8, 16)),
    ]

    if enum_field:
        widgets.append(Badge(flow="main", text=Sample(f"enum_{enum_field}"), anchor=Choice("bottom-right", "top-right")))

    return Page(
        size="A4",
        margin=20,
        flows=[
            Flow(name="main", region=Columns(k=Choice(1, 2), gap=Rand(12, 24))),
        ],
        widgets=widgets,
    )


def build_generic_form(schema: Dict[str, str]) -> Page:
    """Build a form-like document (grid, instructions, signature area)."""
    from .fakerx import generate_pairs_for_schema

    pairs = generate_pairs_for_schema(schema, coverage=0.8)
    form_pairs = [(name, label, val) for name, label, val in pairs]

    widgets = [
        Heading(flow="header", level=1, text=Sample("doc_title")),
        Paragraph(flow="header", lines=Rand(1, 3), text="Instruções: Preencha todos os campos obrigatórios."),
        FormGrid(flow="main", rows=Rand(3, 6), cols=Choice(2, 3), pairs=form_pairs, underline=Choice(True, False)),
        Paragraph(flow="footer", lines=1, text="Assinatura: _________________________"),
    ]

    return Page(
        size="A4",
        margin=15,
        flows=[
            Flow(name="header", region=Top(height=60)),
            Flow(name="main", region=Columns(k=Choice(1, 2), gap=Rand(16, 24))),
            Flow(name="footer", region=Bottom(height=40)),
        ],
        widgets=widgets,
    )


def build_generic_screen(schema: Dict[str, str]) -> Page:
    """Build a screen/system-like document (large table, KV sidebars)."""
    from .fakerx import generate_pairs_for_schema

    pairs = generate_pairs_for_schema(schema, coverage=0.6)
    kv_pairs = [(name, label, val) for name, label, val in pairs]

    # Generate table data
    table_rows = Rand(5, 12).sample()
    table_cols = Choice(3, 4, 5).sample()
    table_data = []
    table_data.append([f"Col{i+1}" for i in range(table_cols)])  # Header
    for r in range(table_rows):
        table_data.append([f"Valor{r+1}_{c+1}" for c in range(table_cols)])

    widgets = [
        Heading(flow="header", level=1, text=Sample("doc_title")),
        KVList(flow="sidebar", pairs=kv_pairs[:3], mode="below", gap=8),
        Table(flow="main", shape=(table_rows + 1, table_cols), headers=True, with_rules=Choice(True, False), data=table_data),
        KVList(flow="sidebar2", pairs=kv_pairs[3:], mode="right_of", gap=8),
    ]

    return Page(
        size="A4",
        margin=12,
        flows=[
            Flow(name="header", region=Top(height=50)),
            Flow(name="sidebar", region=Columns(k=1)),
            Flow(name="main", region=Columns(k=Choice(2, 3), gap=Rand(16, 24))),
            Flow(name="sidebar2", region=Columns(k=1)),
        ],
        widgets=widgets,
    )


def build_generic_invoice(schema: Dict[str, str]) -> Page:
    """Build an invoice/statement-like document (header KV, table, totals)."""
    from .fakerx import generate_pairs_for_schema

    pairs = generate_pairs_for_schema(schema, coverage=0.7)
    kv_pairs = [(name, label, val) for name, label, val in pairs]

    # Split pairs: header vs totals
    header_pairs = kv_pairs[:len(kv_pairs)//2]
    totals_pairs = kv_pairs[len(kv_pairs)//2:]

    # Table for items
    table_rows = Rand(4, 10).sample()
    table_cols = Choice(4, 5).sample()
    table_data = []
    table_data.append(["Item", "Descrição", "Qtd", "Valor", "Total"])
    for r in range(table_rows):
        table_data.append([f"{r+1}", f"Item {r+1}", f"{random.randint(1, 10)}", f"R$ {random.uniform(10, 100):.2f}", f"R$ {random.uniform(50, 500):.2f}"])

    widgets = [
        Heading(flow="header", level=1, text=Sample("doc_title")),
        KVList(flow="header", pairs=header_pairs, mode=Choice("right_of", "same_block"), gap=Rand(8, 16)),
        Table(flow="main", shape=(table_rows + 1, table_cols), headers=True, with_rules=True, data=table_data),
        KVList(flow="footer", pairs=totals_pairs, mode="right_of", gap=Rand(8, 16)),
    ]

    return Page(
        size="A4",
        margin=15,
        flows=[
            Flow(name="header", region=Top(height=80)),
            Flow(name="main", region=Columns(k=1)),
            Flow(name="footer", region=Bottom(height=60)),
        ],
        widgets=widgets,
    )


def build_generic_report(schema: Dict[str, str]) -> Page:
    """Build a report/certificate-like document (headings, paragraphs, sparse KV)."""
    from .fakerx import generate_pairs_for_schema

    pairs = generate_pairs_for_schema(schema, coverage=0.5)
    kv_pairs = [(name, label, val) for name, label, val in pairs]

    widgets = [
        Heading(flow="main", level=1, text=Sample("doc_title")),
        Paragraph(flow="main", lines=Rand(4, 8)),
        KVList(flow="main", pairs=kv_pairs[:2], mode=Choice("right_of", "below"), gap=Rand(8, 16)),
        Heading(flow="main", level=2, text=Sample("section_title")),
        Paragraph(flow="main", lines=Rand(3, 6)),
        KVList(flow="main", pairs=kv_pairs[2:], mode="below", gap=Rand(8, 16)),
        Paragraph(flow="footer", lines=1, text="Data: _________________________ Assinatura: _________________________"),
    ]

    return Page(
        size="A4",
        margin=20,
        flows=[
            Flow(name="main", region=Columns(k=Choice(1, 2), gap=Rand(20, 30))),
            Flow(name="footer", region=Bottom(height=50)),
        ],
        widgets=widgets,
    )


# Registry of archetypes
ARCHETYPES: Dict[str, Archetype] = {
    "generic_card": Archetype(
        name="generic_card",
        weight=2.0,
        builder=build_generic_card,
        description="Card/ID-like documents (compact, title, KV, badge)",
    ),
    "generic_form": Archetype(
        name="generic_form",
        weight=1.5,
        builder=build_generic_form,
        description="Form-like documents (grid, instructions, signature)",
    ),
    "generic_screen": Archetype(
        name="generic_screen",
        weight=1.5,
        builder=build_generic_screen,
        description="Screen/system-like documents (large table, KV sidebars)",
    ),
    "generic_invoice": Archetype(
        name="generic_invoice",
        weight=1.0,
        builder=build_generic_invoice,
        description="Invoice/statement-like documents (header KV, table, totals)",
    ),
    "generic_report": Archetype(
        name="generic_report",
        weight=1.0,
        builder=build_generic_report,
        description="Report/certificate-like documents (headings, paragraphs, sparse KV)",
    ),
}


def get_archetype(name: str) -> Optional[Archetype]:
    """Get archetype by name."""
    return ARCHETYPES.get(name)


def list_archetypes() -> List[str]:
    """List all available archetype names."""
    return list(ARCHETYPES.keys())


def sample_archetype() -> Archetype:
    """Sample an archetype weighted by weight."""
    names = list(ARCHETYPES.keys())
    weights = [ARCHETYPES[name].weight for name in names]
    chosen = random.choices(names, weights=weights)[0]
    return ARCHETYPES[chosen]

