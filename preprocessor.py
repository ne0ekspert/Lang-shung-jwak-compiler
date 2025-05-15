def remove_punct(code: str):
    code = code.replace(' ', '')
    code = code.replace('?', '')
    code = code.replace('!', '')
    code = code.replace('.', '')

    return code