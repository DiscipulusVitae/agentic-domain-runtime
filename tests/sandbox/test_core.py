from src.sandbox.core import FlowResult, TraceHelper, OutputBuilder


def test_flow_result_to_dict():
    # Test with include_display_name=True
    res1 = FlowResult(
        routing={"domain_id": "test_domain"},
        trace="routing: test_domain",
        success=True,
        output="Hello",
        display_name="Tester",
        include_display_name=True,
    )
    d1 = res1.to_dict()
    assert d1 == {
        "routing": {"domain_id": "test_domain"},
        "trace": "routing: test_domain",
        "success": True,
        "output": "Hello",
        "display_name": "Tester",
    }

    # Test with include_display_name=False
    res2 = FlowResult(
        routing={"domain_id": "test_domain"},
        trace="routing: test_domain",
        success=True,
        output="Hello",
        display_name="Tester",
        include_display_name=False,
    )
    d2 = res2.to_dict()
    assert d2 == {
        "routing": {"domain_id": "test_domain"},
        "trace": "routing: test_domain",
        "success": True,
        "output": "Hello",
    }


def test_trace_helper():
    th = TraceHelper()
    th.add_routing("kitchen")
    th.add_flow_steps(
        extraction=True, validation=True, persistence=True, records_count=3
    )
    assert (
        th.build()
        == "[routing: kitchen] -> [extraction: success] -> [validation: success] -> [persistence: saved (3 records)]"
    )

    th_ambig = TraceHelper()
    th_ambig.add_routing(None)
    assert th_ambig.build() == "[routing: ambiguous/clarification_needed]"

    th_fail = TraceHelper()
    th_fail.add_routing("medical")
    th_fail.add_flow_steps(extraction=False, validation=False, persistence=False)
    assert (
        th_fail.build()
        == "[routing: medical] -> [extraction: failed] -> [validation: failed] -> [persistence: failed]"
    )


def test_output_builder():
    ob = OutputBuilder()
    ob.add_header("⏳ Analyzing...", "Assoc")
    ob.add_line("Line 1")
    ob.add_line("Line 2")
    assert ob.build() == "⏳ Analyzing...\n---\n[Assoc]\nLine 1\nLine 2"
