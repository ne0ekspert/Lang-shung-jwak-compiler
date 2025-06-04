import re
from enum import Enum, auto

class TokenType(Enum):
    KEYWORD     = auto()
    SYMBOL      = auto()
    OPERATOR    = auto()
    NUMBER      = auto()
    INPUT       = auto()
    OUTPUT_CHAR = auto()
    OUTPUT_VAL  = auto()
    GOTO        = auto()
    CONDITION   = auto()
    EOL         = auto()
    WS          = auto()

TOKEN_SPEC = [
    (TokenType.KEYWORD,     r'교주님'),
    (TokenType.SYMBOL,      r'(슝|슈우*웅)'),
    (TokenType.OPERATOR,    r'[~@;,]+'),
    (TokenType.NUMBER,      r'(좍|좌아*악)'),
    (TokenType.INPUT,       r'순수ㅋ*따+잇ㅋ*'),
    (TokenType.OUTPUT_CHAR, r'비비ㅋ* *따+잇ㅋ*'),
    (TokenType.OUTPUT_VAL,  r'비비ㅋ* *보호막ㅋ*따+잇ㅋ*'),
    (TokenType.GOTO,        r'(에잇){1,2}ㅋ*'),
    (TokenType.CONDITION,   r'하는재미'),
    (TokenType.EOL,         r'\n+'),
]

TOKEN_REGEX = re.compile('|'.join(f'(?P<{tok.name}>{pattern})' for tok, pattern in TOKEN_SPEC))

GROUPNAME_TO_TYPE = { tok.name: tok for tok, _ in TOKEN_SPEC }

def lex(code: str):
    pos = 0
    while pos < len(code):
        m = TOKEN_REGEX.match(code, pos)
        if not m:
            raise SyntaxError(f'Unknown token at position {pos}: {code[pos]}')
        group = m.lastgroup              # ex) "KEYWORD"
        tok_type = GROUPNAME_TO_TYPE[group]
        text = m.group(group)
        # WS(공백)는 건너뛰기
        if tok_type is not TokenType.WS:
            yield tok_type, text
        pos = m.end()