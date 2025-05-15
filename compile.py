import os
from llvmlite import ir, binding
import itertools

from preprocessor import remove_punct
from lexer import lex
from parser import *

binding.initialize()
binding.initialize_native_target()
binding.initialize_native_asmprinter()

INT8  = ir.IntType(8)
INT32 = ir.IntType(32)

module = ir.Module(name="lsj")
module.triple = binding.get_default_triple()

# tape[30000]
TAPE_TY = ir.ArrayType(INT8, 30_000)
mem     = ir.GlobalVariable(module, TAPE_TY, name="mem")
mem.linkage = "internal"
mem.initializer = ir.Constant(TAPE_TY, None)

# putchar / getchar
putchar = ir.Function(module, ir.FunctionType(INT32, [INT32]), name="putchar")
getchar = ir.Function(module, ir.FunctionType(INT32, []),     name="getchar")

# printf("%d\n", ...)
printf_ty = ir.FunctionType(INT32, [ir.PointerType(INT8)], var_arg=True)
printf    = ir.Function(module, printf_ty, name="printf")

class CodeGen:
    """Generate LLVM IR whose semantics mirrors the Python Interpreter exactly."""
    OPCODES = ("nop", "mov", "add", "sub", "mul", "div")

    def __init__(self, ast):
        self.ast      = ast
        self.builder  = None       # will be set in run()
        self.ptr_var  = None       # i32* alloca holding current index
        self.opcode   = "nop"      # Python-side compile-time flag

    # ─────────────────────────── helpers ────────────────────────────
    def _get_ptr_idx(self):
        return self.builder.load(self.ptr_var, name="cur.ptr.idx")

    def _set_ptr_idx(self, idx_val: ir.Value):
        self.builder.store(idx_val, self.ptr_var)

    def _cell_ptr(self, idx_val: ir.Value):
        return self.builder.gep(mem, [INT32(0), idx_val], inbounds=True)

    def _load_cell(self, idx_val: ir.Value):
        ptr   = self._cell_ptr(idx_val)
        val8  = self.builder.load(ptr)
        val32: ir.CastInstr = self.builder.zext(val8, INT32)
        return val32, ptr

    def _store_cell(self, idx_val: ir.Value, rhs32: ir.Value):
        ptr = self._cell_ptr(idx_val)
        rhs8: ir.CastInstr = self.builder.trunc(rhs32, INT8)
        self.builder.store(rhs8, ptr)

    # ────────────────────────── visitor dispatch ─────────────────────────
    def visit(self, node):
        return getattr(self, f"visit_{type(node).__name__}")(node)

    # ───────────────────────────── Visitors ─────────────────────────────
    def visit_Number(self, node: Number):
        rhs32 = INT32(node.value)
        cur_idx = self._get_ptr_idx()
        cur32, _ = self._load_cell(cur_idx)

        if self.opcode == "mov":
            self._store_cell(cur_idx, rhs32)
        elif self.opcode == "add":
            self._store_cell(cur_idx, self.builder.add(cur32, rhs32))
        elif self.opcode == "sub":
            self._store_cell(cur_idx, self.builder.sub(cur32, rhs32))
        elif self.opcode == "mul":
            self._store_cell(cur_idx, self.builder.mul(cur32, rhs32))
        elif self.opcode == "div":
            self._store_cell(cur_idx, self.builder.sdiv(cur32, rhs32))
        else:   # nop → nothing
            pass

    def visit_Symbol(self, node: Symbol):
        idx_const = INT32(node.addr)
        cur_idx   = self._get_ptr_idx()
        cur32, cur_ptr = self._load_cell(cur_idx)
        rhs32,  _      = self._load_cell(idx_const)

        if self.opcode == "nop":
            self._set_ptr_idx(idx_const)
            self._store_cell(idx_const, INT32(0))
            self.opcode = 'mov'
        elif self.opcode == "mov":
            self._store_cell(cur_idx, rhs32)
        elif self.opcode == "add":
            self._store_cell(cur_idx, self.builder.add(cur32, rhs32))
        elif self.opcode == "sub":
            self._store_cell(cur_idx, self.builder.sub(cur32, rhs32))
        elif self.opcode == "mul":
            self._store_cell(cur_idx, self.builder.mul(cur32, rhs32))
        elif self.opcode == "div":
            self._store_cell(cur_idx, self.builder.sdiv(cur32, rhs32))

    def visit_Operator(self, node: Operator):
        op = node.opcode           # 'add' | 'sub' | 'mul' | 'div'
        if op not in ("add", "sub", "mul", "div"):
            raise ValueError(f"Unknown opcode {op}")

        self.opcode = op

    def visit_Input(self, node: Input):
        idx_const = INT32(node.addr)
        ch        = self.builder.call(getchar, [])
        ch8       = self.builder.trunc(ch, INT8)
        self.builder.store(ch8, self._cell_ptr(idx_const))

    def visit_Output(self, node: Output):
        # 1) 출력할 셀 주소를 직접 계산
        idx_const = ir.Constant(ir.IntType(32), node.addr)
        
        # 2) 그 셀에서 값 읽기
        val32, ptr = self._load_cell(idx_const)

        # 3) char vs val 구분 출력
        if node.output_type == "char":
            self.builder.call(putchar, [val32])
        else:
            # printf("%d", val)
            fmt = "%d\0"
            c_fmt = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt)),
                                bytearray(fmt.encode("utf8")))
            global_fmt = ir.GlobalVariable(module, c_fmt.type, name="fmt_int")
            global_fmt.linkage = 'internal'
            global_fmt.global_constant = True
            global_fmt.initializer = c_fmt
            fmt_ptr = self.builder.bitcast(global_fmt, ir.PointerType(ir.IntType(8)))
            self.builder.call(printf, [fmt_ptr, val32])

    def visit_Keyword(self, node: Keyword):   # not used yet
        pass

    def visit_EOL(self, node: EOL):
        # 줄 끝 → opcode 리셋
        pass

    # ─────────────────────────────── run ───────────────────────────────
    def run(self):
        # ===== main() =====
        fn_t  = ir.FunctionType(INT32, ())
        main  = ir.Function(module, fn_t, name="main")
        block = main.append_basic_block("entry")
        self.builder = ir.IRBuilder(block)

        # ptr = 0
        self.ptr_var = self.builder.alloca(INT32, name="ptr")
        self._set_ptr_idx(INT32(0))

        # 파싱된 Program을 라인별로 분리 (Interpreter 로직과 동일)
        lines = self._split_by_class(self.ast.statements, EOL)

        for line in lines:
            self.opcode = "nop"
            for stmt in line:
                self.visit(stmt)

        # return 0
        self.builder.ret(INT32(0))

    # ───────────────────────── util: split by class ─────────────────────────
    @staticmethod
    def _split_by_class(objs, split_cls):
        return [list(g) for s, g in itertools.groupby(objs, lambda x: isinstance(x, split_cls)) if not s]

if __name__ == '__main__':
    with open('hello_world.jwak', 'r', encoding='utf-8') as f:
        clean_code = remove_punct(f.read())
        tokens = list(lex(clean_code))

        parser = Parser(tokens)
        ast = parser.parse_program()

        codegen = CodeGen(ast)
        codegen.run()

    with open('out.ll', 'w', encoding='utf-8') as f:
        f.write(str(module))

    os.system("llc out.ll -filetype=obj -o out.o")
    os.system("gcc out.o -o lsj_exec")