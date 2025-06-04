from llvmlite import ir, binding
import itertools

from ast_parse import (
    Number,
    Symbol,
    Operator,
    Input,
    Output,
    Keyword,
    Goto,
    EOL,
    Condition
)

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
fmt = "%d\0"
c_fmt = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt)),
                    bytearray(fmt.encode("utf8")))

global_fmt = ir.GlobalVariable(module, c_fmt.type, name="fmt_int")
global_fmt.linkage = 'internal'
global_fmt.global_constant = True
global_fmt.initializer = c_fmt

printf_ty = ir.FunctionType(INT32, [ir.PointerType(INT8)], var_arg=True)
printf    = ir.Function(module, printf_ty, name="printf")

class CodeGen:
    """Generate LLVM IR whose semantics mirrors the Python Interpreter exactly."""
    OPCODES = ("nop", "mov", "add", "sub", "mul", "div")

    def __init__(self, ast):
        self.ast      = ast
        self.builder  = None
        self.ptr_var  = None
        self.opcode   = "nop"

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

    def visit(self, node):
        return getattr(self, f"visit_{type(node).__name__}")(node)

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
        else:
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
        op = node.opcode
        if op not in ("add", "sub", "mul", "div"):
            raise ValueError(f"Unknown opcode {op}")

        self.opcode = op

    def visit_Input(self, node: Input):
        idx_const = INT32(node.addr)
        ch        = self.builder.call(getchar, [])
        ch8       = self.builder.trunc(ch, INT8)
        self.builder.store(ch8, self._cell_ptr(idx_const))

    def visit_Output(self, node: Output):
        idx_const = ir.Constant(ir.IntType(32), node.addr)
        
        val32, ptr = self._load_cell(idx_const)

        if node.output_type == "char":
            self.builder.call(putchar, [val32])
        else:
            fmt_ptr = self.builder.bitcast(global_fmt, ir.PointerType(ir.IntType(8)))
            self.builder.call(printf, [fmt_ptr, val32])

    def visit_Goto(self, node: Goto):
        # Create basic blocks for branching if they don't exist yet
        if not hasattr(self, 'basic_blocks'):
            # Split the program into lines
            self.basic_blocks = {}
            
            # Create a basic block for each line
            lines = self._split_by_class(self.ast.statements, EOL)
            for i in range(len(lines)):
                self.basic_blocks[i] = self.builder.function.append_basic_block(f"line_{i}")
        
        # Branch to the target line's basic block
        target_line = node.addr
        if target_line in self.basic_blocks:
            self.builder.branch(self.basic_blocks[target_line])
        else:
            raise ValueError(f"Cannot goto line {target_line}: line number out of range")

    def visit_Keyword(self, node: Keyword):
        pass

    def visit_EOL(self, node: EOL):
        pass

    def visit_Condition(self, node: Condition):
        # Evaluate condition value (right side) first
        self.visit(node.right_stmt)
        # Load the value to check
        val32, _ = self._load_cell(self._get_ptr_idx())
        # Compare with zero using icmp with "eq" predicate
        cond = self.builder.icmp_unsigned("==", val32, INT32(0))
        
        with self.builder.if_then(cond):
            # Execute the left statement only if condition is true
            self.visit(node.left_stmt)

    def run(self):
        fn_t  = ir.FunctionType(INT32, ())
        main  = ir.Function(module, fn_t, name="main")
        entry_block = main.append_basic_block("entry")
        self.builder = ir.IRBuilder(entry_block)

        self.ptr_var = self.builder.alloca(INT32, name="ptr")
        self._set_ptr_idx(INT32(0))

        lines = self._split_by_class(self.ast.statements, EOL)
        
        # Create basic blocks for each line
        self.basic_blocks = {}
        for i in range(len(lines)):
            self.basic_blocks[i] = main.append_basic_block(f"line_{i}")
        
        # Create a final block for the return
        final_block = main.append_basic_block("final")
        
        # Branch from entry to first line
        self.builder.branch(self.basic_blocks[0])
        
        # Generate code for each line in its own basic block
        for i, line in enumerate(lines):
            # Position builder at start of this line's block
            self.builder.position_at_end(self.basic_blocks[i])
            
            # Process each statement in the line
            self.opcode = "nop"
            for stmt in line:
                self.visit(stmt)
            
            # If no terminator (like a goto), branch to next line or final block
            if not self.builder.block.is_terminated:
                next_block = self.basic_blocks.get(i + 1, final_block)
                self.builder.branch(next_block)
        
        # Add return in final block
        self.builder.position_at_end(final_block)
        self.builder.ret(INT32(0))
        
        return module

    @staticmethod
    def _split_by_class(objs, split_cls):
        return [list(g) for s, g in itertools.groupby(objs, lambda x: isinstance(x, split_cls)) if not s]