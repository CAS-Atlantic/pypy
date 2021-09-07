from rpython.memory.gctransform.boehm import OMRGCTransformer
from rpython.memory.gctransform.test.test_transform import rtype_and_transform, getops
from rpython.memory.gctransform.test.test_refcounting import make_deallocator
from rpython.rtyper.lltypesystem import lltype
from rpython.translator.translator import graphof
from rpython.translator.c.gc import BoehmGcPolicy
from rpython.memory.gctransform.test.test_transform import LLInterpedTranformerTests


class TestLLInterpedOMR(LLInterpedTranformerTests):
    gcpolicy = BoehmGcPolicy


def test_omr_simple():
    class C:
        pass
    def f():
        c = C()
        c.x = 1
        return c.x
    t, transformer = rtype_and_transform(
        f, [], OMRGCTransformer, check=False)
    ops = getops(graphof(t, f))
    assert len(ops.get('direct_call', [])) <= 1
    gcs = [k for k in ops if k.startswith('gc')]
    assert len(gcs) == 0
