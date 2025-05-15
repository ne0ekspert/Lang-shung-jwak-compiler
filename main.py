from preprocessor import remove_punct
from lexer import lex
from parser import Parser
from interpreter import Interpreter

# 이미 lex()로 만든 토큰 스트림(tokens)을 받았다고 가정
f = open('hello_world.jwak', 'r')
clean_code = remove_punct(f.read())
tokens = list(lex(clean_code))

parser = Parser(tokens)
ast = parser.parse_program()

print(ast)

interp = Interpreter()
interp.run(ast)

f.close()