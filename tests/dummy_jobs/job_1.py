"""
Dummy job for testing.
Takes in 2 arguments.
Prints `arg1`.
"""

import argparse
from ast import literal_eval

import labtasker

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--arg1",
        type=str,
        required=True,
    )
    parser.add_argument("--arg2", type=str, required=True)
    parser.add_argument("--arg5", type=str, required=True)
    args = parser.parse_args()

    arg2 = literal_eval(args.arg2)
    assert arg2["arg4"] == "foo"

    assert args.arg5 == 'He said: "What\'s the whether like today?"', args.arg5

    task_name = labtasker.task_info().task_name
    assert (
        task_name == f"test_task_{args.arg1}"
    ), f"task_name: {task_name}, args.arg1: {args.arg1}"
    print(f"Running task {args.arg1}")
