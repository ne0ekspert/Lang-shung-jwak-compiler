import os
import argparse

from preprocessor import remove_punct
from lexer import lex
from ast_parse import Parser
from frontend import CodeGen

parser = argparse.ArgumentParser(
                    prog='jwaklang',
                    description='Lang-shung-jwak compiler')

parser.add_argument('filename')

args = parser.parse_args()

if __name__ == '__main__':
    with open(args.filename, 'r', encoding='utf-8') as f:
        clean_code = remove_punct(f.read())
        tokens = list(lex(clean_code))

        parser = Parser(tokens)
        ast = parser.parse_program()

        codegen = CodeGen(ast)
        module = codegen.run()

    with open('out.ll', 'w', encoding='utf-8') as f:
        f.write(str(module))

    os.system("llc out.ll -filetype=obj -o out.o -relocation-model=pic")
    os.system("gcc -fPIE -pie out.o -o lsj_exec")