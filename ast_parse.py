from dataclasses import dataclass
from typing import List
from lexer import TokenType

# 기본 AST 노드 타입
class ASTNode:
    pass

@dataclass
class Number(ASTNode):
    token: str

    @property
    def value(self):
        if self.token == '좍':
            return 1
        return 2 + self.token.count('아')

@dataclass
class Keyword(ASTNode):
    token: str

@dataclass
class Symbol(ASTNode):
    token: str

    @property
    def addr(self):
        if self.token == '슝':
            return 0
        return 1 + self.token.count('우')

@dataclass
class Operator(ASTNode):
    op: str

    @property
    def opcode(self):
        op = self.op[0]
        if op == '~':
            return 'add'
        if op == ';':
            return 'sub'
        if op == ',':
            return 'mul'
        if op == '@':
            return 'div'

@dataclass
class Input(ASTNode):
    token: str

    @property
    def addr(self):
        return self.token.count('ㅋ') - 1

@dataclass
class Output(ASTNode):
    token: str
    output_type: str  # 'char' or 'val'

    @property
    def addr(self):
        return self.token.count('ㅋ') - 1

@dataclass
class Goto(ASTNode):
    token: str

    @property
    def addr(self):
        return self.token.count('ㅋ')
    
    @property
    def dir(self):
        return self.token.count('에잇')

@dataclass
class EOL(ASTNode):
    pass

@dataclass
class Program(ASTNode):
    statements: List[ASTNode]

@dataclass
class Condition(ASTNode):
    left_stmt: ASTNode  # Statement to execute if condition is true
    right_stmt: ASTNode  # Statement that produces the condition value

    def __init__(self, left_stmt, right_stmt):
        self.left_stmt = left_stmt
        self.right_stmt = right_stmt

class Parser:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def advance(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def expect(self, expected_type):
        tok_type, tok_val = self.peek()
        if tok_type != expected_type:
            raise SyntaxError(f"Expected {expected_type}, got {tok_type} ('{tok_val}') at pos {self.pos}")
        return self.advance()

    def parse_program(self) -> Program:
        stmts = []
        while self.peek()[0] is not None:
            stmts.append(self.parse_statement())
        return Program(statements=stmts)

    def parse_statement(self) -> ASTNode:
        tok_type, tok_val = self.peek()
        if tok_type == TokenType.NUMBER:
            _, tok = self.advance()
            return Number(token=tok)
        if tok_type == TokenType.KEYWORD:
            _, kw = self.advance()
            return Keyword(token=kw)
        if tok_type == TokenType.SYMBOL:
            _, sym = self.advance()
            return Symbol(token=sym)
        if tok_type == TokenType.OPERATOR:
            _, op = self.advance()
            return Operator(op=op)
        if tok_type == TokenType.INPUT:
            _, inp = self.advance()
            return Input(token=inp)
        if tok_type == TokenType.OUTPUT_CHAR:
            _, out = self.advance()
            return Output(token=out, output_type='char')
        if tok_type == TokenType.OUTPUT_VAL:
            _, out = self.advance()
            return Output(token=out, output_type='val')
        if tok_type == TokenType.EOL:
            _, _ = self.advance()
            return EOL()
        if tok_type == TokenType.GOTO:
            _, goto = self.advance()
            return Goto(token=goto)
        if tok_type == TokenType.CONDITION:
            # Consume the condition token
            self.advance()
            # Parse the left statement (to execute if condition is true)
            left_stmt = self.parse_statement()
            # Parse the right statement (condition value)
            right_stmt = self.parse_statement()
            return Condition(left_stmt, right_stmt)
        
        raise SyntaxError(f"Unknown statement start: {tok_type} ('{tok_val}')")
