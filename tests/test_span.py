import gc

import opentracing

from mock import MagicMock

from opentracing.ext import tags as opentracing_tags
from basictracer import BasicTracer


from opentracing_utils.span import (
    get_new_span, adjust_span, extract_span_from_kwargs, remove_span_from_kwargs,
    inspect_span_from_stack
)
from opentracing_utils.span import DEFAULT_SPAN_ARG_NAME

import pytest
import six


def test_get_new_span():

    def f():
        pass

    span_arg_name, span = get_new_span(f, [], {})

    assert DEFAULT_SPAN_ARG_NAME == span_arg_name
    assert isinstance(span, opentracing.Span)


def test_get_new_span_with_extractor():
    opentracing.tracer = BasicTracer()
    parent_span = opentracing.tracer.start_span()

    extractor = MagicMock()
    extractor.return_value = parent_span

    ctx = '123'

    def f(ctx, extras=True):
        pass

    span_arg_name, span = get_new_span(f, [ctx], {'extras': True}, span_extractor=extractor, inspect_stack=False)

    assert DEFAULT_SPAN_ARG_NAME == span_arg_name
    assert span.parent_id == parent_span.context.span_id
    extractor.assert_called_with(ctx, extras=True)


def test_get_new_span_with_failing_extractor():
    def f():
        pass

    def extractor():
        raise RuntimeError('Failed')

    span_arg_name, span = get_new_span(f, [], {}, span_extractor=extractor)

    assert DEFAULT_SPAN_ARG_NAME == span_arg_name
    assert span.parent_id is None


def test_adjust_span(monkeypatch):
    span = MagicMock()
    span.set_tag.side_effect = [Exception, None, None]

    adjust_span(span, 'op_name', 'component', {'tag1': '1', 'tag2': '2'})

    span.set_tag.assert_called_with(opentracing_tags.COMPONENT, 'component')
    span.set_operation_name.assert_called_with('op_name')


def test_extract_span_from_kwargs(monkeypatch):
    span = opentracing.tracer.start_span(operation_name='test_op')

    extracted = extract_span_from_kwargs(span=span, x=1, y='some-value')

    assert extracted == span


def test_extract_span_from_kwargs_no_span(monkeypatch):
    extracted = extract_span_from_kwargs(x=1, y='some-value')

    assert isinstance(extracted, opentracing.Span)


def test_remove_span_from_kwargs(monkeypatch):
    kwargs = {
        'span': opentracing.tracer.start_span(),
        'not_span': 1,
        'also_not_span': 'no span',
    }

    clean_kwargs = remove_span_from_kwargs(**kwargs)

    assert clean_kwargs == {'not_span': 1, 'also_not_span': 'no span'}


@pytest.mark.skipif(six.PY2, reason="gc.get_stats requires >=3.4")
def test_inspect_span_from_stack_does_not_create_reference_cycle():
    # inspect_span_from_stack inspects the stack via stack frames. This can
    # very easily lead to the creation of reference cycles. These are not
    # free-d using reference counting and therefore the GC needs to clean them
    # up. If reference cycles are created frequently and therefore the GC runs
    # frequently, this can have a significant impact on CPU usage and overall
    # latency.
    #
    # This test makes sure that this function doesn't create a reference cycle
    # by testing whether the GC is able to collect any objects after calling
    # this function.

    # Run a collection to ensure that all reference cycles that may have been
    # created up to this point to be collected, so that they don't mess up our
    # measurement.
    gc.collect()

    previous_stats = gc.get_stats()
    inspect_span_from_stack()
    gc.collect()
    stats = gc.get_stats()

    for previous_generation, current_generation in zip(previous_stats, stats):
        assert previous_generation['collected'] == current_generation['collected']
