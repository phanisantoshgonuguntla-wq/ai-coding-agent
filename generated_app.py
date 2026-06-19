def add(x, y):

    return x + y


def subtract(x, y):

    return x - y


def multiply(x, y):

    return x * y


def divide(x, y):

    if y == 0:

        raise ValueError("Cannot divide by zero")

    return x / y


# Dictionary mapping operation names to functions

operations = {

    'add': add,

    'subtract': subtract,

    'multiply': multiply,

    'divide': divide

}


def calculator(operation, x, y):

    if operation in operations:

        return operations[operation](x, y)

    else:

        raise ValueError("Invalid operation")


# Example usage:

result = calculator('add', 5, 3)

print(result) # Outputs: 8