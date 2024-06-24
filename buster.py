import os
import re
import ast
import astunparse
import beaupy
from beaupy.spinners import *



def clear():
    os.system("clear||cls")



def stage_1(input_filename, output_filename, iterations=255):
    cnt=0
    clear()
    spinner = Spinner(ARC, "Unraveling code...")
    spinner.start()
    for i in range(iterations):
        cnt+=1
        with open(input_filename, 'r') as ifr:
            file_content = ifr.read().strip()

        content_split = file_content.split("\n")
        if len(content_split) > 10:
            spinner.stop()
            print(f"Unravled {cnt} layers.")
            break
        else:
            og_line=content_split[-1]
            new_line = f"""stuff={og_line[5:-1]}
with open('unravel.py', 'w') as fw:
    print(stuff.decode('utf-8'), file=fw)
"""
            content_split.pop(-1)
            content_split.append(new_line)
            stuff="\n".join(content_split)

            with open(output_filename, 'w') as ofw:
                ofw.write(stuff)

            with open(output_filename, 'r') as ofr:
                o_file_content = ofr.read()
            exec(o_file_content)

            with open('unravel.py', 'r') as ufr:
                i_file_content = ufr.read()

            with open(input_filename, 'w') as ifw:
                ifw.write(i_file_content)




def extract_obfuscated_main_code(file_path):
    code_snippet = ""
    found = False
    pattern = re.compile(r"[A-Za-z0-9]{32}\(\)")

    with open(file_path, 'r') as file:
        lines = file.readlines()

    for i, line in enumerate(lines):
        if pattern.search(line):
            found = True
            code_start_line = i + 1
            code_snippet = ''.join(lines[code_start_line:])
            break

    if not found:
        return None, None

    match = pattern.search(line)
    var_name = match.group()[:-2] if match else None
    return var_name, code_snippet






def find_antiDBG_and_comment_out(input_filename):
    with open(input_filename, 'r') as rf:
        lines=rf.readlines()

    pattern = r"[A-Za-z0-9]{32}\(\)"
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            lines[i] = '# ' + lines[i]
            if i > 0:
                lines[i - 1] = '# ' + lines[i - 1]
            break

    commented_code = ''.join(lines)
    with open(input_filename, 'w') as fw:
        fw.write(commented_code)




def decrypt_strings_in_main_code(input_filename):
    with open(input_filename, 'r') as rf:
        lines = rf.readlines()

    pattern = r"[A-Za-z0-9]{32}\(\)"
    custom_code_block = """import re
pattern = r'[lI]+\([lI]+, [lI]+, [lI]+\)'
def replace_match(match):
    current_match = match.group(0)
    var = eval(current_match)
    return f'"{var}"'
with open('tmp.py', 'r') as fr:
    file_contents = fr.read()
new_contents = re.sub(pattern, replace_match, file_contents)
with open('obf_main.py', 'w') as fw:
    fw.write(new_contents)
raise ExecExit()

"""
    lines_to_insert_after = 2
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            insert_position = i + lines_to_insert_after
            if insert_position >= len(lines):
                lines.append(custom_code_block)
            else:
                lines.insert(insert_position, custom_code_block)
            break

    modified_code = ''.join(lines)
    with open(input_filename, 'w') as fw:
        fw.write(modified_code)




def replace_quotes(content):
    try:
        content = re.sub(r'"""', "'double_quote'", content)
        content = re.sub(r"'''", "'single_quote'", content)
        content = content.replace("\\", "\\\\")

    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
    except Exception as e:
        print(f"Error: {e}")
    return content






# I HATE ast but also love it Lol.
class ContextualRenamer(ast.NodeTransformer):
    def __init__(self):
        self.renamed_vars = {}
        self.renamed_funcs = {}
        self.var_usage = {}
        self.counter = {}
        self.loop_depth = 0


    # Infer function purpose based off of its body and rename.
    def visit_FunctionDef(self, node):
        original_name = node.name
        new_name = self.infer_func_name(node)
        self.renamed_funcs[original_name] = new_name
        node.name = new_name

        for arg in node.args.args:
            new_arg_name = self.generate_var_name(arg.arg)
            self.renamed_vars[arg.arg] = new_arg_name
            arg.arg = new_arg_name

        self.generic_visit(node)
        return node


    # Collecting context.
    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id
                value_type = type(node.value).__name__
                self.var_usage[var_name] = value_type
        self.generic_visit(node)
        return node


    def rename_loop_variable(self, node, new_loop_var):
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                if child.id in self.renamed_vars:
                    child.id = self.renamed_vars[child.id]
        return node


    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store): # This is for variable assignment.
            original_name = node.id
            if original_name not in self.renamed_vars:
                new_name = self.generate_var_name(original_name)
                self.renamed_vars[original_name] = new_name
            node.id = self.renamed_vars[original_name]
        elif isinstance(node.ctx, ast.Load): # This is for variable usage.
            if node.id in self.renamed_vars:
                node.id = self.renamed_vars[node.id]
            elif node.id in self.renamed_funcs:
                node.id = self.renamed_funcs[node.id]
        return node


    # Can add more onto this later.
    def infer_func_name(self, node):
        if any(isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Attribute) and stmt.value.func.attr in ('system', 'run') for stmt in node.body):
            return "system_command"
        elif any(isinstance(stmt, ast.For) for stmt in node.body):
            return "process_loop"
        elif any(isinstance(stmt, ast.If) for stmt in node.body):
            return "conditional_handler"
        return "generic_function"


    # Makes name based off of context and ussage.
    def generate_var_name(self, original_name):
        base_name = "variable"
        if original_name in self.var_usage:
            usage = self.var_usage[original_name]
            if usage == "Str":
                base_name = "input_str"
            elif usage == "List":
                base_name = "list_var"
            elif usage == "Dict":
                base_name = "dict_var"
            elif usage == "Int":
                base_name = "int_var"
            elif usage == "Float":
                base_name = "float_var"
        if base_name not in self.counter:
            self.counter[base_name] = 0
        self.counter[base_name] += 1
        return f"{base_name}{self.counter[base_name]}"

    def visit_If(self, node):
        self.generic_visit(node)
        return node

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in self.renamed_funcs:
            node.func.id = self.renamed_funcs[node.func.id]

        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id in self.renamed_vars:
                arg.id = self.renamed_vars[arg.id]

        for keyword in node.keywords:
            if isinstance(keyword.value, ast.Name) and keyword.value.id in self.renamed_vars:
                keyword.value.id = self.renamed_vars[keyword.value.id]
            elif isinstance(keyword.value, ast.Constant):
                if keyword.arg in self.renamed_vars:
                    keyword.arg = self.renamed_vars[keyword.arg] # Rename the keyword argument itself  |  func_name(keyword_argument="sjdgfsjdgfsjgh").


        if isinstance(node.func, ast.Name) and node.func.id in self.renamed_funcs:
            node.func.id = self.renamed_funcs[node.func.id]

        self.generic_visit(node)
        return node

def rename_code(code):
    tree = ast.parse(code)
    renamer = ContextualRenamer()
    renamer.visit(tree)
    return astunparse.unparse(tree)












# Main stuff
class ExecExit(Exception):
    pass

def safe_exec(code):
    try:
        exec(code, globals())
    except ExecExit:
        print('Main code strings decrypted and are mostly accurate.')

def main():
    output_filename = 'helper.py'
    input_filename = beaupy.prompt("What file would you like to de-obfuscate? - (drag & drop)")
    if not input_filename:
        clear()
        exit()
    input_filename = input_filename.replace("\\", '').strip()


    stage_1(input_filename, output_filename)
    with open(input_filename, 'r') as rf:
        obfuscated_code=rf.read()
    os.remove(output_filename)
    os.remove('unravel.py')
    print("[+] - Stage 1 complete...")

    find_antiDBG_and_comment_out(input_filename) # I don't NEED to do this, but I am because I can :p
    print("[+] - commented out anti debug...")

    var_name, obfuscated_code = extract_obfuscated_main_code(input_filename)
    if var_name and obfuscated_code:
        with open('tmp.py', 'w') as fw:
            fw.write(obfuscated_code)
    else:
        print("Lambda function not found. Something in the code was either changed or was messed up.")
        exit("Deobfuscation & clean up aborted...")
    print("[+] - Extracted main code...")


    decrypt_strings_in_main_code(input_filename)
    with open(input_filename, 'r') as rf:
        new_code = rf.read()
    safe_exec(new_code)
    print("[+] - Decrypted strings...")


    # Clean up - keeping modified & unravled code.
    os.remove("tmp.py")
    with open('obf_main.py') as omfr:
        obf_code = omfr.read()

    obf_code = replace_quotes(obf_code)
    new_code = rename_code(obf_code)

    with open("cleaned_main.py", 'w') as cmfw:
        cmfw.write(new_code)

    os.remove('obf_main.py')
    input('Code has been de-obfuscated and cleaned up to the best of my ability. The cleaned code can be found in "cleaned_main.py"\nPress "enter" to exit...')
    clear()
    exit("Goodbye! <3")














if __name__ == '__main__':
    clear()
    main()
