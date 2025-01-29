import sys

from antlr4 import CommonTokenStream, InputStream, ParseTreeWalker
from antlr4.error.ErrorListener import ErrorListener

from grammar.LabCmd import LabCmd
from grammar.LabCmdLexer import LabCmdLexer
from grammar.LabCmdListener import LabCmdListener

Total = 5


def print_tab(content, ctx, tabs):
    print("\t" * tabs + content + "\t" * (Total - tabs) + ctx)


def enter_debug(func):
    def wrapper(self, *args, **kwargs):
        if self.debug:
            # Extract the context text for logging
            ctx_text = args[0].getText() if args else ""
            # Print entering message with current indentation
            print_tab(f"Entering {func.__name__}", f">>>> '{ctx_text}'", self.tabs)
            # Increment tabs for nested indentation
            self.tabs += 1
        # Execute the original method
        return func(self, *args, **kwargs)

    return wrapper


def exit_debug(func):
    def wrapper(self, *args, **kwargs):
        if self.debug:
            # Decrement tabs before exiting
            self.tabs -= 1
            # Extract the context text for logging
            ctx_text = args[0].getText() if args else ""
            # Print exiting message with updated indentation
            print_tab(f"Exiting {func.__name__}", f"<<<< '{ctx_text}'", self.tabs)
        # Execute the original method
        return func(self, *args, **kwargs)

    return wrapper


class CmdListener(LabCmdListener):
    def __init__(self, variable_table, debug=True):
        super().__init__()
        self.variable_table = variable_table
        self.result = ""
        self.variable = None
        self.tabs = 0
        self.debug = debug

    # Enter a parse tree produced by LabCmd#command.
    @enter_debug
    def enterCommand(self, ctx: LabCmd.CommandContext):
        if ctx.exception is not None:
            raise ValueError(f"Error encountered: {ctx.exception}")

    # Exit a parse tree produced by LabCmd#command.
    @exit_debug
    def exitCommand(self, ctx: LabCmd.CommandContext):
        pass

    # Enter a parse tree produced by LabCmd#variable.
    @enter_debug
    def enterVariable(self, ctx: LabCmd.VariableContext):
        pass

    # Exit a parse tree produced by LabCmd#variable.
    @exit_debug
    def exitVariable(self, ctx: LabCmd.VariableContext):
        if self.variable is None:
            raise ValueError("Variable not found")

        if isinstance(self.variable, dict):
            raise ValueError(
                f"Entry '{ctx.getText()}' is NOT a value, but another dictionary: '{self.variable}'"
            )

        self.result += str(self.variable)
        self.variable = None

    # Enter a parse tree produced by LabCmd#argument.
    @enter_debug
    def enterArgument(self, ctx: LabCmd.ArgumentContext):
        if self.variable is None:
            self.variable = self.variable_table

        try:
            v = self.variable.get(ctx.getText())
            if v is None:
                raise AttributeError
            self.variable = v
        except AttributeError:
            raise ValueError(
                f"Error: '{ctx.getText()}' is not a valid key or '{self.variable}' is not a valid dictionary"
            )

    # Exit a parse tree produced by LabCmd#argument.
    @exit_debug
    def exitArgument(self, ctx: LabCmd.ArgumentContext):
        pass

    # Enter a parse tree produced by LabCmd#text.
    @enter_debug
    def enterText(self, ctx: LabCmd.TextContext):
        pass

    # Exit a parse tree produced by LabCmd#text.
    @exit_debug
    def exitText(self, ctx: LabCmd.TextContext):
        self.result += ctx.getText()


class CustomErrorListener(ErrorListener):
    def __init__(self, input_text):
        super().__init__()
        self.input_text = input_text.splitlines()

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        # Fetch the offending line
        if 1 <= line <= len(self.input_text):
            error_line = self.input_text[line - 1]
        else:
            error_line = ""

        # Highlight the error location with ^ symbols
        pointer = (
            " " * column
            + "^"
            + " " * (len(offendingSymbol.text) - 1 if offendingSymbol.text else 0)
        )

        info = f"Error at line {line}:{column} - {msg}"
        cnt = column - len(info)
        if cnt > 1:
            info += cnt * "-"
        if cnt > 0:
            info += "|"
        # Prepare the formatted error message
        formatted_error = (
            f"Syntax Error:\n" f"{error_line}\n" f"{pointer}\n" f"{info}\n"
        )

        # Print the formatted error message
        print(formatted_error, file=sys.stderr)

        # Raise an exception to halt parsing
        raise SyntaxError(f"Parsing halted due to syntax error: {msg}")


def replace_variables(input_str, variable_table):
    # Parse the input string
    input_stream = InputStream(input_str)
    lexer = LabCmdLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = LabCmd(token_stream)

    # Remove default error listeners and add custom error listener
    parser.removeErrorListeners()
    parser.addErrorListener(CustomErrorListener(input_str))

    try:
        tree = parser.command()
    except SyntaxError as e:
        raise ValueError(str(e))

    # Walk the parse tree with the custom listener
    listener = CmdListener(variable_table)
    walker = ParseTreeWalker()
    walker.walk(listener, tree)
    r = listener.result
    return r


def main():
    input_str = "python train.py --arg1 {{ a.b }} --arg2 {{c.d.e}} --arg3 {{arg3}} {{ a .e}} {{ e }}"
    variable_table = {
        "a": {"b": "value1", "e": "fcc"},
        "arg3": "e3",
        "c": {"d": {"e": "value2"}},
    }

    try:
        output_str = replace_variables(input_str, variable_table)
        print("table:\t", variable_table)
        print("Input:\t", input_str)
        print("Output:\t", output_str)
    except ValueError as e:
        print("Error:", e)
        exit(1)


# Example usage
if __name__ == "__main__":
    main()
