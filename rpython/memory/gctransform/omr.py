from rpython.memory.gctransform.transform import GCTransformer, mallocHelpers
from rpython.memory.gctransform.support import (get_rtti,
    _static_deallocator_body_for_type, LLTransformerOp, ll_call_destructor,
    ll_report_finalizer_error)
from rpython.rtyper.lltypesystem import lltype, llmemory
from rpython.flowspace.model import Constant
from rpython.rtyper.lltypesystem.lloperation import llop
from rpython.rtyper import rmodel


class OMRGCTransformer(GCTransformer):
    malloc_zero_filled = True
    FINALIZER_PTR = lltype.Ptr(lltype.FuncType([llmemory.GCREF], lltype.Void))

    def __init__(self, translator, inline=False):
        super(OMRGCTransformer, self).__init__(translator, inline=inline)
        self.finalizer_funcptrs = {}

        atomic_mh = mallocHelpers(gckind='gc')
        atomic_mh.allocate = lambda size: llop.omr_malloc(llmemory.GCREF, size)
        ll_malloc_fixedsize_atomic = atomic_mh._ll_malloc_fixedsize

        mh = mallocHelpers(gckind='gc')
        mh.allocate = lambda size: llop.omr_malloc(llmemory.GCREF, size)
        ll_malloc_fixedsize = mh._ll_malloc_fixedsize

        # XXX, do we need/want an atomic version of this function?
        ll_malloc_varsize_no_length = mh.ll_malloc_varsize_no_length
        ll_malloc_varsize = mh.ll_malloc_varsize

        if self.translator:
            self.malloc_fixedsize_ptr = self.inittime_helper(
                ll_malloc_fixedsize, [lltype.Signed], llmemory.GCREF)
            self.malloc_fixedsize_atomic_ptr = self.inittime_helper(
                ll_malloc_fixedsize_atomic, [lltype.Signed], llmemory.GCREF)
            self.malloc_varsize_no_length_ptr = self.inittime_helper(
                ll_malloc_varsize_no_length, [lltype.Signed]*3, llmemory.GCREF, inline=False)
            self.malloc_varsize_ptr = self.inittime_helper(
                ll_malloc_varsize, [lltype.Signed]*4, llmemory.GCREF, inline=False)
            if self.translator.config.translation.rweakref:
                (ll_weakref_create, ll_weakref_deref,
                 self.WEAKLINK, self.convert_weakref_to
                        ) = build_weakref(self.translator.config)
                self.weakref_create_ptr = self.inittime_helper(
                    ll_weakref_create, [llmemory.GCREF], llmemory.WeakRefPtr,
                    inline=False)
                self.weakref_deref_ptr = self.inittime_helper(
                    ll_weakref_deref, [llmemory.WeakRefPtr], llmemory.GCREF)

            self.mixlevelannotator.finish()   # for now
            self.mixlevelannotator.backend_optimize()

        self.finalizer_triggers = []
        self.finalizer_queue_indexes = {}    # {fq: index}

    def gct_fv_gc_malloc(self, hop, flags, TYPE, c_size):
        
        funcptr = self.malloc_fixedsize_ptr
        opname = 'boehm_malloc'
        tr = self.translator

        if tr and tr.config.translation.reverse_debugger:
            v_raw = hop.genop(opname, [c_size], resulttype=llmemory.GCREF)
        else:
            v_raw = hop.genop("direct_call",
                              [funcptr, c_size],
                              resulttype=llmemory.GCREF)
        return v_raw

    gct_fv_gc_malloc_varsize = gct_fv_gc_malloc

    
    def get_finalizer_queue_index(self, hop):
        pass

    def gct_gc_fq_register(self, hop):
        index = self.get_finalizer_queue_index(hop)
        c_index = rmodel.inputconst(lltype.Signed, index)
        v_ptr = hop.spaceop.args[1]
        assert v_ptr.concretetype == llmemory.GCREF
        hop.genop("direct_call", [self.register_finalizer_ptr, self.c_const_gc,
                                  c_index, v_ptr])

    def gct_gc_fq_next_dead(self, hop):
        index = self.get_finalizer_queue_index(hop)
        c_ll_next_dead = self.finalizer_handlers[index][2]
        v_adr = hop.genop("direct_call", [c_ll_next_dead],
                          resulttype=llmemory.Address)
        hop.genop("cast_adr_to_ptr", [v_adr],
                  resultvar = hop.spaceop.result)

    def gct_weakref_create(self, hop):
        v_instance, = hop.spaceop.args
        v_gcref = hop.genop("cast_opaque_ptr", [v_instance],
                            resulttype=llmemory.GCREF)
        v_wref = hop.genop("direct_call",
                           [self.weakref_create_ptr, v_gcref],
                           resulttype=llmemory.WeakRefPtr)
        hop.cast_result(v_wref)

    def gct_zero_everything_inside(self, hop):
        pass

    def gct_zero_gc_pointers_inside(self, hop):
        pass

    def gct_weakref_deref(self, hop):
        v_wref, = hop.spaceop.args
        v_gcref = hop.genop("direct_call",
                            [self.weakref_deref_ptr, v_wref],
                            resulttype=llmemory.GCREF)
        hop.cast_result(v_gcref)

    def gct_gc_id(self, hop):
        v_obj = hop.spaceop.args[0]
        v_adr = hop.genop("cast_ptr_to_adr", [v_obj],
                          resulttype=llmemory.Address)
        hop.genop("direct_call", [self.identityhash_ptr, v_adr],
                  resultvar=hop.spaceop.result)

    def gcheader_initdata(self, obj):
        o = lltype.top_container(obj)
        hdr = self.gcdata.gc.gcheaderbuilder.header_of_object(o)
        return hdr._obj